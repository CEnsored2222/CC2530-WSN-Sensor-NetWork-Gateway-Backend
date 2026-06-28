# -*- coding: utf-8 -*-
"""网关接口:待审列表/我的网关/全部网关列表/审批/拒绝/绑定/解绑"""
import json
import time
from datetime import datetime

from flask import Blueprint, g, jsonify, request

import extensions
from extensions import db
from models.gateway import Gateway
from models.user_gateway import UserGateway
from models.device import Device
from models.sensor_data import SensorData
from models.operation_log import OperationLog
from mqtt import topics
from utils.auth import jwt_required
from utils.gateway_permission import check_user_bound_to_gateway

bp = Blueprint("gateway", __name__)

_IP = lambda: request.remote_addr or ""


@bp.get("/gateways/pending")
@jwt_required
def pending():
    """待审网关列表("寻找"按钮中 pending 状态展示)"""
    gws = Gateway.query.filter_by(status="pending").all()
    return jsonify([gw.to_dict() for gw in gws])


@bp.get("/gateways")
@jwt_required
def list_gateways():
    """当前用户已绑定的网关列表(通过 user_gateways 中间表查询)"""
    ugs = UserGateway.query.filter_by(user_id=g.current_user.id).all()
    gws = [Gateway.query.get(ug.gateway_id) for ug in ugs if Gateway.query.get(ug.gateway_id)]
    result = []
    for gw in gws:
        d = gw.to_dict()
        # 附带用户在中间表中的自定义名称
        ug = next((u for u in ugs if u.gateway_id == gw.id), None)
        d["name"] = ug.name if ug else None
        result.append(d)
    return jsonify(result)


@bp.get("/gateways/all")
@jwt_required
def list_all_gateways():
    """全部网关列表(含当前用户的绑定状态)。

    返回每个网关的基本信息 + bound(是否已绑定) + bind_name(用户自定义名称)。
    """
    gws = Gateway.query.all()
    # 查询当前用户的所有绑定记录
    ug_map = {
        ug.gateway_id: ug
        for ug in UserGateway.query.filter_by(user_id=g.current_user.id).all()
    }
    result = []
    for gw in gws:
        d = gw.to_dict()
        ug = ug_map.get(gw.id)
        d["bound"] = ug is not None
        d["bind_name"] = ug.name if ug else None
        result.append(d)
    return jsonify(result)


@bp.post("/gateways/<gw_uuid>/approve")
@jwt_required
def approve(gw_uuid):
    """审批通过网关(仅改变网关状态,不再绑定用户)。

    任意用户审批通过后,网关变为 approved,之后所有用户均可绑定。
    """
    gw = Gateway.query.filter_by(gw_uuid=gw_uuid).first()
    if not gw:
        return jsonify({"error": "网关不存在"}), 404
    if gw.status != "pending":
        return jsonify({"error": "网关状态不是待审"}), 400

    gw.status = "approved"
    db.session.commit()

    # 下发审批结果给网关
    extensions.mqtt_client.publish(
        topics.register_resp_topic(gw_uuid),
        {"gw_uuid": gw_uuid, "result": "approved", "ts": int(time.time())},
        qos=1,
    )

    db.session.add(OperationLog(
        user_id=g.current_user.id, action="approve_gateway",
        target_type="gateway", target_id=gw.id,
        detail=json.dumps({"gw_uuid": gw_uuid}, ensure_ascii=False),
        ip=_IP(),
    ))
    db.session.commit()
    return jsonify(gw.to_dict())


@bp.post("/gateways/<gw_uuid>/bind")
@jwt_required
def bind_gateway(gw_uuid):
    """用户绑定网关(在 user_gateways 中间表创建记录)。

    要求网关状态为 approved 或 online。
    """
    gw = Gateway.query.filter_by(gw_uuid=gw_uuid).first()
    if not gw:
        return jsonify({"error": "网关不存在"}), 404
    if gw.status not in ("approved", "online"):
        return jsonify({"error": "网关未被审批通过,无法绑定"}), 400

    existing = UserGateway.query.filter_by(
        user_id=g.current_user.id, gateway_id=gw.id
    ).first()
    if existing:
        return jsonify({"error": "您已绑定此网关"}), 409

    data = request.get_json(silent=True) or {}
    name = data.get("name") or gw.hostname

    ug = UserGateway(
        user_id=g.current_user.id,
        gateway_id=gw.id,
        name=name,
    )
    db.session.add(ug)
    db.session.commit()

    db.session.add(OperationLog(
        user_id=g.current_user.id, action="bind_gateway",
        target_type="gateway", target_id=gw.id,
        detail=json.dumps({"gw_uuid": gw_uuid, "name": name}, ensure_ascii=False),
        ip=_IP(),
    ))
    db.session.commit()

    return jsonify({"ok": True, "gateway": gw.to_dict()})


@bp.post("/gateways/<gw_uuid>/reject")
@jwt_required
def reject(gw_uuid):
    """拒绝网关接入"""
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
    """解绑网关(仅删除当前用户的 user_gateways 记录)。

    其他用户的绑定关系不受影响,设备数据不删除,网关状态不变。
    """
    gw = db.session.get(Gateway, gid)
    if not gw:
        return jsonify({"error": "网关不存在"}), 404

    ug = UserGateway.query.filter_by(
        user_id=g.current_user.id, gateway_id=gid
    ).first()
    if not ug:
        return jsonify({"error": "您未绑定此网关"}), 404

    db.session.delete(ug)
    db.session.commit()

    db.session.add(OperationLog(
        user_id=g.current_user.id, action="unbind_gateway",
        target_type="gateway", target_id=gw.id,
        detail=json.dumps({"gw_uuid": gw.gw_uuid}, ensure_ascii=False),
        ip=_IP(),
    ))
    db.session.commit()
    return jsonify({"ok": True})
