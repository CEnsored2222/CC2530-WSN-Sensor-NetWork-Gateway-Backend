# -*- coding: utf-8 -*-
"""ONNXTrainer 训练端到端测试(假数据 + 真实 torch/onnxruntime)。

覆盖:
- pretrain: 从 DB 假数据预训练 → 生成模型文件 + 更新 ml_models 表
- predict: 预训练后推理 → 验证返回结构(6步预测 + history_snapshot)
- _get_device_ids: 按 model_type 过滤设备
- 数据不足时 pretrain 返回 error
"""
import os
from datetime import datetime, timedelta

import pytest

from extensions import db
from models.ml import MlModel
from models.sensor_data import SensorData


class TestGetDeviceIds:
    """_get_device_ids 按 model_type 过滤设备(Python 端过滤,修复 F7)。"""

    def test_temp_hum_finds_devices_with_temp_or_humidity(self, app, sample_data):
        with app.app_context():
            trainer = _make_trainer(app)
            ids = trainer._get_device_ids("mlp_temp_hum")
            assert sample_data["device_temp_hum_id"] in ids
            # 光照设备不应出现
            assert sample_data["device_light_id"] not in ids

    def test_light_finds_devices_with_light(self, app, sample_data):
        with app.app_context():
            trainer = _make_trainer(app)
            ids = trainer._get_device_ids("mlp_light")
            assert sample_data["device_light_id"] in ids
            assert sample_data["device_temp_hum_id"] not in ids

    def test_returns_empty_when_no_matching_device(self, app):
        with app.app_context():
            trainer = _make_trainer(app)
            assert trainer._get_device_ids("mlp_temp_hum") == []


class TestPretrain:
    """pretrain 端到端: 假数据 → 训练 → 文件 + DB。"""

    def test_pretrain_temp_hum_success(self, app, sample_data, trainer):
        with app.app_context():
            result = trainer.pretrain("mlp_temp_hum")

            assert "error" not in result
            assert result["model_type"] == "mlp_temp_hum"
            assert result["num_samples"] >= 12  # MLP_MIN_SAMPLES
            assert result["train_loss"] >= 0
            assert result["val_loss"] is not None or result["val_loss"] is None

            # 验证 ml_models 表更新(UPSERT)
            ml_model = MlModel.query.get("mlp_temp_hum")
            assert ml_model is not None
            assert ml_model.last_train_time is not None
            assert ml_model.num_samples_trained == result["num_samples"]
            assert ml_model.last_finetune_time is None  # 预训练重置微调时间

            # 验证模型文件生成
            d = trainer._model_dir("mlp_temp_hum")
            assert os.path.exists(os.path.join(d, "model.pt"))
            assert os.path.exists(os.path.join(d, "model.onnx"))
            assert os.path.exists(os.path.join(d, "scaler.json"))

    def test_pretrain_light_success(self, app, sample_data, trainer):
        with app.app_context():
            result = trainer.pretrain("mlp_light")

            assert "error" not in result
            assert result["model_type"] == "mlp_light"
            assert result["num_samples"] >= 12

            ml_model = MlModel.query.get("mlp_light")
            assert ml_model is not None
            assert ml_model.num_samples_trained == result["num_samples"]

            d = trainer._model_dir("mlp_light")
            assert os.path.exists(os.path.join(d, "model.onnx"))

    def test_pretrain_no_device_returns_error(self, app, trainer):
        """无对应设备 → error。"""
        with app.app_context():
            result = trainer.pretrain("mlp_temp_hum")
            assert "error" in result
            assert "未找到" in result["error"]

    def test_pretrain_insufficient_data_returns_error(self, app, trainer):
        """数据不足 MLP_MIN_SAMPLES → error。"""
        with app.app_context():
            # 插入 1 个设备但只有 5 条数据(< 12)
            from models.gateway import Gateway
            from models.device import Device
            gw = Gateway(gw_uuid="gw-sparse", status="approved")
            db.session.add(gw)
            db.session.flush()
            dev = Device(gateway_id=gw.id, mac="SPARSE",
                         type=["temperature", "humidity"], bound=True)
            db.session.add(dev)
            db.session.flush()
            now = datetime.now()
            for i in range(5):
                db.session.add(SensorData(
                    device_id=dev.id, temperature=25.0, humidity=60.0,
                    recorded_at=now - timedelta(hours=5 - i),
                ))
            db.session.commit()

            result = trainer.pretrain("mlp_temp_hum")
            assert "error" in result
            assert "不足" in result["error"]


class TestPredict:
    """predict 推理: 预训练后递归多步预测(6步)。"""

    def test_predict_after_pretrain(self, app, sample_data, trainer):
        with app.app_context():
            # 先预训练
            trainer.pretrain("mlp_temp_hum")

            # 拉取最近数据作为推理输入(模拟 prediction.py 的调用)
            dev_id = sample_data["device_temp_hum_id"]
            rows = (SensorData.query
                    .filter_by(device_id=dev_id)
                    .order_by(SensorData.recorded_at)
                    .all())
            row_dicts = [{"recorded_at": r.recorded_at,
                          "temperature": float(r.temperature) if r.temperature else 0,
                          "humidity": float(r.humidity) if r.humidity else 0,
                          "light": r.light} for r in rows]

            result = trainer.predict("mlp_temp_hum", row_dicts)

            # 验证返回结构: {metric: {predicted_values, history_snapshot}}
            assert "temperature" in result
            assert "humidity" in result

            for metric in ("temperature", "humidity"):
                pv = result[metric]["predicted_values"]
                # 6 步预测
                assert len(pv) == 6
                # 键格式 t+10, t+20, ..., t+60
                expected_keys = {f"t+{s}" for s in (10, 20, 30, 40, 50, 60)}
                assert set(pv.keys()) == expected_keys
                # 预测值是数字
                for v in pv.values():
                    assert isinstance(v, (int, float))

                # history_snapshot 有 times + values + metric
                hs = result[metric]["history_snapshot"]
                assert "times" in hs
                assert "values" in hs
                assert hs["metric"] == metric
                # times 包含历史 + 预测(带 * 标记)
                assert len(hs["times"]) > 0

    def test_predict_empty_rows_returns_error(self, app, trainer):
        with app.app_context():
            result = trainer.predict("mlp_temp_hum", [])
            assert "error" in result

    def test_predict_light_after_pretrain(self, app, sample_data, trainer):
        with app.app_context():
            trainer.pretrain("mlp_light")

            dev_id = sample_data["device_light_id"]
            rows = (SensorData.query
                    .filter_by(device_id=dev_id)
                    .order_by(SensorData.recorded_at)
                    .all())
            row_dicts = [{"recorded_at": r.recorded_at,
                          "temperature": None, "humidity": None,
                          "light": r.light} for r in rows]

            result = trainer.predict("mlp_light", row_dicts)

            assert "light" in result
            pv = result["light"]["predicted_values"]
            assert len(pv) == 6
            assert set(pv.keys()) == {f"t+{s}" for s in (10, 20, 30, 40, 50, 60)}


class TestPretrainTwice:
    """二次预训练产生 prev 文件(验证原子写入的 prev 退位)。"""

    def test_second_pretrain_creates_prev(self, app, sample_data, trainer):
        with app.app_context():
            trainer.pretrain("mlp_temp_hum")
            trainer.pretrain("mlp_temp_hum")

            d = trainer._model_dir("mlp_temp_hum")
            assert os.path.exists(os.path.join(d, "model_prev.onnx"))
            assert os.path.exists(os.path.join(d, "model_prev.pt"))
            assert os.path.exists(os.path.join(d, "scaler_prev.json"))


# 辅助:创建 trainer(用于不依赖 trainer fixture 的测试类)
def _make_trainer(app):
    from ml.onnx_trainer import ONNXTrainer
    return ONNXTrainer(app)
