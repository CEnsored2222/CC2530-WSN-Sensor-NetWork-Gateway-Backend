# -*- coding: utf-8 -*-
"""MQTT 客户端封装。
职责:
1. 连接 EMQX,订阅本网关的下行主题(register/resp、device/+/cmd、subscription)
2. 提供上行发布方法(register/discovery/temperature/.../heartbeat)
3. 处理下行消息:审批结果、控制指令、订阅配置

兼容 paho-mqtt 1.x 与 2.x(使用可变参数签名)。"""
import json
import socket
import threading
import time

import paho.mqtt.client as mqtt

import config
from state import gateway_state


def _now() -> int:
    return int(time.time())


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class GatewayMqttClient:
    def __init__(self, gw_uuid: str, cmd_handler=None, subscription_handler=None,
                 register_resp_handler=None):
        """
        :param gw_uuid: 网关 UUID
        :param cmd_handler: 下行控制指令回调 callback(dev_mac, cmd, value)
        :param subscription_handler: 订阅配置回调 callback(enabled_metrics:set or None)
        :param register_resp_handler: 审批结果回调 callback(result, user_id)
        """
        self.gw_uuid = gw_uuid
        self._cmd_handler = cmd_handler
        self._sub_handler = subscription_handler
        self._reg_resp_handler = register_resp_handler

        # 订阅指标开关:None 表示全开(默认),收到 subscription 后设为具体集合
        self._enabled_metrics = None
        self._metrics_lock = threading.Lock()

        self._client = mqtt.Client(client_id=f"gateway-{gw_uuid}")
        if config.EMQX_USERNAME:
            self._client.username_pw_set(config.EMQX_USERNAME, config.EMQX_PASSWORD)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    # ---------- 连接/断开 ----------
    def connect(self):
        self._client.connect(config.EMQX_HOST, config.EMQX_PORT, config.EMQX_KEEPALIVE)

    def loop_start(self):
        self._client.loop_start()

    def loop_stop(self):
        self._client.loop_stop()

    def disconnect(self):
        self._client.disconnect()

    # ---------- 主题构造 ----------
    def _gw_topic(self, suffix: str) -> str:
        return f"{config.TOPIC_PREFIX}/{self.gw_uuid}/{suffix}"

    def _dev_topic(self, dev_mac: str, metric_topic: str) -> str:
        return f"{config.TOPIC_PREFIX}/{self.gw_uuid}/device/{dev_mac}/{metric_topic}"

    # ---------- 订阅指标过滤 ----------
    def is_metric_enabled(self, metric_name: str) -> bool:
        """根据订阅配置判断某指标是否允许发布。"""
        with self._metrics_lock:
            if self._enabled_metrics is None:
                return True
            return metric_name in self._enabled_metrics

    def _set_enabled_metrics(self, metrics):
        with self._metrics_lock:
            self._enabled_metrics = set(metrics) if metrics else None

    # ---------- 回调 ----------
    def _on_connect(self, client, userdata, flags, rc, *args):
        # paho 2.x rc 为 ReasonCode,2.x/1.x 均可判断真值
        ok = (str(rc) == "0" or str(rc).upper() == "SUCCESS" or int(getattr(rc, "value", 0)) == 0)
        if ok:
            print("[MQTT] 已连接 EMQX")
            # 订阅下行主题
            topics = [
                self._gw_topic("register/resp"),
                self._gw_topic("device/+/cmd"),
                self._gw_topic("subscription"),
            ]
            for t in topics:
                client.subscribe(t, qos=1)
                print(f"[MQTT] 订阅 {t}")
        else:
            print(f"[MQTT] 连接失败 rc={rc}")

    def _on_disconnect(self, client, userdata, rc, *args):
        print(f"[MQTT] 断开连接 rc={rc},将自动重连")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            print(f"[MQTT] 解析消息失败 topic={msg.topic} err={e}")
            return

        topic = msg.topic
        try:
            if topic.endswith("/register/resp"):
                self._handle_register_resp(payload)
            elif topic.endswith("/cmd"):
                self._handle_cmd(topic, payload)
            elif topic.endswith("/subscription"):
                self._handle_subscription(payload)
            else:
                print(f"[MQTT] 未知主题 {topic}")
        except Exception as e:
            print(f"[MQTT] 处理消息异常 topic={topic} err={e}")

    def _handle_register_resp(self, payload):
        result = payload.get("result")
        user_id = payload.get("user_id")
        if result == "approved":
            gateway_state.set_approved(True)
            print(f"[MQTT] 网关已审批通过,绑定用户 user_id={user_id}")
        elif result == "revoked":
            gateway_state.set_approved(False)
            print("[MQTT] 网关审批已被撤销,停止业务数据转发")
        if self._reg_resp_handler:
            self._reg_resp_handler(result, user_id)
        else:
            print(f"[MQTT] 网关审批结果: {result}")

    def _handle_cmd(self, topic, payload):
        # topic: .../device/{dev_mac}/cmd
        parts = topic.split("/")
        dev_mac = parts[-2] if len(parts) >= 2 else ""
        cmd = payload.get("cmd")
        value = payload.get("value")
        print(f"[MQTT] 收到下行指令 dev={dev_mac} cmd={cmd} value={value}")
        if self._cmd_handler:
            self._cmd_handler(dev_mac, cmd, value)

    def _handle_subscription(self, payload):
        metrics = payload.get("metrics")
        self._set_enabled_metrics(metrics)
        if self._sub_handler:
            self._sub_handler(self._enabled_metrics)
        print(f"[MQTT] 订阅配置更新 enabled={self._enabled_metrics}")

    # ---------- 上行发布 ----------
    def _publish(self, topic, payload, qos=0, retain=False):
        self._client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=qos, retain=retain)

    def _publish_dev(self, dev_mac, metric_name, topic_suffix, value, qos=0, retain=False):
        """带订阅过滤的设备数据发布。"""
        if not self.is_metric_enabled(metric_name):
            return  # 该指标已被后端取消订阅,网关不再转发
        self._publish(self._dev_topic(dev_mac, topic_suffix),
                      {"value": value, "ts": _now()}, qos=qos, retain=retain)

    def publish_register(self):
        payload = {
            "gw_uuid": self.gw_uuid,
            "hostname": socket.gethostname(),
            "ip": _get_local_ip(),
            "ts": _now(),
        }
        self._publish(self._gw_topic("register"), payload, qos=1, retain=False)
        print("[MQTT] 已发布注册请求,等待后端审批...")

    def publish_discovery(self, dev_mac):
        self._publish(self._dev_topic(dev_mac, "discovery"),
                      {"dev_mac": dev_mac, "ts": _now()},
                      qos=1, retain=True)
        print(f"[MQTT] 发布设备发现 {dev_mac}")

    def publish_temperature(self, dev_mac, value):
        self._publish_dev(dev_mac, "temperature", "temperature", value)

    def publish_humidity(self, dev_mac, value):
        self._publish_dev(dev_mac, "humidity", "humidity", value)

    def publish_light(self, dev_mac, value):
        self._publish_dev(dev_mac, "light", "light", value)

    def publish_led(self, dev_mac, value):
        self._publish_dev(dev_mac, "led_status", "led", value)

    def publish_status(self, dev_mac, status_str):
        # status_str: "active" 或 "sleep"
        # 设备状态统一由本地网关通过 status 主题上报
        # 触发来源:
        #   1. 新 MAC 出现 → active(serial_reader._on_new_mac)
        #   2. 5s 内无新数据 → sleep(mac_registry 超时回调)
        #   3. STATUS 控制指令成功反馈 → active/sleep(serial_reader._handle_feedback)
        self._publish_dev(dev_mac, "device_status", "status", status_str)

    def publish_heartbeat(self):
        self._publish(self._gw_topic("heartbeat"),
                      {"gw_uuid": self.gw_uuid, "ts": _now()},
                      qos=0, retain=False)
