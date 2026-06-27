# -*- coding: utf-8 -*-
"""MlModel / MlEvaluation ORM 模型测试。

验证字段映射、to_dict() 完整性、UPSERT 行为(主键 model_type)。
"""
from datetime import datetime

from models.ml import MlModel, MlEvaluation


class TestMlModel:
    """ml_models 表 ORM 测试(主键 model_type,固定2行 UPSERT)。"""

    def test_create_and_query(self, app):
        with app.app_context():
            m = MlModel(model_type="mlp_temp_hum",
                        last_train_time=datetime(2026, 6, 27, 12, 0, 0),
                        num_samples_trained=100,
                        train_loss=0.123,
                        val_loss=0.456)
            _db_add(m)

            fetched = MlModel.query.get("mlp_temp_hum")
            assert fetched is not None
            assert fetched.model_type == "mlp_temp_hum"
            assert fetched.num_samples_trained == 100
            assert abs(fetched.train_loss - 0.123) < 1e-6
            assert abs(fetched.val_loss - 0.456) < 1e-6

    def test_to_dict_completeness(self, app):
        """to_dict() 必须包含全部 8 个字段(与前端契约一致)。"""
        with app.app_context():
            m = MlModel(model_type="mlp_light",
                        last_train_time=datetime(2026, 6, 27, 12, 0, 0),
                        last_finetune_time=datetime(2026, 6, 27, 15, 0, 0),
                        num_samples_trained=50,
                        train_loss=0.05,
                        val_loss=0.08)
            _db_add(m)

            d = MlModel.query.get("mlp_light").to_dict()
            expected_keys = {"model_type", "last_train_time", "last_finetune_time",
                             "num_samples_trained", "train_loss", "val_loss",
                             "created_at", "updated_at"}
            assert set(d.keys()) == expected_keys
            assert d["model_type"] == "mlp_light"
            assert d["last_train_time"] == "2026-06-27 12:00:00"
            assert d["last_finetune_time"] == "2026-06-27 15:00:00"

    def test_to_dict_null_fields(self, app):
        """空值字段 to_dict 应为 None。"""
        with app.app_context():
            m = MlModel(model_type="mlp_temp_hum")
            _db_add(m)
            d = MlModel.query.get("mlp_temp_hum").to_dict()
            assert d["last_train_time"] is None
            assert d["last_finetune_time"] is None
            assert d["train_loss"] is None
            assert d["val_loss"] is None

    def test_upsert_same_model_type(self, app):
        """同 model_type 再次插入应更新而非新增(UPSERT 语义)。"""
        with app.app_context():
            m1 = MlModel(model_type="mlp_temp_hum", num_samples_trained=100)
            _db_add(m1)

            # 模拟 pretrain 的 UPSERT 逻辑
            m2 = MlModel.query.get("mlp_temp_hum")
            assert m2 is not None
            m2.num_samples_trained = 200
            m2.last_train_time = datetime(2026, 6, 27, 12, 0, 0)
            from extensions import db
            db.session.commit()

            rows = MlModel.query.all()
            assert len(rows) == 1
            assert rows[0].num_samples_trained == 200


class TestMlEvaluation:
    """ml_evaluations 表 ORM 测试(自增 id,追加 INSERT)。"""

    def test_create_and_query(self, app):
        with app.app_context():
            e = MlEvaluation(model_type="mlp_temp_hum",
                             new_mae=0.5, new_r2=0.8, new_rmse=0.6,
                             old_mae=0.7, old_r2=0.7, old_rmse=0.9,
                             winner="new",
                             data_start=datetime(2026, 6, 27, 10, 0, 0),
                             data_end=datetime(2026, 6, 27, 12, 0, 0),
                             num_samples=80)
            from extensions import db
            db.session.add(e)
            db.session.commit()

            fetched = MlEvaluation.query.first()
            assert fetched is not None
            assert fetched.id is not None
            assert fetched.winner == "new"
            assert abs(fetched.new_mae - 0.5) < 1e-6

    def test_to_dict_completeness(self, app):
        """to_dict() 必须包含全部 13 个字段。"""
        with app.app_context():
            e = MlEvaluation(model_type="mlp_light", winner="old",
                             new_mae=1.0, old_mae=0.8)
            from extensions import db
            db.session.add(e)
            db.session.commit()

            d = MlEvaluation.query.first().to_dict()
            expected_keys = {"id", "model_type", "eval_time", "new_mae", "new_r2",
                             "new_rmse", "old_mae", "old_r2", "old_rmse", "winner",
                             "data_start", "data_end", "num_samples"}
            assert set(d.keys()) == expected_keys
            assert d["winner"] == "old"

    def test_append_multiple_evaluations(self, app):
        """评估记录是追加的,每次评估新增一行。"""
        with app.app_context():
            from extensions import db
            for i in range(3):
                db.session.add(MlEvaluation(model_type="mlp_temp_hum",
                                            winner="new", new_mae=float(i)))
            db.session.commit()

            rows = MlEvaluation.query.order_by(MlEvaluation.id).all()
            assert len(rows) == 3
            # id 自增
            assert rows[0].id < rows[1].id < rows[2].id


# 辅助函数:提交单条记录
def _db_add(obj):
    from extensions import db
    db.session.add(obj)
    db.session.commit()
