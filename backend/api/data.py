# -*- coding: utf-8 -*-
"""数据接口:实时监控/历史曲线/总览统计"""
from datetime import datetime

import extensions
from flask import Blueprint, g, jsonify, request

from extensions import db
from models.device import Device
from models.gateway import Gateway
from models.sensor_data import SensorData
from utils.auth import jwt_required
from utils.gateway_permission import get_user_gateway_ids, check_user_bound_to_gateway

bp = Blueprint("data", __name__)

_VALID_METRICS = ("temperature", "humidity", "light")


@bp.get("/data/realtime")
@jwt_required
def realtime():
    """首页实时监控:每个已绑定设备 + 最新数据。

    采集字段(温度/湿度/光照)优先取 data_buffer 实时缓冲,缓冲为空时回退数据库历史表;
    状态字段(led_status/device_status)仅从 data_buffer 取(不入库,由 MQTT led/status
    主题订阅直推)。保证与设备管理页面的状态数据源完全一致。
    """
    gw_ids = get_user_gateway_ids(g.current_user.id)
    if not gw_ids:
        return jsonify({"devices": []})
    devs = Device.query.filter(Device.gateway_id.in_(gw_ids)).all()
    result = []
    for dev in devs:
        buf = extensions.data_buffer.get_latest(dev.id)
        latest_db = (
            SensorData.query.filter_by(device_id=dev.id)
            .order_by(SensorData.recorded_at.desc())
            .first()
        )
        # 采集字段:buffer 优先,回退数据库
        temp = buf.get("temperature")
        hum = buf.get("humidity")
        light = buf.get("light")
        if temp is None and hum is None and light is None and latest_db:
            temp = float(latest_db.temperature) if latest_db.temperature is not None else None
            hum = float(latest_db.humidity) if latest_db.humidity is not None else None
            light = latest_db.light
            recorded_at = latest_db.recorded_at.strftime("%Y-%m-%d %H:%M:%S") if latest_db.recorded_at else None
        else:
            ts = buf.get("_ts")
            recorded_at = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else None

        latest = {
            "device_id": dev.id,
            "temperature": temp,
            "humidity": hum,
            "light": light,
            # 状态字段仅来自 buffer(不入库,由 led/status 主题直推)
            "led_status": buf.get("led_status"),
            "device_status": buf.get("device_status"),
            "recorded_at": recorded_at,
        }
        result.append({
            "device": dev.to_dict(),
            "latest": latest,
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
    if not dev or not check_user_bound_to_gateway(g.current_user.id, dev.gateway_id):
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
    gw_ids = get_user_gateway_ids(g.current_user.id)
    gws = [db.session.get(Gateway, gid) for gid in gw_ids]
    gws = [gw for gw in gws if gw is not None]
    devs = Device.query.filter(Device.gateway_id.in_(gw_ids)).all() if gw_ids else []
    bound = [d for d in devs if d.bound]
    return jsonify({
        "gateway_count": len(gws),
        "device_count": len(devs),
        "bound_device_count": len(bound),
        "gateways": [gw.to_dict() for gw in gws],
    })
