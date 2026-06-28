# -*- coding: utf-8 -*-
"""设备接口:列表/绑定命名/数据流(5条)/下发控制"""
import json
import time

from flask import Blueprint, g, jsonify, request

import extensions
from extensions import db
from models.device import Device
from models.gateway import Gateway
from models.operation_log import OperationLog
from models.sensor_data import SensorData
from mqtt import topics
from utils.auth import jwt_required
from utils.gateway_permission import check_user_bound_to_gateway

bp = Blueprint("device", __name__)

_IP = lambda: request.remote_addr or ""


def _device_owned(dev):
    """检查设备是否属于当前用户(通过 user_gateways 中间表)。

    设备所属的网关必须已被当前用户绑定。
    """
    if dev is None:
        return False
    gw_id = dev.gateway_id if hasattr(dev, 'gateway_id') else (
        dev.gateway.id if dev.gateway else None
    )
    if gw_id is None:
        return False
    return check_user_bound_to_gateway(g.current_user.id, gw_id)


@bp.get("/gateways/<int:gw_id>/devices")
@jwt_required
def list_devices(gw_id):
    gw = db.session.get(Gateway, gw_id)
    if not gw or not check_user_bound_to_gateway(g.current_user.id, gw_id):
        return jsonify({"error": "网关不存在"}), 404
    devs = Device.query.filter_by(gateway_id=gw_id).all()
    result = []
    for d in devs:
        item = d.to_dict()
        # 附带最新读数(用于前端按钮状态)
        latest = extensions.data_buffer.get_latest(d.id)
        item["led_status"] = latest.get("led_status")
        item["device_status"] = latest.get("device_status")
        result.append(item)
    return jsonify(result)


@bp.patch("/devices/<int:did>")
@jwt_required
def bind_device(did):
    dev = db.session.get(Device, did)
    if not _device_owned(dev):
        return jsonify({"error": "设备不存在"}), 404
    data = request.get_json(silent=True) or {}
    dev.name = data.get("name", dev.name)
    # type 现在是 JSON 数组,如 ["temperature","humidity"];允许手动覆盖
    if "type" in data:
        t = data["type"]
        dev.type = t if isinstance(t, list) else dev.type
    dev.bound = True
    db.session.commit()
    db.session.add(OperationLog(
        user_id=g.current_user.id, action="bind_device",
        target_type="device", target_id=dev.id,
        detail=json.dumps({"name": dev.name}, ensure_ascii=False),
        ip=_IP(),
    ))
    db.session.commit()
    return jsonify(dev.to_dict())


@bp.get("/devices/<int:did>/stream")
@jwt_required
def device_stream(did):
    dev = db.session.get(Device, did)
    if not _device_owned(dev):
        return jsonify({"error": "设备不存在"}), 404
    records = (
        SensorData.query.filter_by(device_id=did)
        .order_by(SensorData.recorded_at.desc())
        .limit(5)
        .all()
    )
    records.reverse()  # 时间升序展示
    return jsonify([r.to_dict() for r in records])


@bp.post("/devices/<int:did>/cmd")
@jwt_required
def cmd(did):
    dev = db.session.get(Device, did)
    if not _device_owned(dev):
        return jsonify({"error": "设备不存在"}), 404
    data = request.get_json(silent=True) or {}
    cmd_name = data.get("cmd")
    value = data.get("value")
    if cmd_name not in ("LED", "STATUS"):
        return jsonify({"error": "无效指令,仅支持 LED/STATUS"}), 400
    try:
        value = int(value)
    except (TypeError, ValueError):
        return jsonify({"error": "value 必须为整数"}), 400

    topic = topics.cmd_topic(dev.gateway.gw_uuid, dev.mac)
    extensions.mqtt_client.publish(
        topic, {"cmd": cmd_name, "value": value, "ts": int(time.time())}, qos=1,
    )
    db.session.add(OperationLog(
        user_id=g.current_user.id, action="device_cmd",
        target_type="device", target_id=dev.id,
        detail=json.dumps({"cmd": cmd_name, "value": value}, ensure_ascii=False),
        ip=_IP(),
    ))
    db.session.commit()
    return jsonify({"ok": True, "cmd": cmd_name, "value": value})
