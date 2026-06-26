# -*- coding: utf-8 -*-
"""订阅管理接口(管理员)。
切换某指标订阅状态 -> 更新表 -> MQTT 订阅/取消订阅 -> (可选)下发订阅配置给网关。"""
import json
import time
from datetime import datetime

from flask import Blueprint, g, jsonify, request

import extensions
from extensions import db
from models.gateway import Gateway
from models.operation_log import OperationLog
from models.subscription import Subscription
from mqtt import topics
from utils.auth import admin_required, jwt_required

bp = Blueprint("subscription", __name__)


@bp.get("/subscriptions")
@jwt_required
def list_subscriptions():
    subs = Subscription.query.all()
    return jsonify([s.to_dict() for s in subs])


@bp.patch("/subscriptions/<metric>")
@admin_required
def toggle(metric):
    if metric not in topics.METRIC_TOPICS:
        return jsonify({"error": "无效指标"}), 400
    sub = Subscription.query.filter_by(metric=metric).first()
    if not sub:
        return jsonify({"error": "订阅记录不存在"}), 404

    data = request.get_json(silent=True) or {}
    if "subscribed" in data:
        sub.subscribed = bool(data["subscribed"])
    else:
        sub.subscribed = not sub.subscribed
    sub.updated_by = g.current_user.id
    sub.updated_at = datetime.now()
    db.session.commit()

    # 切换后端 MQTT 订阅
    if sub.subscribed:
        extensions.mqtt_client.subscribe_metric(metric)
    else:
        extensions.mqtt_client.unsubscribe_metric(metric)

    # 下发订阅配置给所有已绑定网关(可选优化,网关据此停止转发)
    enabled = [s.metric for s in Subscription.query.filter_by(subscribed=True).all()]
    for gw in Gateway.query.filter(Gateway.user_id.isnot(None)).all():
        extensions.mqtt_client.publish(
            topics.subscription_topic(gw.gw_uuid),
            {"metrics": enabled, "ts": int(time.time())},
            qos=1, retain=True,
        )

    db.session.add(OperationLog(
        user_id=g.current_user.id, action="toggle_subscription",
        target_type="subscription", detail=json.dumps(
            {"metric": metric, "subscribed": sub.subscribed}, ensure_ascii=False),
    ))
    db.session.commit()
    return jsonify(sub.to_dict())
