# -*- coding: utf-8 -*-
"""WebSocket 事件处理。

客户端连接后发送 join 事件携带 token,服务端校验后加入用户私有房间
user_{user_id}。MQTT 处理器据此房间推送 sensor_data / gateway_pending /
device_discovered 事件。

注:cmd_feedback 事件已删除,指令反馈由本地网关解析后通过 led/status 主题上报,
前端通过监听 sensor_data 中的 led_status/device_status 变化来判断指令成败。
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
