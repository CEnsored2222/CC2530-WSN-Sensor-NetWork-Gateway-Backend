# -*- coding: utf-8 -*-
"""pytest 全局 fixtures。

测试策略:
- 用 SQLite 内存库,不污染远程 MySQL
- 自建最小 Flask app(不启动 MQTT/调度器),注册 mlp 蓝图
- monkeypatch JWT 认证,跳过 token 校验
- MLP_MODELS_DIR 指向临时目录,避免污染真实模型文件

运行: cd backend; python -m pytest tests/ -v
"""
import os
import sys

# 把 backend/ 加入 sys.path(测试从任意目录运行均可)
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pytest
from flask import Flask
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

from extensions import db as _db
import extensions as ext_mod

# 导入所有模型,确保 SQLAlchemy 元数据注册
from models import (  # noqa: F401
    User, Gateway, Device, SensorData, Subscription,
    OperationLog, MlModel, MlEvaluation,
)


# SQLite 兼容: BigInteger 在 SQLite 下编译为 INTEGER,
# 使 BIGINT PRIMARY KEY 也能自增(SQLite 只有 INTEGER PRIMARY KEY 是 ROWID 别名)
@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def app(tmp_path, monkeypatch):
    """测试用 Flask app (SQLite 内存库, 不启动 MQTT/调度器)。"""
    # 覆盖 MLP_MODELS_DIR 到临时目录,避免污染真实模型文件
    from config import Config
    monkeypatch.setattr(Config, "MLP_MODELS_DIR", str(tmp_path / "mlp_models"))

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["TESTING"] = True

    _db.init_app(app)

    # 注册 mlp 蓝图
    from api.mlp import bp as mlp_bp
    app.register_blueprint(mlp_bp, url_prefix="/api")

    # 清理 extensions 单例(避免上次测试残留)
    for attr in ("onnx_trainer", "mlp_scheduler", "data_buffer", "mqtt_client"):
        if hasattr(ext_mod, attr):
            delattr(ext_mod, attr)

    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    """Flask test client。"""
    return app.test_client()


@pytest.fixture(autouse=True)
def _mock_auth(monkeypatch):
    """跳过 JWT 认证(所有测试自动生效,仅 patch utils.auth 模块)。"""
    from utils import auth

    class _FakeUser:
        id = 1
        role = "admin"
        username = "test_admin"

    def _fake_extract():
        return _FakeUser(), None

    monkeypatch.setattr(auth, "_extract_user", _fake_extract)


@pytest.fixture
def sample_data(app):
    """插入假数据: 1 gateway + 2 device + 48h sensor_data(每30min一条,共96条/设备)。

    Returns:
        dict: {gateway_id, device_temp_hum_id, device_light_id}
    """
    from datetime import datetime, timedelta

    with app.app_context():
        gw = Gateway(gw_uuid="test-gw-001", status="approved", name="测试网关")
        _db.session.add(gw)
        _db.session.flush()  # 获取 gw.id

        dev_th = Device(
            gateway_id=gw.id, mac="AA:BB:CC:DD:EE:01",
            name="温湿度传感器", type=["temperature", "humidity"], bound=True,
        )
        dev_lt = Device(
            gateway_id=gw.id, mac="AA:BB:CC:DD:EE:02",
            name="光照传感器", type=["light"], bound=True,
        )
        _db.session.add_all([dev_th, dev_lt])
        _db.session.flush()

        # 48h 假数据,每 30min 一条 → 96 条/设备(远超 MLP_MIN_SAMPLES=12)
        now = datetime.now()
        for i in range(96):
            t = now - timedelta(hours=48 - i * 0.5)
            # 温湿度: 温度 20-30°C 周期波动, 湿度 50-70% 周期波动
            temp = 25.0 + 5.0 * (i % 10) * 0.1
            hum = 60.0 + 5.0 * (i % 8) * 0.1
            _db.session.add(SensorData(
                device_id=dev_th.id,
                temperature=round(temp, 2),
                humidity=round(hum, 2),
                recorded_at=t,
            ))
            # 光照: 200-500 周期波动
            light = 300 + (i % 20) * 10
            _db.session.add(SensorData(
                device_id=dev_lt.id,
                light=light,
                recorded_at=t,
            ))
        _db.session.commit()

        return {
            "gateway_id": gw.id,
            "device_temp_hum_id": dev_th.id,
            "device_light_id": dev_lt.id,
        }


@pytest.fixture
def trainer(app):
    """真实 ONNXTrainer 实例(MLP_MODELS_DIR 已指向临时目录)。

    同时注入 extensions.onnx_trainer,供 API 的 _get_trainer() 使用。
    """
    from ml.onnx_trainer import ONNXTrainer
    ext_mod.onnx_trainer = ONNXTrainer(app)
    return ext_mod.onnx_trainer


@pytest.fixture
def mock_scheduler(app):
    """mock FineTuneScheduler(避免启动真实后台线程)。"""
    class _FakeScheduler:
        def __init__(self):
            self._eval_set = {}

        def manual_finetune(self, model_type):
            return True, "微调已触发"

    ext_mod.mlp_scheduler = _FakeScheduler()
    return ext_mod.mlp_scheduler
