# -*- coding: utf-8 -*-
"""MLP API 集成测试(Flask test client + SQLite 内存库)。

覆盖 6 个端点的参数校验、空表响应、认证跳过。
真实训练测试在 test_onnx_trainer_train.py 中(直接调用 trainer,不走 HTTP)。
"""
from datetime import datetime

from extensions import db
from models.ml import MlModel, MlEvaluation


class TestStatusEndpoint:
    """GET /api/predictions/mlp/status。"""

    def test_missing_model_type_returns_400(self, client):
        resp = client.get("/api/predictions/mlp/status")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_invalid_model_type_returns_400(self, client):
        resp = client.get("/api/predictions/mlp/status?model_type=invalid")
        assert resp.status_code == 400

    def test_valid_but_no_data_returns_null(self, client):
        resp = client.get("/api/predictions/mlp/status?model_type=mlp_temp_hum")
        assert resp.status_code == 200
        assert resp.get_json() is None

    def test_returns_model_dict_when_exists(self, app, client):
        with app.app_context():
            m = MlModel(model_type="mlp_temp_hum",
                        last_train_time=datetime(2026, 6, 27, 12, 0, 0),
                        num_samples_trained=100, train_loss=0.1, val_loss=0.2)
            db.session.add(m)
            db.session.commit()

        resp = client.get("/api/predictions/mlp/status?model_type=mlp_temp_hum")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["model_type"] == "mlp_temp_hum"
        assert data["num_samples_trained"] == 100
        assert data["last_train_time"] == "2026-06-27 12:00:00"


class TestEvaluationsEndpoint:
    """GET /api/predictions/mlp/evaluations。"""

    def test_empty_returns_empty_list(self, client):
        resp = client.get("/api/predictions/mlp/evaluations?model_type=mlp_temp_hum")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_invalid_model_type_returns_400(self, client):
        resp = client.get("/api/predictions/mlp/evaluations?model_type=bad")
        assert resp.status_code == 400

    def test_returns_list_ordered_by_time_desc(self, app, client):
        with app.app_context():
            for i in range(3):
                db.session.add(MlEvaluation(
                    model_type="mlp_light", winner="new",
                    eval_time=datetime(2026, 6, 27, 10 + i, 0, 0),
                ))
            db.session.commit()

        resp = client.get("/api/predictions/mlp/evaluations?model_type=mlp_light")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 3
        # 倒序(最新在前)
        assert data[0]["eval_time"] >= data[1]["eval_time"]

    def test_limit_parameter(self, app, client):
        with app.app_context():
            for i in range(5):
                db.session.add(MlEvaluation(model_type="mlp_temp_hum", winner="new"))
            db.session.commit()

        resp = client.get("/api/predictions/mlp/evaluations?model_type=mlp_temp_hum&limit=2")
        assert len(resp.get_json()) == 2

    def test_limit_clamped_to_max_100(self, client):
        resp = client.get("/api/predictions/mlp/evaluations?model_type=mlp_temp_hum&limit=999")
        assert resp.status_code == 200  # 不报错,内部 clamp


class TestModelsEndpoint:
    """GET /api/predictions/mlp/models。"""

    def test_empty_returns_empty_list(self, client):
        resp = client.get("/api/predictions/mlp/models")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_returns_all_models(self, app, client):
        with app.app_context():
            db.session.add(MlModel(model_type="mlp_temp_hum", num_samples_trained=100))
            db.session.add(MlModel(model_type="mlp_light", num_samples_trained=50))
            db.session.commit()

        resp = client.get("/api/predictions/mlp/models")
        data = resp.get_json()
        assert len(data) == 2
        types = {m["model_type"] for m in data}
        assert types == {"mlp_temp_hum", "mlp_light"}


class TestTrainEndpointValidation:
    """POST /api/predictions/mlp/train 参数校验。"""

    def test_missing_model_type_returns_400(self, client):
        resp = client.post("/api/predictions/mlp/train", json={})
        assert resp.status_code == 400

    def test_invalid_model_type_returns_400(self, client):
        resp = client.post("/api/predictions/mlp/train", json={"model_type": "bad"})
        assert resp.status_code == 400

    def test_trainer_not_installed_returns_503(self, client):
        """未注入 trainer(extensions.onnx_trainer 为 None) → 503。"""
        resp = client.post("/api/predictions/mlp/train",
                           json={"model_type": "mlp_temp_hum"})
        assert resp.status_code == 503
        assert "未安装" in resp.get_json()["error"]


class TestFinetuneEndpointValidation:
    """POST /api/predictions/mlp/finetune 参数校验。"""

    def test_missing_model_type_returns_400(self, client):
        resp = client.post("/api/predictions/mlp/finetune", json={})
        assert resp.status_code == 400

    def test_invalid_model_type_returns_400(self, client):
        resp = client.post("/api/predictions/mlp/finetune",
                           json={"model_type": "invalid"})
        assert resp.status_code == 400

    def test_scheduler_not_installed_returns_503(self, client):
        resp = client.post("/api/predictions/mlp/finetune",
                           json={"model_type": "mlp_temp_hum"})
        assert resp.status_code == 503

    def test_scheduler_installed_returns_202(self, client, mock_scheduler):
        """注入 mock scheduler → 返回 202(已触发)。"""
        resp = client.post("/api/predictions/mlp/finetune",
                           json={"model_type": "mlp_temp_hum"})
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["model_type"] == "mlp_temp_hum"


class TestEvaluateEndpointValidation:
    """POST /api/predictions/mlp/evaluate 参数校验。"""

    def test_missing_model_type_returns_400(self, client):
        resp = client.post("/api/predictions/mlp/evaluate", json={})
        assert resp.status_code == 400

    def test_trainer_not_installed_returns_503(self, client):
        resp = client.post("/api/predictions/mlp/evaluate",
                           json={"model_type": "mlp_temp_hum"})
        assert resp.status_code == 503
