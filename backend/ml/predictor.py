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
from sklearn.neighbors import KNeighborsRegressor
from sklearn.ensemble import RandomForestRegressor
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
# 滞后窗口大小:用过去 W+1 个时间点的 metric 值作为特征(含当前)
# W=8 意味着 [metric_t .. metric_{t-8}],共 9 个滞后值,覆盖 80min 历史
LAG_WINDOW = 8
# 差分阶数:Δy_t, Δy_{t-1}, Δy_{t-2}(3 个变化率,反映趋势加速度)
DIFF_ORDERS = 3
# 滚动统计窗口:过去 5 步的 mean/std(反映局部波动幅度)
ROLLING_WINDOW = 5
# 日内秒数周期(用于 sin/cos 编码,消除绝对时间数值过大问题)
SECONDS_PER_DAY = 86400.0


def _to_seconds(recorded_at: datetime, t0: datetime) -> float:
    return (recorded_at - t0).total_seconds()


def _encode_time_cyclic(t_sec: float) -> tuple:
    """将绝对秒数编码为日内周期的 (sin, cos),消除大数值 + 捕捉日内周期。

    用 86400s 为周期,让模型学到"早晚温差"等周期模式。
    """
    phase = (t_sec % SECONDS_PER_DAY) / SECONDS_PER_DAY * 2 * math.pi
    return math.sin(phase), math.cos(phase)


def _clean_outliers(rows: List[Dict[str, Any]], metric: str) -> List[Dict[str, Any]]:
    """IQR 法清洗异常值(如 hum=13.0 这种传感器故障)。

    检测 < Q1-1.5*IQR 或 > Q3+1.5*IQR 的点,用前后合法值的中位数替换(保持行数不变)。
    """
    vals = [r.get(metric) for r in rows if r.get(metric) is not None]
    if len(vals) < 4:
        return rows  # 数据太少,不做清洗
    arr = sorted(float(v) for v in vals)
    n = len(arr)
    q1 = arr[n // 4]
    q3 = arr[3 * n // 4]
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    # 合法值的中位数(用于替换异常)
    legal = [float(v) for v in vals if lo <= float(v) <= hi]
    if not legal:
        return rows
    median_legal = sorted(legal)[len(legal) // 2]
    # 替换异常值
    cleaned = []
    for r in rows:
        r2 = dict(r)
        v = r2.get(metric)
        if v is not None and not (lo <= float(v) <= hi):
            r2[metric] = median_legal
        cleaned.append(r2)
    return cleaned


def _interpolate_missing(rows: List[Dict[str, Any]], metric: str) -> List[Dict[str, Any]]:
    """线性插补缺失值(替代填 0,保持趋势连续性)。

    对 None 值,用前后最近的合法值线性插值;首尾缺失用最近值填充。
    """
    # 收集索引和值
    n = len(rows)
    vals = [r.get(metric) for r in rows]
    # 找到所有非 None 的位置
    valid_idx = [i for i, v in enumerate(vals) if v is not None]
    if not valid_idx:
        return rows  # 全部缺失,无法插补
    result = []
    for i, r in enumerate(rows):
        r2 = dict(r)
        v = r2.get(metric)
        if v is not None:
            result.append(r2)
            continue
        # 找前后最近的合法值
        prev_idx = max((j for j in valid_idx if j < i), default=None)
        next_idx = min((j for j in valid_idx if j > i), default=None)
        if prev_idx is not None and next_idx is not None:
            # 线性插值
            prev_v = float(vals[prev_idx])
            next_v = float(vals[next_idx])
            ratio = (i - prev_idx) / (next_idx - prev_idx)
            r2[metric] = prev_v + ratio * (next_v - prev_v)
        elif prev_idx is not None:
            r2[metric] = float(vals[prev_idx])  # 用前值填充
        else:
            r2[metric] = float(vals[next_idx])  # 用后值填充
        result.append(r2)
    return result


def _build_features(rows: List[Dict[str, Any]], metric: str) -> tuple:
    """全面增强特征工程 + 残差学习(预测 Δy)。

    特征向量:
      [sin_t, cos_t,                    # 时间周期编码(2)
       M_t, M_{t-1}, ..., M_{t-W},      # 滞后窗口(LAG_WINDOW+1=9)
       ΔM_t, ΔM_{t-1}, ΔM_{t-2},        # 差分变化率(DIFF_ORDERS=3)
       roll_mean, roll_std,             # 滚动统计(2)
       other_vars...]                   # 其他变量当前值(2)
    目标:残差 ΔM = M_{t+1} - M_t(让模型学变化量,波动更贴合)
    """
    # 数据预处理:1.线性插补缺失值 2.IQR 清洗异常值(保持趋势连续性)
    rows = _interpolate_missing(rows, metric)
    rows = _clean_outliers(rows, metric)

    times = [r["recorded_at"] for r in rows if r.get("recorded_at")]
    if not times:
        return None, None, None
    t0 = min(times)

    other_cols = [c for c in ("temperature", "humidity", "light") if c != metric]

    # 预提取 metric 序列(便于算差分和滚动统计)
    metric_seq = []
    for r in rows:
        v = r.get(metric)
        metric_seq.append(float(v) if v is not None else 0.0)

    X, y = [], []
    for i in range(LAG_WINDOW, len(rows) - 1):
        r = rows[i]
        r_next = rows[i + 1]
        if r.get("recorded_at") is None:
            continue
        t_sec = _to_seconds(r["recorded_at"], t0)
        # 1. 时间 sin/cos 编码(消除大数值 + 捕捉日内周期)
        sin_t, cos_t = _encode_time_cyclic(t_sec)
        # 2. 滞后窗口 [t-W .. t](共 W+1 个)
        lag = list(metric_seq[i - LAG_WINDOW : i + 1])
        # 3. 差分 Δy(变化率,反映趋势加速度)
        diffs = []
        for d in range(DIFF_ORDERS):
            idx = i - d
            if idx - 1 >= 0:
                diffs.append(metric_seq[idx] - metric_seq[idx - 1])
            else:
                diffs.append(0.0)
        # 4. 滚动统计(过去 ROLLING_WINDOW 步的均值/标准差,反映局部波动幅度)
        wv = metric_seq[max(0, i - ROLLING_WINDOW + 1) : i + 1]
        roll_mean = float(np.mean(wv)) if wv else 0.0
        roll_std = float(np.std(wv)) if wv else 0.0
        # 5. 其他变量当前值(辅助多变量信息)
        other = [float(r.get(c) or 0) for c in other_cols]
        # 目标:残差 Δy = next - current(让模型学变化量而非绝对值)
        cur_val = metric_seq[i]
        next_val = r_next.get(metric)
        if next_val is None:
            continue
        delta_y = float(next_val) - cur_val
        # 组装特征:[时间编码, 滞后, 差分, 滚动统计, 其他变量]
        feat = [sin_t, cos_t] + lag + diffs + [roll_mean, roll_std] + other
        X.append(feat)
        y.append(delta_y)

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
    if model_name not in ("linear", "svr", "knn", "rf"):
        return {"error": "model_name 必须为 linear/svr/knn/rf"}

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
    # SVR 线性核(支持趋势外推) / KNN 模式匹配(复现波动) / RF 非线性拟合 / Linear 基线
    if model_name == "svr":
        base = SVR(kernel="linear", C=1.0)
    elif model_name == "knn":
        base = KNeighborsRegressor(n_neighbors=5, weights="distance", algorithm="auto")
    elif model_name == "rf":
        base = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42)
    else:
        base = LinearRegression()

    # SVR 和 KNN 对特征尺度敏感,使用标准化;RF 和 Linear 不需要
    needs_scaler = model_name in ("svr", "knn")
    if needs_scaler:
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        base.fit(X_train_s, y_train)
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
    # 用最后一条记录的时间作为基准(X 第一列现在是 sin_t 而非 t_sec)
    last_row = rows[-1] if rows else None
    last_dt = last_row["recorded_at"] if last_row and last_row.get("recorded_at") else t0
    last_t_sec = _to_seconds(last_dt, t0) if last_dt else 0.0

    # 用每个 metric 的最新读数作为外推起点
    last_temp = float(rows[-1].get("temperature") or 0) if rows else 0
    last_hum = float(rows[-1].get("humidity") or 0) if rows else 0
    last_light = float(rows[-1].get("light") or 0) if rows else 0

    # 非目标变量(与 _build_features 一致)
    other_cols = [c for c in ("temperature", "humidity", "light") if c != metric]

    # 清洗后的历史序列(用于构造 lag/diffs/roll 特征),保留足够长的尾部
    rows_clean = _clean_outliers(rows, metric)
    hist_seq = []
    for r in rows_clean:
        v = r.get(metric)
        hist_seq.append(float(v) if v is not None else 0.0)
    # 只保留尾部足够构造特征的长度
    keep_len = LAG_WINDOW + max(DIFF_ORDERS, ROLLING_WINDOW) + 2
    hist_seq = hist_seq[-keep_len:] if len(hist_seq) > keep_len else hist_seq

    # 其他变量当前值(目标 metric 用预测值更新,其他保持最新真实值)
    cur_vals = {"temperature": last_temp, "humidity": last_hum, "light": last_light}

    # 生成预测时间点:每步 = 一个采样间隔(10min),根据 horizon 动态生成
    num_steps = max(1, horizon_minutes // SAMPLE_INTERVAL_MIN)
    steps = [SAMPLE_INTERVAL_MIN * i for i in range(1, num_steps + 1)]

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

    # 递归多步预测 + 残差学习:模型输出 Δy,yhat = cur + Δy
    for m in steps:
        future_t_sec = last_t_sec + m * 60
        # 1. 时间 sin/cos 编码
        sin_t, cos_t = _encode_time_cyclic(future_t_sec)
        # 2. 滞后窗口 [t-W .. t](从 hist_seq 尾部取)
        i = len(hist_seq) - 1
        lag = list(hist_seq[i - LAG_WINDOW : i + 1])
        # 3. 差分 Δy(变化率)
        diffs = []
        for d in range(DIFF_ORDERS):
            idx = i - d
            if idx - 1 >= 0:
                diffs.append(hist_seq[idx] - hist_seq[idx - 1])
            else:
                diffs.append(0.0)
        # 4. 滚动统计
        wv = hist_seq[max(0, i - ROLLING_WINDOW + 1) : i + 1]
        roll_mean = float(np.mean(wv)) if wv else 0.0
        roll_std = float(np.std(wv)) if wv else 0.0
        # 5. 其他变量当前值
        other_now = [cur_vals[c] for c in other_cols]
        # 组装特征:[sin, cos, lag, diffs, roll, other]
        feat = np.array([[sin_t, cos_t] + lag + diffs + [roll_mean, roll_std] + other_now], dtype=float)
        feat_t = predict_features(feat)
        # 残差预测:模型输出 Δy
        delta = float(base.predict(feat_t)[0])
        # yhat = 当前值 + Δy(残差学习,让模型学变化量,波动更贴合)
        cur_val = hist_seq[-1]
        yhat = cur_val + delta
        # 滑动历史序列(供下一步构造特征)
        hist_seq.append(yhat)
        cur_vals[metric] = yhat

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
