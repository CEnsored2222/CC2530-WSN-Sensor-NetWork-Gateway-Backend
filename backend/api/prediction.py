# -*- coding: utf-8 -*-
"""预测接口。

- POST /api/predictions/run   触发预测(即时训练 + 预测)
- GET  /api/predictions/latest  最新一条预测
- GET  /api/predictions/history  历史预测列表
"""
from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request

from extensions import db
from models.device import Device
from models.prediction import Prediction
from models.sensor_data import SensorData
from utils.auth import jwt_required
from ml import predictor

bp = Blueprint("prediction", __name__)

_VALID_METRICS = ("temperature", "humidity", "light")
_VALID_MODELS = ("linear", "svr")
_MLP_MODELS = ("mlp_temp_hum", "mlp_light")
# 默认拉取最近 144 条历史数据(10min/条 × 144 = 24 小时)
_DEFAULT_LOOKBACK = 144


def _device_or_404(device_id):
    dev = db.session.get(Device, device_id)
    if not dev or dev.gateway.user_id != g.current_user.id:
        return None, (jsonify({"error": "设备不存在或无权访问"}), 404)
    return dev, None


def _fetch_history(device_id, limit=_DEFAULT_LOOKBACK):
    """拉取该设备最近 N 条 sensor_data,按时间正序。"""
    rows = (
        SensorData.query
        .filter_by(device_id=device_id)
        .order_by(SensorData.recorded_at.desc())
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))  # 改为正序
    return [
        {
            "recorded_at": r.recorded_at,
            "temperature": float(r.temperature) if r.temperature is not None else None,
            "humidity": float(r.humidity) if r.humidity is not None else None,
            "light": float(r.light) if r.light is not None else None,
        }
        for r in rows
    ]


def _purge_expired_predictions(device_id):
    """删除该设备已完全过期的预测记录(惰性清理)。

    过期判定:predicted_at + horizon_minutes < 该设备最新传感器数据时间。
    即预测窗口已完全落后于实际数据,不再有参考价值。

    本函数会执行 db.session.commit(),调用时 session 中不应有未提交的 add。
    清理失败时仅 rollback 并静默返回(惰性清理不应阻断业务读取)。

    数据库压力分析:
    - predictions 表有 idx_dev_metric_time 复合索引,按设备过滤走索引
    - 候选集很小(每设备每次预测生成 1-2 条,课程项目场景下 < 1000 条/设备)
    - DELETE 操作 < 50ms,仅在 /run, /latest, /history 调用,非高频
    """
    try:
        latest_data = (
            SensorData.query
            .filter_by(device_id=device_id)
            .order_by(SensorData.recorded_at.desc())
            .first()
        )
        if not latest_data:
            return 0  # 无传感器数据,无法判定过期
        threshold = latest_data.recorded_at

        # 候选集:预测时间早于最新数据时间(预测窗口可能与实际数据重叠的不算过期)
        candidates = (
            Prediction.query
            .filter_by(device_id=device_id)
            .filter(Prediction.predicted_at < threshold)
            .all()
        )
        # 精筛:整个预测窗口都在最新数据之前
        expired_ids = [
            p.id for p in candidates
            if p.predicted_at + timedelta(minutes=p.horizon_minutes) < threshold
        ]
        if not expired_ids:
            return 0
        Prediction.query.filter(Prediction.id.in_(expired_ids)).delete(synchronize_session=False)
        db.session.commit()
        return len(expired_ids)
    except Exception:
        db.session.rollback()
        return 0  # 清理失败不影响主流程


@bp.post("/predictions/run")
@jwt_required
def run_prediction():
    """触发预测。

    入参 JSON:
      device_id: int (必填)
      metric: str (必填, temperature/humidity/light)
      model_name: str (默认 linear, 可选 svr)
      horizon_minutes: int (默认 60, 范围 10-240, 对齐 10min 采样间隔)
      lookback: int (可选, 拉取历史样本数, 默认 144 = 24 小时)
    """
    data = request.get_json(silent=True) or {}
    device_id = data.get("device_id")
    metric = data.get("metric")
    model_name = data.get("model_name") or "linear"
    horizon = data.get("horizon_minutes") or 60
    lookback = data.get("lookback") or _DEFAULT_LOOKBACK

    if not device_id:
        return jsonify({"error": "device_id 必填"}), 400
    if model_name not in _VALID_MODELS and model_name not in _MLP_MODELS:
        return jsonify({"error": f"model_name 必须为 {_VALID_MODELS + _MLP_MODELS} 之一"}), 400
    # metric 必填仅 for linear/svr; mlp_* 多输出模型忽略 metric
    if model_name in _VALID_MODELS and metric not in _VALID_METRICS:
        return jsonify({"error": f"metric 必须为 {_VALID_METRICS} 之一"}), 400

    dev, err = _device_or_404(device_id)
    if err:
        return err

    # 清理该设备已过期的预测记录(惰性清理,在生成新预测前先回收旧记录)
    _purge_expired_predictions(dev.id)

    # ===== MLP 分流(mlp_temp_hum / mlp_light)=====
    if model_name in _MLP_MODELS:
        import extensions as ext_mod
        from config import Config
        from models.ml import MlModel
        trainer = getattr(ext_mod, "onnx_trainer", None)
        if trainer is None:
            return jsonify({"error": "MLP 模块未安装(PyTorch/onnxruntime 不可用)"}), 503
        ml_model = MlModel.query.get(model_name)
        if not ml_model or not ml_model.last_train_time:
            return jsonify({"error": "模型未训练,请先 POST /api/predictions/mlp/train"}), 400
        # 按 MLP_LOOKBACK_HOURS 拉取该设备历史数据(单设备推理,非多设备聚合)
        since = datetime.now() - timedelta(hours=Config.MLP_LOOKBACK_HOURS)
        db_rows = (SensorData.query
                   .filter_by(device_id=dev.id)
                   .filter(SensorData.recorded_at >= since)
                   .order_by(SensorData.recorded_at)
                   .all())
        row_dicts = [{"recorded_at": r.recorded_at,
                       "temperature": r.temperature,
                       "humidity": r.humidity,
                       "light": r.light} for r in db_rows]
        if not row_dicts:
            return jsonify({"error": "无历史数据"}), 400
        try:
            result = trainer.predict(model_name, row_dicts, horizon_minutes=int(horizon))
        except Exception as e:
            return jsonify({"error": f"MLP 推理失败: {str(e)}"}), 500
        if "error" in result:
            return jsonify(result), 400
        # 多输出单事务写入(修复 P1 #8: mlp_temp_hum 写 2 条,任一失败全部回滚)
        preds = []
        for metric_name, pred_data in result.items():
            preds.append(Prediction(
                device_id=dev.id,
                metric=metric_name,
                horizon_minutes=int(horizon),
                predicted_values=pred_data["predicted_values"],
                history_snapshot=pred_data["history_snapshot"],
                model_name=model_name,
                mae=None, r2=None,
            ))
            db.session.add(preds[-1])
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({"error": "预测结果保存失败"}), 500
        return jsonify([p.to_dict() for p in preds]), 201

    # ===== linear / svr 原有流程(不变)=====
    history = _fetch_history(dev.id, limit=int(lookback))
    if len(history) < predictor.MIN_SAMPLES:
        return jsonify({
            "error": f"历史数据不足,至少需要 {predictor.MIN_SAMPLES} 条,当前 {len(history)} 条"
        }), 400

    # 调用预测引擎
    try:
        result = predictor.predict(
            rows=history,
            metric=metric,
            model_name=model_name,
            horizon_minutes=int(horizon),
        )
    except Exception as e:
        return jsonify({"error": f"预测失败: {str(e)}"}), 500

    if "error" in result:
        return jsonify(result), 400

    # 持久化
    pred = Prediction(
        device_id=dev.id,
        metric=metric,
        horizon_minutes=result["horizon_minutes"],
        predicted_values=result["predicted_values"],
        history_snapshot=result["history_snapshot"],
        model_name=result["model_name"],
        mae=result.get("mae"),
        r2=result.get("r2"),
    )
    db.session.add(pred)
    db.session.commit()

    return jsonify(pred.to_dict()), 201


@bp.get("/predictions/latest")
@jwt_required
def latest_prediction():
    """获取某设备某指标的最新预测。

    入参 query:
      device_id: int (必填)
      metric: str (必填)
      model_name: str (可选, linear/svr/mlp_temp_hum/mlp_light)
    """
    device_id = request.args.get("device_id", type=int)
    metric = request.args.get("metric")
    model_name = request.args.get("model_name")
    if not device_id or metric not in _VALID_METRICS:
        return jsonify({"error": "device_id + metric 必填,metric ∈ temperature/humidity/light"}), 400
    if model_name and model_name not in _VALID_MODELS + _MLP_MODELS:
        return jsonify({"error": f"model_name 必须为 {_VALID_MODELS + _MLP_MODELS} 之一"}), 400

    dev, err = _device_or_404(device_id)
    if err:
        return err

    # 惰性清理过期预测,确保返回的最新记录是仍有效的
    _purge_expired_predictions(dev.id)

    q = Prediction.query.filter_by(device_id=dev.id, metric=metric)
    if model_name:
        q = q.filter_by(model_name=model_name)
    pred = q.order_by(Prediction.predicted_at.desc()).first()
    if not pred:
        return jsonify(None)
    return jsonify(pred.to_dict())


@bp.get("/predictions/history")
@jwt_required
def prediction_history():
    """历史预测列表。

    入参 query:
      device_id: int (必填)
      metric: str (可选)
      model_name: str (可选, linear/svr/mlp_temp_hum/mlp_light)
      limit: int (默认 20)
    """
    device_id = request.args.get("device_id", type=int)
    metric = request.args.get("metric")
    model_name = request.args.get("model_name")
    limit = request.args.get("limit", 20, type=int)
    limit = max(1, min(limit, 100))

    if not device_id:
        return jsonify({"error": "device_id 必填"}), 400
    if model_name and model_name not in _VALID_MODELS + _MLP_MODELS:
        return jsonify({"error": f"model_name 必须为 {_VALID_MODELS + _MLP_MODELS} 之一"}), 400
    dev, err = _device_or_404(device_id)
    if err:
        return err

    # 惰性清理过期预测,确保历史列表中不含已失效记录
    _purge_expired_predictions(dev.id)

    q = Prediction.query.filter_by(device_id=dev.id)
    if metric:
        if metric not in _VALID_METRICS:
            return jsonify({"error": "metric 不合法"}), 400
        q = q.filter_by(metric=metric)
    if model_name:
        q = q.filter_by(model_name=model_name)
    rows = q.order_by(Prediction.predicted_at.desc()).limit(limit).all()
    return jsonify([p.to_dict() for p in rows])
