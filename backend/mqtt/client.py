# -*- coding: utf-8 -*-
"""MQTT 客户端封装(paho-mqtt)。

- start():后台线程连接 EMQX,失败自动重试;连接成功后订阅默认主题
- subscribe_metric / unsubscribe_metric:订阅管理切换
- publish:下行发布(审批结果/控制指令/订阅配置)
兼容 paho-mqtt 1.x 与 2.x。"""
import json
import threading
import time

import paho.mqtt.client as mqtt

from config import Config
from mqtt import topics


class MqttClient:
    def __init__(self, handler, app):
        self._handler = handler
        self._app = app
        self._client = mqtt.Client(client_id="flask-backend")
        if Config.MQTT_USERNAME:
            self._client.username_pw_set(Config.MQTT_USERNAME, Config.MQTT_PASSWORD)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._on_connect
        self._client.on_message = handler.on_message
        self._connected = False

    # ---------- 连接 ----------
    def _on_connect(self, client, userdata, flags, rc, *args):
        ok = self._is_success(rc)
        if not ok:
            print(f"[MQTT] 连接失败 rc={rc}")
            return
        self._connected = True
        print("[MQTT] 已连接 EMQX,开始订阅主题")
        # 始终订阅
        for t in topics.ALWAYS_ON_TOPICS:
            client.subscribe(t, qos=1)
        # 按订阅表订阅启用的指标
        with self._app.app_context():
            from models.subscription import Subscription
            for sub in Subscription.query.all():
                if sub.subscribed:
                    client.subscribe(topics.METRIC_TOPICS[sub.metric], qos=topics.METRIC_QOS[sub.metric])
        print("[MQTT] 主题订阅完成")

    @staticmethod
    def _is_success(rc) -> bool:
        # 兼容 paho 1.x(int 0) 与 2.x(ReasonCode)
        try:
            return int(rc) == 0
        except (TypeError, ValueError):
            return str(rc).upper() == "SUCCESS"

    def start(self):
        """后台线程连接 EMQX,失败自动重试。"""
        def _retry():
            while True:
                try:
                    self._client.connect(Config.MQTT_HOST, Config.MQTT_PORT, Config.MQTT_KEEPALIVE)
                    self._client.loop_start()
                    print(f"[MQTT] 已连接 {Config.MQTT_HOST}:{Config.MQTT_PORT}")
                    return
                except Exception as e:
                    print(f"[MQTT] 连接失败({Config.MQTT_HOST}:{Config.MQTT_PORT}): {e},3s 后重试")
                    time.sleep(3)
        threading.Thread(target=_retry, daemon=True, name="mqtt-connect").start()

    def stop(self):
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:
            pass

    # ---------- 订阅管理 ----------
    def subscribe_metric(self, metric):
        if self._connected:
            self._client.subscribe(topics.METRIC_TOPICS[metric], qos=topics.METRIC_QOS.get(metric, 0))
            print(f"[MQTT] 订阅指标 {metric}")

    def unsubscribe_metric(self, metric):
        if self._connected:
            self._client.unsubscribe(topics.METRIC_TOPICS[metric])
            print(f"[MQTT] 取消订阅指标 {metric}")

    # ---------- 发布 ----------
    def publish(self, topic, payload, qos=1, retain=False):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, ensure_ascii=False)
        self._client.publish(topic, payload, qos=qos, retain=retain)
