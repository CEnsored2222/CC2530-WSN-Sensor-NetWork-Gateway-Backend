# -*- coding: utf-8 -*-
"""MLP 机器学习 API 蓝图。

6 个端点(前缀 /api,路径 /predictions/mlp/...):
- POST /predictions/mlp/train       预训练(同步)
- POST /predictions/mlp/finetune    手动微调(异步)
- POST /predictions/mlp/evaluate    手动评估(同步)
- GET  /predictions/mlp/status      查询模型状态
- GET  /predictions/mlp/evaluations 评估历史
- GET  /predictions/mlp/models      列出所有模型

OperationLog 写入规范(修复 R1):
- ml_models 主键是字符串 model_type → 不传 target_id(BigInteger),model_type 放 detail
- ml_evaluations 有整数 id → 正常关联 target_id
- GET 请求不写日志(与现有 GET 接口一致)
"""
import json

from flask import Blueprint, g, jsonify, request

from extensions import db
from models.ml import MlModel, MlEvaluation
from models.operation_log import OperationLog
from utils.auth import jwt_required
import extensions as ext_mod

bp = Blueprint("mlp", __name__)

_VALID_MODEL_TYPES = ("mlp_temp_hum", "mlp_light")


def _get_trainer():
    """获取 ONNXTrainer 实例(torch 未装时为 None)。"""
    return getattr(ext_mod, "onnx_trainer", None)


def _get_scheduler():
    """获取 FineTuneScheduler 实例。"""
    return getattr(ext_mod, "mlp_scheduler", None)


@bp.post("/predictions/mlp/train")
@jwt_required
def mlp_train():
    """预训练模型(同步)。

    入参: {model_type: 'mlp_temp_hum'|'mlp_light', pretrain_hours?: 48}
    """
    data = request.get_json(silent=True) or {}
    model_type = data.get("model_type")
    pretrain_hours = data.get("pretrain_hours")

    if model_type not in _VALID_MODEL_TYPES:
        return jsonify({"error": f"model_type 必须为 {_VALID_MODEL_TYPES} 之一"}), 400

    trainer = _get_trainer()
    if trainer is None:
        return jsonify({"error": "MLP 模块未安装(PyTorch/onnxruntime 不可用)"}), 503

    result = trainer.pretrain(model_type, pretrain_hours=pretrain_hours)
    if "error" in result:
        return jsonify(result), 400

    # 写 OperationLog(修复 R1:不传 target_id,model_type 放 detail)
    db.session.add(OperationLog(
        user_id=g.current_user.id, action="mlp_train",
        target_type="ml_model",
        detail=json.dumps({"model_type": model_type,
                           "train_loss": result.get("train_loss")},
                          ensure_ascii=False),
    ))
    db.session.commit()
    return jsonify(result), 201


@bp.post("/predictions/mlp/finetune")
@jwt_required
def mlp_finetune():
    """手动触发微调(异步)。

    入参: {model_type: 'mlp_temp_hum'|'mlp_light'}
    """
    data = request.get_json(silent=True) or {}
    model_type = data.get("model_type")

    if model_type not in _VALID_MODEL_TYPES:
        return jsonify({"error": f"model_type 必须为 {_VALID_MODEL_TYPES} 之一"}), 400

    scheduler = _get_scheduler()
    if scheduler is None:
        return jsonify({"error": "MLP 调度器未安装"}), 503

    success, message = scheduler.manual_finetune(model_type)
    if not success:
        # 409: 已有微调进行中; 400: 模型未预训练
        code = 409 if "微调中" in message else 400
        return jsonify({"error": message}), code

    # 写 OperationLog(异步触发,日志在响应前写)
    db.session.add(OperationLog(
        user_id=g.current_user.id, action="mlp_finetune",
        target_type="ml_model",
        detail=json.dumps({"model_type": model_type}, ensure_ascii=False),
    ))
    db.session.commit()
    return jsonify({"message": message, "model_type": model_type}), 202


@bp.post("/predictions/mlp/evaluate")
@jwt_required
def mlp_evaluate():
    """手动重新评估(同步,使用最近一次微调的 eval_set 缓存)。

    入参: {model_type: 'mlp_temp_hum'|'mlp_light'}
    """
    data = request.get_json(silent=True) or {}
    model_type = data.get("model_type")

    if model_type not in _VALID_MODEL_TYPES:
        return jsonify({"error": f"model_type 必须为 {_VALID_MODEL_TYPES} 之一"}), 400

    trainer = _get_trainer()
    scheduler = _get_scheduler()
    if trainer is None or scheduler is None:
        return jsonify({"error": "MLP 模块未安装"}), 503

    # 使用微调时缓存的 eval_set(修复 F1)
    eval_set = scheduler._eval_set.get(model_type)
    result = trainer.evaluate(model_type, eval_set=eval_set)
    if "error" in result:
        return jsonify(result), 400

    # 写 OperationLog(ml_evaluations 有整数 id,可关联 target_id)
    eval_record = (MlEvaluation.query
                   .filter_by(model_type=model_type)
                   .order_by(MlEvaluation.eval_time.desc())
                   .first())
    if eval_record:
        db.session.add(OperationLog(
            user_id=g.current_user.id, action="mlp_evaluate",
            target_type="ml_evaluation", target_id=eval_record.id,
            detail=json.dumps({"model_type": model_type,
                               "winner": result.get("winner")},
                              ensure_ascii=False),
        ))
        db.session.commit()
    return jsonify(result), 200


@bp.get("/predictions/mlp/status")
@jwt_required
def mlp_status():
    """查询模型状态。

    入参 query: model_type (必填)
    """
    model_type = request.args.get("model_type")
    if model_type not in _VALID_MODEL_TYPES:
        return jsonify({"error": f"model_type 必须为 {_VALID_MODEL_TYPES} 之一"}), 400

    ml_model = MlModel.query.get(model_type)
    if not ml_model:
        return jsonify(None)
    return jsonify(ml_model.to_dict())


@bp.get("/predictions/mlp/evaluations")
@jwt_required
def mlp_evaluations():
    """评估历史列表。

    入参 query: model_type (必填), limit? (默认 20)
    """
    model_type = request.args.get("model_type")
    limit = request.args.get("limit", 20, type=int)
    limit = max(1, min(limit, 100))

    if model_type not in _VALID_MODEL_TYPES:
        return jsonify({"error": f"model_type 必须为 {_VALID_MODEL_TYPES} 之一"}), 400

    rows = (MlEvaluation.query
            .filter_by(model_type=model_type)
            .order_by(MlEvaluation.eval_time.desc())
            .limit(limit)
            .all())
    return jsonify([r.to_dict() for r in rows])


@bp.get("/predictions/mlp/models")
@jwt_required
def mlp_models():
    """列出所有 MLP 模型状态(管理面板用)。"""
    rows = MlModel.query.all()
    return jsonify([r.to_dict() for r in rows])
