# -*- coding: utf-8 -*-
"""网关配置:所有参数均可通过环境变量覆盖"""
import os
import sys


def _app_dir() -> str:
    """获取可执行文件/脚本所在目录(PyInstaller 打包后也能正确返回)。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包的单文件 EXE
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


# ============ EMQX 配置 ============
EMQX_HOST = os.getenv("EMQX_HOST", "127.0.0.1")
EMQX_PORT = int(os.getenv("EMQX_PORT", "1883"))
EMQX_USERNAME = os.getenv("EMQX_USERNAME", "")
EMQX_PASSWORD = os.getenv("EMQX_PASSWORD", "")
EMQX_KEEPALIVE = int(os.getenv("EMQX_KEEPALIVE", "60"))

# ============ 串口配置 ============
SERIAL_PORT = os.getenv("SERIAL_PORT", "COM1")
SERIAL_BAUDRATE = int(os.getenv("SERIAL_BAUDRATE", "38400"))

# ============ 网关标识 ============
GW_UUID_FILE = os.path.join(_app_dir(), "gw_uuid.txt")

# ============ 主题 ============
TOPIC_PREFIX = "smart_home/gateway"

# 订阅指标名 -> 业务主题后缀 的映射
# 订阅管理表用指标名(led_status/device_status),MQTT 主题用简短后缀(led/status)
METRIC_TO_TOPIC = {
    "temperature": "temperature",
    "humidity": "humidity",
    "light": "light",
    "led_status": "led",
    "device_status": "status",
}

# ============ 定时参数 ============
MAC_TIMEOUT_SECONDS = int(os.getenv("MAC_TIMEOUT_SECONDS", "5"))  # 设备 MAC 无数据超时(秒)
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "30"))   # 网关心跳间隔(秒)
