# -*- coding: utf-8 -*-
"""MQTT 主题定义与通配符、指标映射。"""
from config import Config

TOPIC_PREFIX = Config.TOPIC_PREFIX

# 始终订阅的主题(register/discovery/feedback/heartbeat 不受订阅管理控制)
ALWAYS_ON_TOPICS = [
    f"{TOPIC_PREFIX}/+/register",
    f"{TOPIC_PREFIX}/+/device/+/discovery",
    f"{TOPIC_PREFIX}/+/device/+/feedback",
    f"{TOPIC_PREFIX}/+/heartbeat",
]

# 订阅管理可控的指标 -> 通配符主题
METRIC_TOPICS = {
    "temperature": f"{TOPIC_PREFIX}/+/device/+/temperature",
    "humidity": f"{TOPIC_PREFIX}/+/device/+/humidity",
    "light": f"{TOPIC_PREFIX}/+/device/+/light",
    "led_status": f"{TOPIC_PREFIX}/+/device/+/led",
    "device_status": f"{TOPIC_PREFIX}/+/device/+/status",
}

# 主题后缀(从报文主题解析得到)-> data_buffer 字段名
TOPIC_SUFFIX_TO_FIELD = {
    "temperature": "temperature",
    "humidity": "humidity",
    "light": "light",
    "led": "led_status",
    "status": "device_status",
}

# 各指标的 QoS(数据类 QoS0,降低开销)
METRIC_QOS = {
    "temperature": 0, "humidity": 0, "light": 0,
    "led_status": 0, "device_status": 0,
}


def register_resp_topic(gw_uuid: str) -> str:
    return f"{TOPIC_PREFIX}/{gw_uuid}/register/resp"


def cmd_topic(gw_uuid: str, dev_mac: str) -> str:
    return f"{TOPIC_PREFIX}/{gw_uuid}/device/{dev_mac}/cmd"


def subscription_topic(gw_uuid: str) -> str:
    return f"{TOPIC_PREFIX}/{gw_uuid}/subscription"
