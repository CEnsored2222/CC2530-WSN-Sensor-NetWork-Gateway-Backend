# -*- coding: utf-8 -*-
"""Flask 应用工厂。

启动顺序:
1. 创建 Flask、初始化 db / socketio / CORS
2. 注册蓝图与 WebSocket 事件
3. 启动数据入库缓冲
4. 后台连接 EMQX 并订阅主题

运行:
  pip install -r requirements.txt
  python app.py
"""
from flask import Flask, jsonify
from flask_cors import CORS

import extensions
from config import Config
from extensions import db, socketio
from models import sensor_data as sensor_data_model  # noqa: F401  注册模型
from services.data_buffer import DataBuffer
from mqtt.client import MqttClient
from mqtt.handler import MqttHandler


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app, supports_credentials=True)

    db.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")

    # 注册蓝图
    from api import auth, gateway, device, data, subscription, operation_log, alert, prediction
    app.register_blueprint(auth.bp, url_prefix="/api/auth")
    app.register_blueprint(gateway.bp, url_prefix="/api")
    app.register_blueprint(device.bp, url_prefix="/api")
    app.register_blueprint(data.bp, url_prefix="/api")
    app.register_blueprint(subscription.bp, url_prefix="/api")
    app.register_blueprint(operation_log.bp, url_prefix="/api")
    app.register_blueprint(alert.bp, url_prefix="/api")
    app.register_blueprint(prediction.bp, url_prefix="/api")

    # 注册 WebSocket 事件
    from ws import events  # noqa: F401

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True})

    # 组件引用
    extensions.app = app
    extensions.data_buffer = DataBuffer(
        db, sensor_data_model.SensorData, app, Config.DATA_FLUSH_INTERVAL
    )

    handler = MqttHandler(app)
    extensions.mqtt_client = MqttClient(handler, app)

    with app.app_context():
        extensions.data_buffer.start()
        # 后台连接 EMQX(失败自动重试,不阻塞服务启动)
        extensions.mqtt_client.start()

    return app, socketio


app, socketio_inst = create_app()


if __name__ == "__main__":
    socketio_inst.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
