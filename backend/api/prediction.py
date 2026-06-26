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
            "led_status": r.led_status,
            "device_status": r.device_status,
        }
        for r in rows
    ]


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
    if metric not in _VALID_METRICS:
        return jsonify({"error": f"metric 必须为 {_VALID_METRICS} 之一"}), 400
    if model_name not in _VALID_MODELS:
        return jsonify({"error": f"model_name 必须为 {_VALID_MODELS} 之一"}), 400

    dev, err = _device_or_404(device_id)
    if err:
        return err

    # 拉取历史数据
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
    """
    device_id = request.args.get("device_id", type=int)
    metric = request.args.get("metric")
    if not device_id or metric not in _VALID_METRICS:
        return jsonify({"error": "device_id + metric 必填,metric ∈ temperature/humidity/light"}), 400

    dev, err = _device_or_404(device_id)
    if err:
        return err

    pred = (
        Prediction.query
        .filter_by(device_id=dev.id, metric=metric)
        .order_by(Prediction.predicted_at.desc())
        .first()
    )
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
      limit: int (默认 20)
    """
    device_id = request.args.get("device_id", type=int)
    metric = request.args.get("metric")
    limit = request.args.get("limit", 20, type=int)
    limit = max(1, min(limit, 100))

    if not device_id:
        return jsonify({"error": "device_id 必填"}), 400
    dev, err = _device_or_404(device_id)
    if err:
        return err

    q = Prediction.query.filter_by(device_id=dev.id)
    if metric:
        if metric not in _VALID_METRICS:
            return jsonify({"error": "metric 不合法"}), 400
        q = q.filter_by(metric=metric)
    rows = q.order_by(Prediction.predicted_at.desc()).limit(limit).all()
    return jsonify([p.to_dict() for p in rows])
