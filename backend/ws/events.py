# -*- coding: utf-8 -*-
"""WebSocket 事件处理。

客户端连接后发送 join 事件携带 token,服务端校验后加入用户私有房间
user_{user_id}。MQTT 处理器据此房间推送 sensor_data / gateway_pending /
device_discovered / cmd_feedback 事件。
"""
from flask_socketio import join_room

from extensions import socketio
from utils.auth import decode_token


@socketio.on("join")
def on_join(data):
    if not isinstance(data, dict):
        return {"error": "invalid payload"}
    token = data.get("token")
    if not token:
        return {"error": "no token"}
    payload = decode_token(token)
    if not payload:
        return {"error": "invalid token"}
    user_id = payload.get("user_id")
    join_room(f"user_{user_id}")
    return {"ok": True, "user_id": user_id}


@socketio.on("disconnect")
def on_disconnect():
    pass
