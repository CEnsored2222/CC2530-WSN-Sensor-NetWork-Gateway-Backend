# -*- coding: utf-8 -*-
"""MLP PyTorch 网络结构定义。

全面增强特征工程(时间编码 + 滞后窗口 + 差分 + 滚动统计 + 残差学习):
  TempHumModel: 输入 30 维
    [sin_t, cos_t,
     temp 的 9 滞后 + 3 差分 + 2 滚动,
     hum 的 9 滞后 + 3 差分 + 2 滚动]
    → 输出 2 维 [Δtemp, Δhum](残差)
  LightModel: 输入 16 维
    [sin_t, cos_t,
     light 的 9 滞后 + 3 差分 + 2 滚动]
    → 输出 1 维 [Δlight](残差)

网络结构(约 3-4K 参数):
  Linear(in,64) → BatchNorm1d → ReLU → Dropout(0.05)
  → Linear(64,64) → BatchNorm1d → ReLU → Dropout(0.05)
  → Linear(64,32) → BatchNorm1d → ReLU
  → Linear(32, out)
"""
import torch
import torch.nn as nn

# ===== 特征工程常量(与 predictor.py 保持一致)=====
LAG_WINDOW = 8          # 滞后窗口(过去 8+1=9 个时间点)
DIFF_ORDERS = 3         # 差分阶数(3 个变化率)
ROLLING_WINDOW = 5      # 滚动统计窗口
# 每个输出列的特征数:滞后(LAG+1) + 差分(DIFF) + 滚动统计(2)
PER_COL_FEATURES = (LAG_WINDOW + 1) + DIFF_ORDERS + 2
# 直接多步输出:一次输出 6 步预测(避免递归多步的平滑效应,保留波形)
NUM_FORECAST_STEPS = 6


class _MLPBase(nn.Module):
    """MLP 基类:共享网络结构,子类指定 input_dim / output_dim。"""

    def __init__(self, input_dim, output_dim):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(0.05),
            nn.Linear(64, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(0.05),
            nn.Linear(64, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Linear(32, output_dim),
        )

    def forward(self, x):
        return self.net(x)


class TempHumModel(_MLPBase):
    """温湿度模型:输入 30 维 → 输出 12 维(6 步 × 2 列,直接多步)。"""

    def __init__(self):
        input_dim = 2 + PER_COL_FEATURES * 2
        # 输出:NUM_FORECAST_STEPS(6 步) × 2 列(temp+hum) = 12
        super().__init__(input_dim=input_dim, output_dim=NUM_FORECAST_STEPS * 2)


class LightModel(_MLPBase):
    """光照模型:输入 16 维 → 输出 6 维(6 步 × 1 列,直接多步)。"""

    def __init__(self):
        input_dim = 2 + PER_COL_FEATURES
        # 输出:NUM_FORECAST_STEPS(6 步) × 1 列(light) = 6
        super().__init__(input_dim=input_dim, output_dim=NUM_FORECAST_STEPS * 1)


# model_type → 模型类映射
MODEL_CLASSES = {
    "mlp_temp_hum": TempHumModel,
    "mlp_light": LightModel,
}

# model_type → 输入特征列名(与 X 矩阵列顺序严格一致)
# 列顺序:[sin_t, cos_t, <col_0 的 滞后+差分+滚动>, <col_1 的 ...>, ...]
def _build_input_columns(model_type):
    out_cols = _OUTPUT_COLUMNS[model_type]
    cols = ["sin_t", "cos_t"]
    for col in out_cols:
        # 滞后
        for w in range(LAG_WINDOW + 1):
            cols.append(f"{col}_lag{w}" if w > 0 else col)
        # 差分
        for d in range(DIFF_ORDERS):
            cols.append(f"d_{col}_{d}")
        # 滚动统计
        cols.append(f"{col}_roll_mean")
        cols.append(f"{col}_roll_std")
    return cols


# model_type → 输出列名(与 y 矩阵列顺序 / ONNX 输出张量列顺序严格一致)
_OUTPUT_COLUMNS = {
    "mlp_temp_hum": ["temperature", "humidity"],
    "mlp_light": ["light"],
}

_INPUT_COLUMNS = {mt: _build_input_columns(mt) for mt in _OUTPUT_COLUMNS}
