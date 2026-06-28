# -*- coding: utf-8 -*-
"""网关接口:待审列表/我的网关/审批/拒绝/解绑"""
import json
import time
from datetime import datetime

from flask import Blueprint, g, jsonify, request

import extensions
from extensions import db
from models.gateway import Gateway
from models.device import Device
from models.sensor_data import SensorData
from models.operation_log import OperationLog
from mqtt import topics
from utils.auth import jwt_required

bp = Blueprint("gateway", __name__)


_IP = lambda: request.remote_addr or ""


@bp.get("/gateways/pending")
@jwt_required
def pending():
    """待审网关列表("寻找"按钮)"""
    gws = Gateway.query.filter_by(status="pending").all()
    return jsonify([gw.to_dict() for gw in gws])


@bp.get("/gateways")
@jwt_required
def list_gateways():
    gws = Gateway.query.filter_by(user_id=g.current_user.id).all()
    return jsonify([gw.to_dict() for gw in gws])


@bp.post("/gateways/<gw_uuid>/approve")
@jwt_required
def approve(gw_uuid):
    gw = Gateway.query.filter_by(gw_uuid=gw_uuid).first()
    if not gw:
        return jsonify({"error": "网关不存在"}), 404
    if gw.user_id is not None and gw.user_id != g.current_user.id:
        return jsonify({"error": "网关已被其他用户绑定"}), 409

    data = request.get_json(silent=True) or {}
    gw.user_id = g.current_user.id
    gw.status = "approved"
    gw.name = data.get("name") or gw.name
    gw.approved_at = datetime.now()
    db.session.commit()

    # 下发审批结果给网关
    extensions.mqtt_client.publish(
        topics.register_resp_topic(gw_uuid),
        {"gw_uuid": gw_uuid, "result": "approved", "user_id": gw.user_id, "ts": int(time.time())},
        qos=1,
    )

    db.session.add(OperationLog(
        user_id=g.current_user.id, action="approve_gateway",
        target_type="gateway", target_id=gw.id,
        detail=json.dumps({"name": gw.name}, ensure_ascii=False),
        ip=_IP(),
    ))
    db.session.commit()
    return jsonify(gw.to_dict())


@bp.post("/gateways/<gw_uuid>/reject")
@jwt_required
def reject(gw_uuid):
    gw = Gateway.query.filter_by(gw_uuid=gw_uuid).first()
    if not gw:
        return jsonify({"error": "网关不存在"}), 404
    gw.status = "rejected"
    db.session.commit()

    extensions.mqtt_client.publish(
        topics.register_resp_topic(gw_uuid),
        {"gw_uuid": gw_uuid, "result": "rejected", "ts": int(time.time())},
        qos=1,
    )
    db.session.add(OperationLog(
        user_id=g.current_user.id, action="reject_gateway",
        target_type="gateway", target_id=gw.id,
        detail=json.dumps({"gw_uuid": gw_uuid}, ensure_ascii=False),
        ip=_IP(),
    ))
    db.session.commit()
    return jsonify({"ok": True})


@bp.delete("/gateways/<int:gid>")
@jwt_required
def unbind(gid):
    gw = db.session.get(Gateway, gid)
    if not gw or gw.user_id != g.current_user.id:
        return jsonify({"error": "网关不存在"}), 404

    # 收集设备 ID,用于清除缓冲
    dev_ids = [d.id for d in Device.query.filter_by(gateway_id=gw.id).all()]

    # 删除设备历史数据与设备记录
    if dev_ids:
        SensorData.query.filter(SensorData.device_id.in_(dev_ids)).delete(synchronize_session=False)
        Device.query.filter_by(gateway_id=gw.id).delete(synchronize_session=False)
    # 清除数据缓冲
    if extensions.data_buffer:
        for did in dev_ids:
            extensions.data_buffer.clear(did)

    gw.user_id = None
    gw.status = "offline"
    gw.approved_at = None
    db.session.commit()

    # 通知网关撤销审批,停止业务数据转发
    extensions.mqtt_client.publish(
        topics.register_resp_topic(gw.gw_uuid),
        {"gw_uuid": gw.gw_uuid, "result": "revoked", "ts": int(time.time())},
        qos=1,
    )

    db.session.add(OperationLog(
        user_id=g.current_user.id, action="unbind_gateway",
        target_type="gateway", target_id=gw.id,
        detail=json.dumps({"gw_uuid": gw.gw_uuid}, ensure_ascii=False),
        ip=_IP(),
    ))
    db.session.commit()
    return jsonify({"ok": True})
