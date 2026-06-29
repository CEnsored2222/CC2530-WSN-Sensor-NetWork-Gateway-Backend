# -*- coding: utf-8 -*-
"""ONNXTrainer: MLP 模型预训练/微调/评估/推理。

职责:
- pretrain(): 从 sensor_data 表拉取历史数据,从随机初始化训练 PyTorch 模型,导出 ONNX
- fine_tune(): 从环形缓冲区拉取新数据,加载 model.pt 权重继续训练,导出 ONNX
- evaluate(): 在留出集上对比新旧 ONNX 模型,决定保留或回滚
- predict(): 加载 ONNX Session,递归多步预测(6 步)

模型文件结构(每类模型一个目录):
  model.pt / model_prev.pt     PyTorch 权重(微调用)
  model.onnx / model_prev.onnx  ONNX(推理用)
  scaler.json / scaler_prev.json  归一化参数

原子写入 6 步流程保证任何步骤失败都不破坏现有文件。
"""
import json
import os
import threading
import time
from datetime import datetime, timedelta

import numpy as np

from config import Config
from ml.mlp_models import (MODEL_CLASSES, _INPUT_COLUMNS, _OUTPUT_COLUMNS,
                           LAG_WINDOW, DIFF_ORDERS, ROLLING_WINDOW, PER_COL_FEATURES,
                           NUM_FORECAST_STEPS)

# ============================================================
# 模块级:ONNX Session 缓存(避免每次推理 50-100ms 创建开销)
# ============================================================
_SESSION_CACHE = {}                 # {model_type: (session, input_name, mtime)}
_SESSION_LOCK = threading.Lock()


def _to_daily_seconds(dt):
    """转换为日内秒数(0-86399),消除跨设备启动时间偏差。

    多设备聚合训练时,若用绝对时间偏移会引入设备启动偏置。
    日内秒数使所有设备同一时刻 t_sec 相同,模型学到真实日内周期。
    """
    if isinstance(dt, datetime):
        return dt.hour * 3600 + dt.minute * 60 + dt.second
    # ts 是 unix 时间戳(环形缓冲区) → 转为 datetime 再取日内秒数
    return _to_daily_seconds(datetime.fromtimestamp(dt))


def _encode_time_cyclic(t_sec):
    """将日内秒数编码为 (sin, cos),捕捉日内周期(昼夜温差等)。"""
    import math
    phase = (t_sec % 86400.0) / 86400.0 * 2 * math.pi
    return math.sin(phase), math.cos(phase)


def _build_col_features(seq, i, col):
    """为单个输出列构造 [滞后窗口, 差分, 滚动统计] 特征(共 PER_COL_FEATURES 个)。

    seq: 该列的值序列(已对齐到全局时间轴)
    i: 当前索引
    返回:list[float],长度 = LAG_WINDOW+1 + DIFF_ORDERS + 2
    """
    # 滞后窗口 [t-W .. t]
    lag = list(seq[i - LAG_WINDOW : i + 1])
    # 差分 Δy(变化率)
    diffs = []
    for d in range(DIFF_ORDERS):
        idx = i - d
        if idx - 1 >= 0:
            diffs.append(seq[idx] - seq[idx - 1])
        else:
            diffs.append(0.0)
    # 滚动统计
    wv = seq[max(0, i - ROLLING_WINDOW + 1) : i + 1]
    import numpy as np
    roll_mean = float(np.mean(wv)) if wv else 0.0
    roll_std = float(np.std(wv)) if wv else 0.0
    return lag + diffs + [roll_mean, roll_std]


def load_session(onnx_path, model_type):
    """加载 ONNX 模型(缓存单例 + mtime 检查 + prev 降级)。

    Returns:
        (session, input_name)
    """
    import onnxruntime as ort

    prev_path = onnx_path.replace("model.onnx", "model_prev.onnx")

    def _try_load(path):
        if not os.path.exists(path):
            return None, None, None
        mtime = os.path.getmtime(path)
        with _SESSION_LOCK:
            cached = _SESSION_CACHE.get(model_type)
            if cached and cached[2] == mtime:
                return cached[0], cached[1], mtime
        session = ort.InferenceSession(path, providers=['CPUExecutionProvider'])
        input_name = session.get_inputs()[0].name
        return session, input_name, mtime

    session, input_name, mtime = _try_load(onnx_path)
    if session is not None:
        with _SESSION_LOCK:
            _SESSION_CACHE[model_type] = (session, input_name, mtime)
        return session, input_name

    session, input_name, mtime = _try_load(prev_path)
    if session is not None:
        print(f"[MLP] 警告: model.onnx 加载失败,降级使用 model_prev.onnx")
        with _SESSION_LOCK:
            _SESSION_CACHE[model_type] = (session, input_name, mtime)
        return session, input_name

    raise RuntimeError("所有模型文件不可用")


# ============================================================
# ONNXTrainer
# ============================================================
class ONNXTrainer:
    def __init__(self, app):
        self._app = app
        self._models_dir = Config.MLP_MODELS_DIR

    # ---------- 路径辅助 ----------
    def _model_dir(self, model_type):
        return os.path.join(self._models_dir, model_type)

    def _onnx_path(self, model_type):
        return os.path.join(self._model_dir(model_type), "model.onnx")

    def _pt_path(self, model_type):
        return os.path.join(self._model_dir(model_type), "model.pt")

    # ---------- 设备查询 ----------
    def _get_device_ids(self, model_type):
        """按 model_type 查询所有同类型设备 id(device.type 是 JSON 数组)。

        Python 端过滤,避免 SQLAlchemy JSON contains 误匹配。
        """
        from models.device import Device
        if model_type == "mlp_temp_hum":
            required = ("temperature", "humidity")
        else:
            required = ("light",)
        all_devices = Device.query.all()
        result = []
        for d in all_devices:
            if d.type and any(t in d.type for t in required):
                result.append(d.id)
        return result

    # ---------- 特征构造 ----------
    def _build_features_from_db(self, rows, model_type):
        """从 sensor_data 行构造增强特征 (X, y) + 残差学习(预测 Δy)。

        特征:[sin_t, cos_t, <col_0 的 滞后+差分+滚动>, <col_1 的 ...>, ...]
        目标:残差 Δy = next_col - cur_col(让模型学变化量,波动更贴合)
        NULL 填 0,y 列顺序与 _OUTPUT_COLUMNS 严格对齐。
        """
        X, y = [], []
        out_cols = _OUTPUT_COLUMNS[model_type]
        LAG = LAG_WINDOW
        # 预提取每列的值序列(便于算差分和滚动统计)
        col_seqs = {col: [] for col in out_cols}
        for r in rows:
            for col in out_cols:
                v = r.get(col)
                col_seqs[col].append(float(v) if v is not None else 0.0)
        # 时序配对:用 [t-LAG .. t] 的窗口预测未来 NUM_FORECAST_STEPS 步(直接多步)
        for i in range(LAG, len(rows) - NUM_FORECAST_STEPS):
            r = rows[i]
            if not r.get("recorded_at"):
                continue
            t_sec = _to_daily_seconds(r["recorded_at"])
            sin_t, cos_t = _encode_time_cyclic(t_sec)
            # 构造每个输出列的特征
            feat = [sin_t, cos_t]
            for col in out_cols:
                feat.extend(_build_col_features(col_seqs[col], i, col))
            # 多步目标:每个输出列未来 NUM_FORECAST_STEPS 步的绝对值
            # y 列顺序:[col_0 的 6 步, col_1 的 6 步, ...]
            target = []
            for col in out_cols:
                for s in range(NUM_FORECAST_STEPS):
                    v = rows[i + 1 + s].get(col)
                    target.append(float(v) if v is not None else 0.0)
            X.append(feat)
            y.append(target)
        if not X:
            return None, None
        return np.array(X, dtype=float), np.array(y, dtype=float)

    def _build_features_from_ringbuffer(self, data, model_type):
        """从环形缓冲区数据构造增强特征 (X, y)(时序:x_t → y_{t+1})。"""
        X, y = [], []
        out_cols = _OUTPUT_COLUMNS[model_type]
        LAG = LAG_WINDOW
        # 预提取每列的值序列
        col_seqs = {col: [] for col in out_cols}
        for _ts, _did, fields in data:
            for col in out_cols:
                v = fields.get(col)
                col_seqs[col].append(float(v) if v is not None else 0.0)
        # 时序配对:用 [t-LAG .. t] 的窗口预测未来 NUM_FORECAST_STEPS 步(直接多步)
        for i in range(LAG, len(data) - NUM_FORECAST_STEPS):
            ts, _did, fields = data[i]
            t_sec = _to_daily_seconds(ts)
            sin_t, cos_t = _encode_time_cyclic(t_sec)
            # 构造每个输出列的特征
            feat = [sin_t, cos_t]
            for col in out_cols:
                feat.extend(_build_col_features(col_seqs[col], i, col))
            # 多步目标:每个输出列未来 NUM_FORECAST_STEPS 步的绝对值
            target = []
            for col in out_cols:
                for s in range(NUM_FORECAST_STEPS):
                    v = data[i + 1 + s][2].get(col)
                    target.append(float(v) if v is not None else 0.0)
            X.append(feat)
            y.append(target)
        if not X:
            return None, None
        return np.array(X, dtype=float), np.array(y, dtype=float)

    # ---------- Scaler ----------
    def _save_scaler(self, model_type, input_scaler, output_scaler):
        """构建 scaler.json 字典(不写文件,由 _atomic_save 统一写入)。"""
        def _scaler_dict(scaler, names):
            return {
                "mean_": scaler.mean_.tolist(),
                "scale_": scaler.scale_.tolist(),
                "n_features_in_": scaler.n_features_in_,
                "feature_names_": names,
            }
        return {
            "model_type": model_type,
            "input": _scaler_dict(input_scaler, _INPUT_COLUMNS[model_type]),
            "output": _scaler_dict(output_scaler, _OUTPUT_COLUMNS[model_type]) if output_scaler else None,
            "created_at": datetime.now().isoformat(),
            "fitted": True,
        }

    def _load_scaler(self, model_type):
        """从 scaler.json 加载 StandardScaler 实例(输入+输出)。"""
        from sklearn.preprocessing import StandardScaler
        path = os.path.join(self._model_dir(model_type), "scaler.json")
        with open(path) as f:
            data = json.load(f)

        def _build(d):
            s = StandardScaler()
            s.mean_ = np.array(d["mean_"])
            s.scale_ = np.array(d["scale_"])
            s.n_features_in_ = d["n_features_in_"]
            s.var_ = s.scale_ ** 2
            return s

        input_scaler = _build(data["input"])
        output_scaler = _build(data["output"]) if data.get("output") else None
        return input_scaler, output_scaler

    # ---------- 训练 ----------
    def _train_model(self, model, X, y, is_finetune, input_scaler=None, output_scaler=None):
        """训练 PyTorch 模型,返回 (model, train_loss, val_loss)。

        预训练:从随机初始化训练,fit scaler,early stopping
        微调:加载已有 scaler(transform only),冻结 BN/Dropout
        """
        import torch
        import torch.nn as nn

        from sklearn.preprocessing import StandardScaler

        # 归一化
        if is_finetune:
            # 微调:用已有 scaler transform,不 fit
            X_norm = input_scaler.transform(X)
            y_norm = output_scaler.transform(y) if output_scaler else y
        else:
            # 预训练:fit_transform
            input_scaler = StandardScaler()
            X_norm = input_scaler.fit_transform(X)
            output_scaler = StandardScaler()
            y_norm = output_scaler.fit_transform(y)

        # 划分训练/验证(预训练 80/20,微调用全部传入数据)
        n = len(X_norm)
        if is_finetune:
            X_train, y_train = X_norm, y_norm
            X_val, y_val = None, None
        else:
            split = max(1, int(n * (1 - Config.MLP_EVAL_SPLIT_RATIO)))
            X_train, y_train = X_norm[:split], y_norm[:split]
            X_val, y_val = X_norm[split:], y_norm[split:]

        # CPU 限制 + GIL 管理
        _orig_threads = torch.get_num_threads()
        torch.set_num_threads(1)
        lr = Config.MLP_FINETUNE_LR if is_finetune else Config.MLP_TRAIN_LR
        epochs = Config.MLP_FINETUNE_EPOCHS if is_finetune else Config.MLP_EPOCHS
        optimizer = torch.optim.Adam(model.parameters(), lr=lr)
        criterion = nn.MSELoss()
        batch_size = max(2, min(Config.MLP_BATCH_SIZE, len(X_train)))

        if is_finetune:
            model.eval()      # 冻结 BN running stats + 关闭 Dropout
        else:
            model.train()

        X_t = torch.FloatTensor(X_train)
        y_t = torch.FloatTensor(y_train)
        best_val_loss = float('inf')
        patience_counter = 0
        train_loss = 0.0
        val_loss = None

        try:
            for epoch in range(epochs):
                # 训练
                epoch_loss = 0.0
                num_batches = 0
                for i in range(0, len(X_t), batch_size):
                    bx = X_t[i:i+batch_size]
                    by = y_t[i:i+batch_size]
                    # BatchNorm1d 训练态至少需要 2 个样本,跳过尾部 size=1 的 batch
                    if len(bx) < 2:
                        continue
                    optimizer.zero_grad()
                    out = model(bx)
                    loss = criterion(out, by)
                    loss.backward()
                    optimizer.step()
                    epoch_loss += loss.item()
                    num_batches += 1
                    time.sleep(0)       # 让出 GIL
                train_loss = epoch_loss / num_batches if num_batches else 0

                # 验证(仅预训练)
                if X_val is not None and len(X_val) > 0:
                    model.eval()
                    with torch.no_grad():
                        out_val = model(torch.FloatTensor(X_val))
                        val_loss = float(criterion(out_val, torch.FloatTensor(y_val)))
                    if not is_finetune:
                        model.train()

                    # Early stopping(仅预训练)
                    if val_loss < best_val_loss:
                        best_val_loss = val_loss
                        patience_counter = 0
                    else:
                        patience_counter += 1
                        if patience_counter >= Config.MLP_EARLY_STOP_PATIENCE:
                            break
                time.sleep(0.001)       # epoch 末尾 1ms 暂停
        finally:
            torch.set_num_threads(_orig_threads)   # 恢复

        return model, input_scaler, output_scaler, train_loss, val_loss

    # ---------- 原子写入 ----------
    def _atomic_save(self, model, model_type, scaler_dict):
        """6 步原子写入: .pt + .onnx + scaler.json(任何步骤失败不破坏现有文件)。"""
        import torch
        import onnx
        import onnxruntime

        d = self._model_dir(model_type)
        os.makedirs(d, exist_ok=True)
        input_dim = len(_INPUT_COLUMNS[model_type])

        # 步骤1: 写 .pt.tmp
        pt_tmp = os.path.join(d, "model.pt.tmp")
        torch.save(model.state_dict(), pt_tmp)

        # 步骤2: 导出 .onnx.tmp
        model.eval()
        dummy = torch.randn(1, input_dim)
        onnx_tmp = os.path.join(d, "model.onnx.tmp")
        torch.onnx.export(model, dummy, onnx_tmp,
                          opset_version=Config.MLP_ONNX_OPSET_VERSION,
                          input_names=["input"],
                          output_names=["output"])

        # 步骤3: 校验 ONNX
        onnx.checker.check_model(onnx_tmp)

        # 步骤4: 写 scaler.json.tmp
        scaler_tmp = os.path.join(d, "scaler.json.tmp")
        with open(scaler_tmp, "w") as f:
            json.dump(scaler_dict, f, ensure_ascii=False, indent=2)
            os.fsync(f.fileno())

        # 步骤5: 现有文件退为 prev(首次预训练时跳过)
        pt_path = os.path.join(d, "model.pt")
        onnx_path = os.path.join(d, "model.onnx")
        scaler_path = os.path.join(d, "scaler.json")
        if os.path.exists(pt_path):
            os.replace(pt_path, os.path.join(d, "model_prev.pt"))
            os.replace(onnx_path, os.path.join(d, "model_prev.onnx"))
            os.replace(scaler_path, os.path.join(d, "scaler_prev.json"))

        # 步骤6: 原子替换
        os.replace(pt_tmp, pt_path)
        os.replace(onnx_tmp, onnx_path)
        os.replace(scaler_tmp, scaler_path)

    def _rollback_to_prev(self, model_type):
        """回滚到 model_prev.*(评估判定 old 更优时调用),走 5 步原子流程。"""
        import shutil
        import onnx

        d = self._model_dir(model_type)
        pt_prev = os.path.join(d, "model_prev.pt")
        onnx_prev = os.path.join(d, "model_prev.onnx")
        scaler_prev = os.path.join(d, "scaler_prev.json")
        if not os.path.exists(onnx_prev):
            return False    # 无 prev 可回滚

        # 步骤1-3: 复制 prev 为 tmp
        shutil.copy2(pt_prev, os.path.join(d, "model.pt.tmp"))
        shutil.copy2(onnx_prev, os.path.join(d, "model.onnx.tmp"))
        shutil.copy2(scaler_prev, os.path.join(d, "scaler.json.tmp"))

        # 步骤4: 校验
        onnx.checker.check_model(os.path.join(d, "model.onnx.tmp"))

        # 步骤5: 原子替换(prev 文件保持不变,作为下次评估 baseline)
        os.replace(os.path.join(d, "model.pt.tmp"), os.path.join(d, "model.pt"))
        os.replace(os.path.join(d, "model.onnx.tmp"), os.path.join(d, "model.onnx"))
        os.replace(os.path.join(d, "scaler.json.tmp"), os.path.join(d, "scaler.json"))
        return True

    def _recover_tmp_files(self, model_type):
        """启动时崩溃恢复: .tmp 三件齐全则完成替换,否则删除 .tmp。"""
        d = self._model_dir(model_type)
        tmps = ["model.pt.tmp", "model.onnx.tmp", "scaler.json.tmp"]
        if all(os.path.exists(os.path.join(d, t)) for t in tmps):
            for t in tmps:
                real = t.replace(".tmp", "")
                os.replace(os.path.join(d, t), os.path.join(d, real))
            print(f"[MLP] {model_type}: 恢复未完成的原子写入")
        else:
            for t in tmps:
                p = os.path.join(d, t)
                if os.path.exists(p):
                    os.remove(p)

    # ---------- 预训练 ----------
    def pretrain(self, model_type, pretrain_hours=None):
        """从 sensor_data 表拉取历史数据预训练。

        Returns:
            dict: {train_loss, val_loss, epochs_completed, num_samples, model_type}
            或 {"error": "..."}
        """
        from models.sensor_data import SensorData
        from models.ml import MlModel
        from extensions import db

        hours = pretrain_hours or Config.MLP_PRETRAIN_HOURS
        device_ids = self._get_device_ids(model_type)
        if not device_ids:
            return {"error": f"未找到 {model_type} 对应的设备"}

        since = datetime.now() - timedelta(hours=hours)
        rows = (SensorData.query
                .filter(SensorData.device_id.in_(device_ids),
                        SensorData.recorded_at >= since)
                .order_by(SensorData.recorded_at)
                .all())
        row_dicts = [{"recorded_at": r.recorded_at,
                       "temperature": r.temperature,
                       "humidity": r.humidity,
                       "light": r.light} for r in rows]

        X, y = self._build_features_from_db(row_dicts, model_type)
        if X is None or len(X) < Config.MLP_MIN_SAMPLES:
            return {"error": f"历史数据不足,至少需要 {Config.MLP_MIN_SAMPLES} 条"}

        # 训练
        model_cls = MODEL_CLASSES[model_type]
        model = model_cls()
        model, input_scaler, output_scaler, train_loss, val_loss = \
            self._train_model(model, X, y, is_finetune=False)

        # 原子写入
        scaler_dict = self._save_scaler(model_type, input_scaler, output_scaler)
        self._atomic_save(model, model_type, scaler_dict)

        # 更新 ml_models(UPSERT)
        ml_model = MlModel.query.get(model_type)
        if ml_model is None:
            ml_model = MlModel(model_type=model_type)
            db.session.add(ml_model)
        ml_model.last_train_time = datetime.now()
        ml_model.last_finetune_time = None
        ml_model.num_samples_trained = len(X)
        ml_model.train_loss = round(train_loss, 6)
        ml_model.val_loss = round(val_loss, 6) if val_loss is not None else None
        db.session.commit()

        return {
            "train_loss": round(train_loss, 6),
            "val_loss": round(val_loss, 6) if val_loss is not None else None,
            "num_samples": len(X),
            "model_type": model_type,
        }

    # ---------- 微调 ----------
    def fine_tune(self, model_type, ml_model, eval_set_cache=None):
        """从环形缓冲区拉取新数据,加载 model.pt 权重继续训练。

        Args:
            model_type: 模型类型
            ml_model: MlModel ORM 实例(调用方在 app_context 内查询)
            eval_set_cache: dict 引用,微调时缓存 eval_set 供评估使用
        """
        import torch
        import extensions as ext_mod

        data_buf = getattr(ext_mod, "data_buffer", None)
        if data_buf is None or data_buf.ring_buffer is None:
            return {"error": "环形缓冲区未初始化"}

        device_ids = self._get_device_ids(model_type)
        since_ts = ml_model.last_train_time.timestamp() if ml_model.last_train_time else 0
        data = data_buf.ring_buffer.get_aggregated_since(device_ids, since_ts)
        if len(data) < Config.MLP_FINETUNE_MIN_SAMPLES:
            return {"error": f"新数据不足({len(data)}/{Config.MLP_FINETUNE_MIN_SAMPLES})"}

        # 80/20 划分(防数据泄露): 前 80% 训练, 后 20% 留出评估
        split = max(1, int(len(data) * (1 - Config.MLP_EVAL_SPLIT_RATIO)))
        finetune_data = data[:split]
        eval_data = data[split:]

        # 缓存 eval_set(评估时直接使用,不从环 buffer 重新拉取)
        if eval_set_cache is not None:
            eval_set_cache[model_type] = eval_data

        if len(eval_data) < Config.MLP_EVAL_MIN_SAMPLES:
            return {"error": f"留出集不足({len(eval_data)}/{Config.MLP_EVAL_MIN_SAMPLES})"}

        # 构造训练特征
        X, y = self._build_features_from_ringbuffer(finetune_data, model_type)
        if X is None:
            return {"error": "微调数据全部为空"}

        # 加载 PyTorch 权重(ONNX 不可微调,必须用 .pt)
        input_scaler, output_scaler = self._load_scaler(model_type)
        model_cls = MODEL_CLASSES[model_type]
        model = model_cls()
        pt_path = self._pt_path(model_type)
        model.load_state_dict(torch.load(pt_path, map_location='cpu'))

        # 训练(微调: eval 模式冻结 BN, 不 fit scaler)
        model, _, _, train_loss, _ = \
            self._train_model(model, X, y, is_finetune=True,
                              input_scaler=input_scaler, output_scaler=output_scaler)

        # 原子写入(scaler.json 内容不变, 但仍走 6 步流程保证一致性)
        scaler_dict = self._save_scaler(model_type, input_scaler, output_scaler)
        self._atomic_save(model, model_type, scaler_dict)

        # 更新分界线(不调 flush)
        ml_model.last_train_time = datetime.now()

        return {"train_loss": round(train_loss, 6), "num_samples": len(X),
                "model_type": model_type}

    # ---------- 评估 ----------
    def evaluate(self, model_type, eval_set=None):
        """在留出集上对比新旧 ONNX 模型,决定保留或回滚。

        Args:
            eval_set: [(ts, device_id, fields), ...] 来自微调缓存;None 时尝试加载
        Returns:
            dict: {winner, new_mae, new_r2, new_rmse, old_mae, ...}
        """
        from models.ml import MlEvaluation
        from extensions import db
        from sklearn.metrics import mean_absolute_error, r2_score

        if not eval_set:
            return {"error": "无可评估数据,请先微调"}

        X_eval, y_eval = self._build_features_from_ringbuffer(eval_set, model_type)
        if X_eval is None or len(X_eval) == 0:
            return {"error": "评估数据为空"}

        input_scaler, output_scaler = self._load_scaler(model_type)
        X_norm = input_scaler.transform(X_eval)

        # 新模型评估
        new_session, new_input = load_session(self._onnx_path(model_type), model_type)
        new_pred_norm = new_session.run(None, {new_input: X_norm.astype(np.float32)})[0]
        new_pred = output_scaler.inverse_transform(new_pred_norm) if output_scaler else new_pred_norm
        new_mae = float(mean_absolute_error(y_eval, new_pred))
        new_r2 = float(r2_score(y_eval, new_pred))
        new_rmse = float(np.sqrt(np.mean((y_eval - new_pred) ** 2)))

        # 旧模型评估(model_prev.onnx 不存在时 winner='new')
        old_mae = old_r2 = old_rmse = None
        prev_onnx = self._onnx_path(model_type).replace("model.onnx", "model_prev.onnx")
        if os.path.exists(prev_onnx):
            old_session, old_input = load_session(prev_onnx, model_type)
            old_pred_norm = old_session.run(None, {old_input: X_norm.astype(np.float32)})[0]
            old_pred = output_scaler.inverse_transform(old_pred_norm) if output_scaler else old_pred_norm
            old_mae = float(mean_absolute_error(y_eval, old_pred))
            old_r2 = float(r2_score(y_eval, old_pred))
            old_rmse = float(np.sqrt(np.mean((y_eval - old_pred) ** 2)))

        # 判定 winner
        if old_mae is not None and new_mae > old_mae:
            winner = "old"
            self._rollback_to_prev(model_type)     # 回滚到旧模型
        elif old_mae is not None and abs(new_mae - old_mae) < 1e-9:
            winner = "tie"
        else:
            winner = "new"

        # 写入 ml_evaluations
        ts_list = [ts for ts, _, _ in eval_set]
        eval_record = MlEvaluation(
            model_type=model_type,
            new_mae=round(new_mae, 6), new_r2=round(new_r2, 6), new_rmse=round(new_rmse, 6),
            old_mae=round(old_mae, 6) if old_mae is not None else None,
            old_r2=round(old_r2, 6) if old_r2 is not None else None,
            old_rmse=round(old_rmse, 6) if old_rmse is not None else None,
            winner=winner,
            data_start=datetime.fromtimestamp(min(ts_list)),
            data_end=datetime.fromtimestamp(max(ts_list)),
            num_samples=len(eval_set),
        )
        db.session.add(eval_record)
        db.session.commit()

        return {
            "winner": winner, "new_mae": new_mae, "new_r2": new_r2, "new_rmse": new_rmse,
            "old_mae": old_mae, "old_r2": old_r2, "old_rmse": old_rmse,
            "num_samples": len(eval_set),
        }

    # ---------- 推理 ----------
    def predict(self, model_type, rows, horizon_minutes=None):
        """ONNX 推理: 递归多步预测(按 horizon 动态生成步数)。

        Args:
            model_type: 模型类型
            rows: sensor_data 行(最近 MLP_LOOKBACK_HOURS 小时,单设备)
            horizon_minutes: 预测时长(分钟),None 时用默认值 60
        Returns:
            {metric: {"predicted_values": {"t+10": v, ...}, "history_snapshot": {...}}}
        """
        if not rows:
            return {"error": "无历史数据"}

        input_scaler, output_scaler = self._load_scaler(model_type)
        out_cols = _OUTPUT_COLUMNS[model_type]
        session, input_name = load_session(self._onnx_path(model_type), model_type)

        # 取最后一条作为基准时间
        last_row = rows[-1]
        last_dt = last_row.get("recorded_at") or datetime.now()
        t_sec_last = _to_daily_seconds(last_dt)

        # 初始化每列的历史序列(rows 最后足够长的真实值,用于构造 lag/diffs/roll)
        # 残差学习:模型输出 Δy,yhat = last_real + Δy(让模型学变化量,波动更贴合)
        keep_len = LAG_WINDOW + max(DIFF_ORDERS, ROLLING_WINDOW) + 2
        hist_seqs = {}
        for col in out_cols:
            seq = []
            for r in rows[-keep_len:]:
                v = r.get(col)
                seq.append(float(v) if v is not None else 0.0)
            hist_seqs[col] = seq

        # 直接多步预测:一次前向得到 NUM_FORECAST_STEPS 步(避免递归平滑,保留波形)
        predictions = {col: [] for col in out_cols}
        # 步进 = 相邻预测点间隔(10min = 600s)
        step_min = Config.MLP_FORECAST_STEPS[0]
        if horizon_minutes is None:
            horizon_minutes = Config.MLP_DEFAULT_HORIZON
        num_steps = max(1, horizon_minutes // step_min)
        steps = [step_min * i for i in range(1, num_steps + 1)]
        # 用最后一条数据的时间构造特征(只需一次前向)
        sin_t, cos_t = _encode_time_cyclic(t_sec_last)
        feat = [sin_t, cos_t]
        for col in out_cols:
            feat.extend(_build_col_features(hist_seqs[col], len(hist_seqs[col]) - 1, col))
        feat_arr = input_scaler.transform(np.array([feat], dtype=float))
        out_norm = session.run(None, {input_name: feat_arr.astype(np.float32)})[0]
        out = output_scaler.inverse_transform(out_norm) if output_scaler else out_norm
        pred_all = out[0]  # shape = (NUM_FORECAST_STEPS * num_cols,)
        # 拆分:每列的 NUM_FORECAST_STEPS 步,y 列顺序为 [col_0 的 6 步, col_1 的 6 步, ...]
        for col_idx, col in enumerate(out_cols):
            col_preds = pred_all[col_idx * NUM_FORECAST_STEPS : (col_idx + 1) * NUM_FORECAST_STEPS]
            for step_idx in range(min(num_steps, NUM_FORECAST_STEPS)):
                predictions[col].append(round(float(col_preds[step_idx]), 2))
            # horizon > 60 时,超出 6 步的部分用最后一步值填充(保持连续)
            for step_idx in range(NUM_FORECAST_STEPS, num_steps):
                predictions[col].append(round(float(col_preds[-1]), 2))

        # 构造返回结果(每个 metric 一份 predicted_values + history_snapshot)
        result = {}
        for i, col in enumerate(out_cols):
            pred_vals = predictions[col]
            predicted_values = {}
            for j, step in enumerate(steps):
                predicted_values[f"t+{step}"] = pred_vals[j]

            # history_snapshot(与现有 predictor 结构一致)
            times = []
            values = []
            for r in rows:
                if r.get("recorded_at") and r.get(col) is not None:
                    dt = r["recorded_at"]
                    times.append(dt.strftime("%Y-%m-%d %H:%M:%S")
                                 if isinstance(dt, datetime) else str(dt))
                    values.append(float(r[col]))
            for j, step in enumerate(steps):
                future_dt = last_dt + timedelta(minutes=step)
                times.append(future_dt.strftime("%Y-%m-%d %H:%M:%S") + " *")
                values.append(pred_vals[j])

            result[col] = {
                "predicted_values": predicted_values,
                "history_snapshot": {"times": times, "values": values, "metric": col},
            }
        return result
