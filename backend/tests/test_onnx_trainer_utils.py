# -*- coding: utf-8 -*-
"""ONNXTrainer 工具函数与文件操作测试。

覆盖:
- _to_daily_seconds: 日内秒数转换(含跨日回绕)
- _save_scaler / _load_scaler: scaler.json 往返一致性
- _atomic_save: 6步原子写入(首次 + 二次产生 prev)
- _rollback_to_prev: 回滚到 prev
- _recover_tmp_files: 崩溃恢复(三件齐全 vs 部分 tmp)
"""
import filecmp
import json
import os
import time
from datetime import datetime, timezone

import numpy as np
import pytest

from ml.onnx_trainer import _to_daily_seconds
from ml.mlp_models import MODEL_CLASSES


class TestToDailySeconds:
    """日内秒数转换(修复 P1 #11: 消除跨设备启动偏置)。"""

    def test_midnight_is_zero(self):
        assert _to_daily_seconds(datetime(2026, 6, 27, 0, 0, 0)) == 0

    def test_end_of_day(self):
        assert _to_daily_seconds(datetime(2026, 6, 27, 23, 59, 59)) == 86399

    def test_noon(self):
        assert _to_daily_seconds(datetime(2026, 6, 27, 12, 0, 0)) == 43200

    def test_hour_minute_second(self):
        # 01:01:01 → 3600 + 60 + 1 = 3661
        assert _to_daily_seconds(datetime(2026, 6, 27, 1, 1, 1)) == 3661

    def test_unix_timestamp_uses_local_time(self):
        """timestamp 输入: fromtimestamp 转本地时间后取日内秒数。"""
        # 构造本地时间 12:00:00 的 timestamp
        dt_local = datetime(2026, 6, 27, 12, 0, 0)
        ts = time.mktime(dt_local.timetuple())
        assert _to_daily_seconds(ts) == 43200

    def test_date_part_ignored(self):
        """不同日期同时刻 → 同一日内秒数(消除日期偏置)。"""
        d1 = datetime(2026, 6, 27, 10, 30, 0)
        d2 = datetime(2026, 6, 28, 10, 30, 0)
        assert _to_daily_seconds(d1) == _to_daily_seconds(d2)


class TestScalerRoundtrip:
    """scaler.json 保存/加载往返一致性(微调时 transform only,必须与预训练一致)。"""

    def test_save_load_roundtrip(self, trainer, app):
        from sklearn.preprocessing import StandardScaler

        with app.app_context():
            X = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]], dtype=float)
            y = np.array([[10], [20], [30]], dtype=float)
            input_scaler = StandardScaler().fit(X)
            output_scaler = StandardScaler().fit(y)

            # 构造 scaler dict
            scaler_dict = trainer._save_scaler("mlp_temp_hum", input_scaler, output_scaler)
            assert scaler_dict["fitted"] is True
            assert scaler_dict["model_type"] == "mlp_temp_hum"

            # 手动写文件(_atomic_save 也会写,这里单独测 scaler)
            d = trainer._model_dir("mlp_temp_hum")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "scaler.json"), "w") as f:
                json.dump(scaler_dict, f)

            # 加载
            loaded_in, loaded_out = trainer._load_scaler("mlp_temp_hum")

            # transform 结果必须一致
            np.testing.assert_array_almost_equal(
                loaded_in.transform(X), input_scaler.transform(X))
            np.testing.assert_array_almost_equal(
                loaded_out.transform(y), output_scaler.transform(y))

    def test_load_scaler_without_output(self, trainer, app):
        """output 为 None 时(mlp_light 单输出也用 scaler,但测试 None 分支)。"""
        from sklearn.preprocessing import StandardScaler

        with app.app_context():
            X = np.array([[1, 2], [3, 4]], dtype=float)
            input_scaler = StandardScaler().fit(X)
            scaler_dict = trainer._save_scaler("mlp_light", input_scaler, None)
            assert scaler_dict["output"] is None

            d = trainer._model_dir("mlp_light")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "scaler.json"), "w") as f:
                json.dump(scaler_dict, f)

            loaded_in, loaded_out = trainer._load_scaler("mlp_light")
            assert loaded_out is None
            np.testing.assert_array_almost_equal(
                loaded_in.transform(X), input_scaler.transform(X))


class TestAtomicSave:
    """6步原子写入: .pt + .onnx + scaler.json。"""

    def _make_scaler_dict(self, trainer, model_type):
        from sklearn.preprocessing import StandardScaler
        X = np.array([[1, 2, 3], [4, 5, 6]], dtype=float)
        y = np.array([[1], [2]], dtype=float)
        in_s = StandardScaler().fit(X)
        out_s = StandardScaler().fit(y)
        return trainer._save_scaler(model_type, in_s, out_s)

    def test_first_save_creates_three_files(self, trainer, app):
        with app.app_context():
            model = MODEL_CLASSES["mlp_temp_hum"]()
            scaler_dict = self._make_scaler_dict(trainer, "mlp_temp_hum")

            trainer._atomic_save(model, "mlp_temp_hum", scaler_dict)

            d = trainer._model_dir("mlp_temp_hum")
            assert os.path.exists(os.path.join(d, "model.pt"))
            assert os.path.exists(os.path.join(d, "model.onnx"))
            assert os.path.exists(os.path.join(d, "scaler.json"))
            # 首次保存,无 prev
            assert not os.path.exists(os.path.join(d, "model_prev.pt"))
            assert not os.path.exists(os.path.join(d, "model_prev.onnx"))

    def test_second_save_creates_prev(self, trainer, app):
        with app.app_context():
            scaler_dict = self._make_scaler_dict(trainer, "mlp_temp_hum")
            model1 = MODEL_CLASSES["mlp_temp_hum"]()
            model2 = MODEL_CLASSES["mlp_temp_hum"]()

            trainer._atomic_save(model1, "mlp_temp_hum", scaler_dict)
            trainer._atomic_save(model2, "mlp_temp_hum", scaler_dict)

            d = trainer._model_dir("mlp_temp_hum")
            assert os.path.exists(os.path.join(d, "model_prev.pt"))
            assert os.path.exists(os.path.join(d, "model_prev.onnx"))
            assert os.path.exists(os.path.join(d, "scaler_prev.json"))

    def test_no_tmp_files_left_after_save(self, trainer, app):
        """原子写入完成后不应残留 .tmp 文件。"""
        with app.app_context():
            model = MODEL_CLASSES["mlp_light"]()
            from sklearn.preprocessing import StandardScaler
            X = np.array([[1, 2], [3, 4]], dtype=float)
            y = np.array([[1], [2]], dtype=float)
            scaler_dict = trainer._save_scaler(
                "mlp_light", StandardScaler().fit(X), StandardScaler().fit(y))

            trainer._atomic_save(model, "mlp_light", scaler_dict)

            d = trainer._model_dir("mlp_light")
            assert not os.path.exists(os.path.join(d, "model.pt.tmp"))
            assert not os.path.exists(os.path.join(d, "model.onnx.tmp"))
            assert not os.path.exists(os.path.join(d, "scaler.json.tmp"))


class TestRollbackToPrev:
    """回滚到 model_prev(评估判定 old 更优时)。"""

    def test_rollback_without_prev_returns_false(self, trainer, app):
        with app.app_context():
            assert trainer._rollback_to_prev("mlp_temp_hum") is False

    def test_rollback_restores_prev_content(self, trainer, app):
        """二次保存后回滚,model.onnx 内容应与 model_prev.onnx 一致。"""
        from sklearn.preprocessing import StandardScaler

        with app.app_context():
            X = np.array([[1, 2, 3], [4, 5, 6]], dtype=float)
            y = np.array([[1], [2]], dtype=float)
            scaler_dict = trainer._save_scaler(
                "mlp_temp_hum", StandardScaler().fit(X), StandardScaler().fit(y))

            model1 = MODEL_CLASSES["mlp_temp_hum"]()
            model2 = MODEL_CLASSES["mlp_temp_hum"]()
            trainer._atomic_save(model1, "mlp_temp_hum", scaler_dict)
            trainer._atomic_save(model2, "mlp_temp_hum", scaler_dict)

            # 回滚
            assert trainer._rollback_to_prev("mlp_temp_hum") is True

            d = trainer._model_dir("mlp_temp_hum")
            # 回滚后 model.onnx 与 model_prev.onnx 内容一致
            assert filecmp.cmp(
                os.path.join(d, "model.onnx"),
                os.path.join(d, "model_prev.onnx"),
                shallow=False,
            )


class TestRecoverTmpFiles:
    """启动时崩溃恢复: .tmp 三件齐全则完成替换,否则删除。"""

    def test_recover_complete_tmp_completes_replace(self, trainer, app):
        """三件 tmp 齐全 → 替换为正式文件。"""
        from sklearn.preprocessing import StandardScaler

        with app.app_context():
            # 先正常保存一次
            X = np.array([[1, 2, 3], [4, 5, 6]], dtype=float)
            y = np.array([[1], [2]], dtype=float)
            scaler_dict = trainer._save_scaler(
                "mlp_temp_hum", StandardScaler().fit(X), StandardScaler().fit(y))
            trainer._atomic_save(MODEL_CLASSES["mlp_temp_hum"](), "mlp_temp_hum", scaler_dict)

            # 模拟崩溃:复制正式文件为 tmp(假装保存中断在步骤6之前)
            import shutil
            d = trainer._model_dir("mlp_temp_hum")
            for name in ("model.pt", "model.onnx", "scaler.json"):
                shutil.copy(os.path.join(d, name), os.path.join(d, name + ".tmp"))

            # 恢复
            trainer._recover_tmp_files("mlp_temp_hum")

            # tmp 被清理
            for name in ("model.pt.tmp", "model.onnx.tmp", "scaler.json.tmp"):
                assert not os.path.exists(os.path.join(d, name))
            # 正式文件仍在
            for name in ("model.pt", "model.onnx", "scaler.json"):
                assert os.path.exists(os.path.join(d, name))

    def test_recover_partial_tmp_deletes_all(self, trainer, app):
        """部分 tmp(不齐全) → 全部删除,保留现有正式文件。"""
        with app.app_context():
            d = trainer._model_dir("mlp_temp_hum")
            os.makedirs(d, exist_ok=True)
            # 只创建 1 个 tmp(不齐全)
            with open(os.path.join(d, "model.pt.tmp"), "w") as f:
                f.write("partial")

            trainer._recover_tmp_files("mlp_temp_hum")

            assert not os.path.exists(os.path.join(d, "model.pt.tmp"))

    def test_recover_when_dir_not_exists(self, trainer, app):
        """目录不存在时静默处理(不抛异常,app.py 启动时安全调用)。"""
        with app.app_context():
            # 目录不存在,_recover_tmp_files 应静默处理(all(exists) 为 False → 删除分支,无 tmp 可删)
            trainer._recover_tmp_files("mlp_light")
            # 验证没有创建目录
            d = trainer._model_dir("mlp_light")
            assert not os.path.exists(d)
