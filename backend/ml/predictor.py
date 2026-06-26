# -*- coding: utf-8 -*-
"""机器学习预测模块。

策略(遵循设计文档):
- 输入:某设备最近 N 条历史 sensor_data
- 数据采样间隔:约 10 分钟/条(传感器上报频率)
- 特征:时间戳(转秒)、温度、湿度、光照(多变量,缺失填 0)
- 目标:预测未来 10/20/30/40/50/60 min 的 metric 值(每步对齐一个数据间隔)
- 模型:LinearRegression(基线) / SVR(可切换)
- 训练:每次 POST /api/predictions/run 时即时训练并预测(在线预测,不持久化模型)
- 评估:在训练集最后 20% 上回算 MAE / R² 作为参考指标
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import List, Dict, Any

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.svm import SVR
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score

# 数据采样间隔(分钟)— 用于决定预测步长与最小样本数
SAMPLE_INTERVAL_MIN = 10

# 默认预测时长(分钟)
DEFAULT_HORIZON = 60
# 预测步长:每步 = 一个采样间隔(10min),共 6 步 → t+10/+20/.../+60
FORECAST_STEPS = tuple(SAMPLE_INTERVAL_MIN * i for i in range(1, 7))  # (10,20,30,40,50,60)
# 训练最少样本数:12 条 = 2 小时数据(保证至少能捕捉到短期趋势)
MIN_SAMPLES = 12
# 历史快照最多保留条数(供前端绘制对比曲线)
HISTORY_SNAPSHOT_LIMIT = 60


def _to_seconds(recorded_at: datetime, t0: datetime) -> float:
    return (recorded_at - t0).total_seconds()


def _build_features(rows: List[Dict[str, Any]], metric: str) -> tuple:
    """构造训练特征矩阵 X 与目标向量 y。

    特征:[t_sec, temp, hum, light] 多变量,缺失填 0
    目标:对应 metric 值
    """
    # 选择最早时间作为 t0
    times = [r["recorded_at"] for r in rows if r.get("recorded_at")]
    if not times:
        return None, None, None
    t0 = min(times)

    X, y = [], []
    for r in rows:
        if r.get("recorded_at") is None:
            continue
        t_sec = _to_seconds(r["recorded_at"], t0)
        temp = float(r.get("temperature") or 0)
        hum = float(r.get("humidity") or 0)
        light = float(r.get("light") or 0)
        target = r.get(metric)
        if target is None:
            continue
        X.append([t_sec, temp, hum, light])
        y.append(float(target))

    if len(X) < MIN_SAMPLES:
        return None, None, t0
    return np.array(X, dtype=float), np.array(y, dtype=float), t0


def _evaluate(model, X_test, y_test) -> tuple:
    if len(X_test) == 0:
        return None, None
    y_pred = model.predict(X_test)
    mae = float(mean_absolute_error(y_test, y_pred))
    # r2 在样本极少时可能为负,容错处理
    try:
        r2 = float(r2_score(y_test, y_pred))
    except Exception:
        r2 = None
    return mae, r2


def predict(rows: List[Dict[str, Any]], metric: str, model_name: str = "linear",
            horizon_minutes: int = DEFAULT_HORIZON) -> Dict[str, Any]:
    """对历史数据训练模型并预测未来值。

    Args:
        rows: 历史数据列表,每项需含 recorded_at(datetime)/temperature/humidity/light/metric 字段
        metric: 预测指标 'temperature'|'humidity'|'light'
        model_name: 'linear' | 'svr'
        horizon_minutes: 预测时长(分钟),默认 30,最大 60

    Returns:
        dict: {predicted_values, history_snapshot, model_name, mae, r2, error?}
    """
    if metric not in ("temperature", "humidity", "light"):
        return {"error": "metric 必须为 temperature/humidity/light"}
    if model_name not in ("linear", "svr"):
        return {"error": "model_name 必须为 linear 或 svr"}

    # 预测时长范围:[一个采样间隔, 4 小时]
    horizon_minutes = max(SAMPLE_INTERVAL_MIN, min(int(horizon_minutes or DEFAULT_HORIZON), 240))

    # 1. 构造特征
    X, y, t0 = _build_features(rows, metric)
    if X is None:
        return {"error": f"历史数据不足,至少需要 {MIN_SAMPLES} 条带 {metric} 的记录"}

    # 2. 划分训练/评估(最后 20% 作为评估集)
    n = len(X)
    split = max(1, int(n * 0.8))
    X_train, X_eval = X[:split], X[split:]
    y_train, y_eval = y[:split], y[split:]

    # 3. 选择模型
    if model_name == "svr":
        base = SVR(kernel="rbf", C=1.0, gamma="scale")
    else:
        base = LinearRegression()

    # SVR 对特征尺度敏感,使用标准化
    if model_name == "svr":
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        base.fit(X_train_s, y_train)
        # 用于预测的特征也需要 transform
        predict_features = lambda feats: scaler.transform(feats)
    else:
        base.fit(X_train, y_train)
        predict_features = lambda feats: feats

    # 4. 评估
    if len(X_eval) > 0:
        X_eval_t = predict_features(X_eval)
        mae, r2 = _evaluate(base, X_eval_t, y_eval)
    else:
        mae, r2 = None, None

    # 5. 预测未来时间点
    # 假设数据采样间隔约为 10min(与入库节流一致),用最后一条时间外推
    last_t_sec = float(X[-1, 0])
    # 取实际数据最后一个时间点作为基准
    last_dt = rows[-1]["recorded_at"] if rows and rows[-1].get("recorded_at") else t0

    # 用每个 metric 的最新读数作为外推起点
    last_temp = float(rows[-1].get("temperature") or 0) if rows else 0
    last_hum = float(rows[-1].get("humidity") or 0) if rows else 0
    last_light = float(rows[-1].get("light") or 0) if rows else 0

    # 生成预测时间点(分钟 → 秒):每步 = 一个采样间隔,过滤超出 horizon 的步
    steps = [m for m in FORECAST_STEPS if m <= horizon_minutes]
    if not steps:
        steps = [horizon_minutes]

    predicted_values = {}
    history_snapshot = {
        "times": [],
        "values": [],
        "metric": metric,
    }
    # 历史快照(供前端绘制对比曲线,最多取后 HISTORY_SNAPSHOT_LIMIT 条避免过大)
    for r in rows[-HISTORY_SNAPSHOT_LIMIT:]:
        if r.get("recorded_at") and r.get(metric) is not None:
            history_snapshot["times"].append(
                r["recorded_at"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(r["recorded_at"], datetime)
                else str(r["recorded_at"])
            )
            history_snapshot["values"].append(float(r[metric]))

    # 多步预测:每步用上一步预测值作为输入(递归多步)
    cur_temp, cur_hum, cur_light = last_temp, last_hum, last_light
    for m in steps:
        future_t_sec = last_t_sec + m * 60
        # 用当前最新读数作为多变量输入(简化策略:保持其他变量为最新值)
        feat = np.array([[future_t_sec, cur_temp, cur_hum, cur_light]], dtype=float)
        feat_t = predict_features(feat)
        yhat = float(base.predict(feat_t)[0])
        # 用预测值更新对应 metric(模拟趋势传播)
        if metric == "temperature":
            cur_temp = yhat
        elif metric == "humidity":
            cur_hum = yhat
        elif metric == "light":
            cur_light = yhat

        future_dt = last_dt + timedelta(minutes=m)
        predicted_values[f"t+{m}"] = round(yhat, 2)
        history_snapshot["times"].append(
            future_dt.strftime("%Y-%m-%d %H:%M:%S") + " *"
        )
        history_snapshot["values"].append(round(yhat, 2))

    return {
        "predicted_values": predicted_values,
        "history_snapshot": history_snapshot,
        "model_name": model_name,
        "mae": round(mae, 4) if mae is not None else None,
        "r2": round(r2, 4) if r2 is not None else None,
        "horizon_minutes": horizon_minutes,
    }
