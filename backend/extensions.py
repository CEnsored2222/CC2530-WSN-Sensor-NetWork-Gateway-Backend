# -*- coding: utf-8 -*-
"""扩展单例。
db / socketio 在 create_app 中 init_app;
mqtt_client / data_buffer / app 在 create_app 中赋值,供 API 与 MQTT 线程使用。"""
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

db = SQLAlchemy()
socketio = SocketIO(async_mode="threading", cors_allowed_origins="*")

# 以下在 create_app 中赋值
mqtt_client = None      # MqttClient 实例
data_buffer = None      # DataBuffer 实例
app = None              # Flask app 引用
