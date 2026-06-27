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
from models import ml as ml_model  # noqa: F401  注册 MLP 模型
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

    # ----- 新增: MLP 蓝图注册(延迟导入 + 容错)-----
    try:
        from api import mlp
        app.register_blueprint(mlp.bp, url_prefix="/api")
    except ImportError:
        print("[MLP] onnxruntime 未安装,跳过 MLP API 蓝图")

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

    # ----- 新增: MLP 调度器初始化(延迟导入 + PyTorch 未装容错)-----
    try:
        from ml.onnx_trainer import ONNXTrainer
        from ml.scheduler import FineTuneScheduler
        extensions.onnx_trainer = ONNXTrainer(app)
        extensions.mlp_scheduler = FineTuneScheduler(app, extensions.onnx_trainer)
    except ImportError:
        print("[MLP] PyTorch/onnxruntime 未安装,跳过 MLP 调度器")

    handler = MqttHandler(app)
    extensions.mqtt_client = MqttClient(handler, app)

    with app.app_context():
        extensions.data_buffer.start()
        # 后台连接 EMQX(失败自动重试,不阻塞服务启动)
        extensions.mqtt_client.start()
        # MLP: 启动调度器 + 恢复未完成的原子写入
        if hasattr(extensions, "mlp_scheduler"):
            for mt in ("mlp_temp_hum", "mlp_light"):
                try:
                    extensions.onnx_trainer._recover_tmp_files(mt)
                except Exception:
                    pass  # 目录不存在时忽略
            extensions.mlp_scheduler.start()
            print("[MLP] 调度器已启动")

    return app, socketio


app, socketio_inst = create_app()


if __name__ == "__main__":
    socketio_inst.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
