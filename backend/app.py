# -*- coding: utf-8 -*-
"""Flask 应用工厂。

启动顺序:
1. 创建 Flask、初始化 db / socketio / CORS
2. 注册蓝图与 WebSocket 事件
3. 建表 + seed(管理员账号、5 条订阅记录)
4. 启动数据入库缓冲(10s)
5. 后台连接 EMQX 并订阅主题

运行:
  pip install -r requirements.txt
  python app.py
"""
import bcrypt
from flask import Flask, jsonify
from flask_cors import CORS

import extensions
from config import Config
from extensions import db, socketio
from models import sensor_data as sensor_data_model  # noqa: F401  注册模型
from models.user import User
from models.subscription import Subscription
from models.alert_rule import AlertRule
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
    from api import auth, gateway, device, data, subscription, operation_log, alert
    app.register_blueprint(auth.bp, url_prefix="/api/auth")
    app.register_blueprint(gateway.bp, url_prefix="/api")
    app.register_blueprint(device.bp, url_prefix="/api")
    app.register_blueprint(data.bp, url_prefix="/api")
    app.register_blueprint(subscription.bp, url_prefix="/api")
    app.register_blueprint(operation_log.bp, url_prefix="/api")
    app.register_blueprint(alert.bp, url_prefix="/api")

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
        if Config.CREATE_TABLES_ON_START:
            db.create_all()
            _seed(app)
        extensions.data_buffer.start()
        # 后台连接 EMQX(失败自动重试,不阻塞服务启动)
        extensions.mqtt_client.start()

    return app, socketio


def _seed(app):
    """预置管理员账号与 5 条订阅记录。"""
    # 管理员
    if Config.SEED_ADMIN and not User.query.filter_by(username=Config.ADMIN_USERNAME).first():
        pw_hash = bcrypt.hashpw(Config.ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        admin = User(username=Config.ADMIN_USERNAME, password_hash=pw_hash, role="admin")
        db.session.add(admin)
        print(f"[Seed] 创建管理员账号 {Config.ADMIN_USERNAME}/{Config.ADMIN_PASSWORD}")

    # 订阅记录
    for metric in ("temperature", "humidity", "light", "led_status", "device_status"):
        if not Subscription.query.filter_by(metric=metric).first():
            db.session.add(Subscription(metric=metric, subscribed=True))

    # 预置告警规则
    if not AlertRule.query.first():
        seeds = [
            AlertRule(name="高温告警", metric="temperature", operator="gt", threshold=35,
                      logic="none", severity="critical", enabled=True),
            AlertRule(name="低温告警", metric="temperature", operator="lt", threshold=10,
                      logic="none", severity="warning", enabled=True),
            AlertRule(name="高湿告警", metric="humidity", operator="gt", threshold=80,
                      logic="none", severity="warning", enabled=True),
            AlertRule(name="低湿告警", metric="humidity", operator="lt", threshold=20,
                      logic="none", severity="info", enabled=True),
            AlertRule(name="强光告警", metric="light", operator="gt", threshold=1000,
                      logic="none", severity="info", enabled=True),
            AlertRule(name="高温且低湿(危险组合)", metric="temperature", operator="gt", threshold=32,
                      logic="and", second_metric="humidity", second_operator="lt", second_threshold=30,
                      severity="critical", enabled=True),
        ]
        for r in seeds:
            db.session.add(r)
        print(f"[Seed] 创建 {len(seeds)} 条预置告警规则")

    db.session.commit()


app, socketio_inst = create_app()


if __name__ == "__main__":
    socketio_inst.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
