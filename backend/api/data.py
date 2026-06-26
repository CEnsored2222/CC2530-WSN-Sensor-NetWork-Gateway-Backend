# -*- coding: utf-8 -*-
"""数据接口:实时监控/历史曲线/总览统计"""
from datetime import datetime

from flask import Blueprint, g, jsonify, request

from extensions import db
from models.device import Device
from models.gateway import Gateway
from models.sensor_data import SensorData
from utils.auth import jwt_required

bp = Blueprint("data", __name__)

_VALID_METRICS = ("temperature", "humidity", "light")


@bp.get("/data/realtime")
@jwt_required
def realtime():
    """首页实时监控:每个已绑定设备 + 最新一条数据"""
    gw_ids = [gw.id for gw in Gateway.query.filter_by(user_id=g.current_user.id).all()]
    if not gw_ids:
        return jsonify({"devices": []})
    devs = Device.query.filter(Device.gateway_id.in_(gw_ids)).all()
    result = []
    for dev in devs:
        latest = (
            SensorData.query.filter_by(device_id=dev.id)
            .order_by(SensorData.recorded_at.desc())
            .first()
        )
        result.append({
            "device": dev.to_dict(),
            "latest": latest.to_dict() if latest else None,
        })
    return jsonify({"devices": result})


@bp.get("/data/history")
@jwt_required
def history():
    """历史曲线:按设备+指标+时间范围查询"""
    device_id = request.args.get("device_id", type=int)
    metric = request.args.get("metric")
    start = request.args.get("start")
    end = request.args.get("end")

    if not device_id or metric not in _VALID_METRICS:
        return jsonify({"error": "参数错误(device_id + metric 必填,metric ∈ temperature/humidity/light)"}), 400

    dev = db.session.get(Device, device_id)
    if not dev or dev.gateway.user_id != g.current_user.id:
        return jsonify({"error": "设备不存在"}), 404

    q = SensorData.query.filter_by(device_id=device_id)
    if start:
        try:
            q = q.filter(SensorData.recorded_at >= datetime.fromisoformat(start))
        except ValueError:
            return jsonify({"error": "start 格式错误(用 ISO 日期)"}), 400
    if end:
        try:
            q = q.filter(SensorData.recorded_at <= datetime.fromisoformat(end))
        except ValueError:
            return jsonify({"error": "end 格式错误(用 ISO 日期)"}), 400

    rows = q.order_by(SensorData.recorded_at.asc()).all()
    return jsonify([
        {"t": r.recorded_at.strftime("%Y-%m-%d %H:%M:%S"), "v": float(getattr(r, metric)) if getattr(r, metric) is not None else None}
        for r in rows
    ])


@bp.get("/data/overview")
@jwt_required
def overview():
    """总览统计:网关数/设备数/在线设备"""
    gws = Gateway.query.filter_by(user_id=g.current_user.id).all()
    gw_ids = [gw.id for gw in gws]
    devs = Device.query.filter(Device.gateway_id.in_(gw_ids)).all() if gw_ids else []
    bound = [d for d in devs if d.bound]
    return jsonify({
        "gateway_count": len(gws),
        "device_count": len(devs),
        "bound_device_count": len(bound),
        "gateways": [gw.to_dict() for gw in gws],
    })
