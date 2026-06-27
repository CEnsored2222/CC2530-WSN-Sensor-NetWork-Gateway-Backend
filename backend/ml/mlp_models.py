# -*- coding: utf-8 -*-
"""MLP PyTorch 网络结构定义。

TempHumModel: 输入 [t_sec, temperature, humidity](3维) → 输出 [temperature, humidity](2维)
LightModel:   输入 [t_sec, light](2维)               → 输出 [light](1维)

网络结构(约 3-4K 参数):
  Linear(in,64) → BatchNorm1d → ReLU → Dropout(0.05)
  → Linear(64,64) → BatchNorm1d → ReLU → Dropout(0.05)
  → Linear(64,32) → BatchNorm1d → ReLU
  → Linear(32, out)

forward 返回单个 tensor shape=(batch, out),ONNX 导出时 output_names=["output"],
推理后用 _OUTPUT_COLUMNS[model_type] 按列拆分。
"""
import torch
import torch.nn as nn


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
    """温湿度模型:输入 3 维 [t_sec, temperature, humidity] → 输出 2 维 [temperature, humidity]。"""

    def __init__(self):
        super().__init__(input_dim=3, output_dim=2)


class LightModel(_MLPBase):
    """光照模型:输入 2 维 [t_sec, light] → 输出 1 维 [light]。"""

    def __init__(self):
        super().__init__(input_dim=2, output_dim=1)


# model_type → 模型类映射
MODEL_CLASSES = {
    "mlp_temp_hum": TempHumModel,
    "mlp_light": LightModel,
}

# model_type → 输入特征列名(与 X 矩阵列顺序严格一致)
_INPUT_COLUMNS = {
    "mlp_temp_hum": ["t_sec", "temperature", "humidity"],
    "mlp_light": ["t_sec", "light"],
}

# model_type → 输出列名(与 y 矩阵列顺序 / ONNX 输出张量列顺序严格一致)
_OUTPUT_COLUMNS = {
    "mlp_temp_hum": ["temperature", "humidity"],
    "mlp_light": ["light"],
}
