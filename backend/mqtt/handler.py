# -*- coding: utf-8 -*-
"""MQTT 消息分发处理。

收到报文后:
- register:落库网关(status=pending),WS 广播 gateway_pending 给所有用户
- heartbeat:更新网关 last_seen
- discovery:落库设备(不存在则建),WS 推送 device_discovered 给绑定用户
- 数据类(temp/hum/light/led/status):更新 data_buffer + 实时 WS 推送 sensor_data

状态管理统一:
- led_status / device_status 仅在 data_buffer 内存缓冲中保留,不入 sensor_data 表
- flush 入库时只写 temperature/humidity/light(去空+去重),状态字段不落库
- 前端通过 sensor_data WS 事件中的 led_status/device_status 获取实时状态
- 指令反馈由本地网关解析后通过 led/status 主题上报(feedback 主题已删除)

所有 DB 操作在 app context 中执行(on_message 运行于 paho 线程)。"""
import json
import re
from datetime import datetime

from extensions import db, socketio
import extensions
from models.gateway import Gateway
from models.device import Device
from models.subscription import Subscription
from mqtt import topics
from services.alert_engine import alert_engine

_REGISTER_RE = re.compile(rf"^{topics.TOPIC_PREFIX}/([^/]+)/register$")
_HEARTBEAT_RE = re.compile(rf"^{topics.TOPIC_PREFIX}/([^/]+)/heartbeat$")
_DEVICE_RE = re.compile(rf"^{topics.TOPIC_PREFIX}/([^/]+)/device/([^/]+)/([^/]+)$")


class MqttHandler:
    def __init__(self, app):
        self.app = app
        self._enabled_metrics = None  # 缓存已启用指标集合,None 表示未加载

    def refresh_enabled_metrics(self):
        """刷新已启用指标缓存(订阅切换后调用)。"""
        with self.app.app_context():
            self._enabled_metrics = {s.metric for s in Subscription.query.filter_by(subscribed=True).all()}

    def _get_enabled_metrics(self):
        """获取已启用指标集合(惰性加载 + 缓存)。"""
        if self._enabled_metrics is None:
            self.refresh_enabled_metrics()
        return self._enabled_metrics

    def on_message(self, client, userdata, msg):
        with self.app.app_context():
            try:
                self._dispatch(msg.topic, msg.payload)
            except Exception as e:
                print(f"[MQTT] 处理异常 topic={msg.topic} err={e}")

    def _dispatch(self, topic_str, payload):
        try:
            data = json.loads(payload.decode("utf-8"))
        except Exception:
            data = {}

        m = _REGISTER_RE.match(topic_str)
        if m:
            self._handle_register(m.group(1), data)
            return
        m = _HEARTBEAT_RE.match(topic_str)
        if m:
            self._handle_heartbeat(m.group(1), data)
            return
        m = _DEVICE_RE.match(topic_str)
        if m:
            gw_uuid, mac, suffix = m.group(1), m.group(2), m.group(3)
            if suffix == "discovery":
                self._handle_discovery(gw_uuid, mac, data)
            elif suffix in topics.TOPIC_SUFFIX_TO_FIELD:
                self._handle_data(gw_uuid, mac, suffix, data)
            return

    # ---------- 网关 ----------
    def _handle_register(self, gw_uuid, data):
        gw = Gateway.query.filter_by(gw_uuid=gw_uuid).first()
        if gw is None:
            gw = Gateway(
                gw_uuid=gw_uuid,
                hostname=data.get("hostname"),
                ip=data.get("ip"),
                status="pending",
            )
            db.session.add(gw)
            db.session.commit()
            print(f"[MQTT] 新网关注册请求 {gw_uuid} ({gw.hostname})")
        else:
            gw.hostname = data.get("hostname", gw.hostname)
            gw.ip = data.get("ip", gw.ip)
            gw.last_seen = datetime.now()
            # 解绑后重新上线:从 offline 回到 pending,重新等待审批
            if gw.status in ("offline", "rejected") and gw.user_id is None:
                gw.status = "pending"
            db.session.commit()

        # 已绑定用户的网关重启后自动重发审批结果,无需用户再次审批
        # 注意:运行中网关 status 为 online(心跳更新),所以用 user_id 判断而非 status
        if gw.user_id is not None and gw.status in ("approved", "online"):
            extensions.mqtt_client.publish(
                topics.register_resp_topic(gw_uuid),
                {"gw_uuid": gw_uuid, "result": "approved",
                 "user_id": gw.user_id, "ts": int(datetime.now().timestamp())},
                qos=1,
            )
            print(f"[MQTT] 已绑定网关 {gw_uuid} 重启,自动重发审批结果")
            return

        # 广播给所有在线用户(待审网关任何用户都可认领)
        socketio.emit("gateway_pending", {
            "gw_uuid": gw_uuid,
            "hostname": gw.hostname,
            "ip": gw.ip,
            "ts": data.get("ts"),
        })

    def _handle_heartbeat(self, gw_uuid, data):
        gw = Gateway.query.filter_by(gw_uuid=gw_uuid).first()
        if gw:
            gw.last_seen = datetime.now()
            if gw.status == "approved":
                gw.status = "online"
            db.session.commit()

    # ---------- 设备 ----------
    def _get_or_create_device(self, gw, mac, dev_type=None):
        dev = Device.query.filter_by(gateway_id=gw.id, mac=mac).first()
        if dev is None:
            # dev_type 现在应为 list(如 ["temperature"]),若非 list 则忽略
            t = dev_type if isinstance(dev_type, list) else None
            dev = Device(gateway_id=gw.id, mac=mac, type=t, bound=False)
            db.session.add(dev)
            db.session.commit()
            print(f"[MQTT] 新设备发现 gw={gw.gw_uuid} mac={mac}")
        return dev

    def _handle_discovery(self, gw_uuid, mac, data):
        gw = Gateway.query.filter_by(gw_uuid=gw_uuid).first()
        if not gw:
            return
        dev = self._get_or_create_device(gw, mac)
        if gw.user_id:
            socketio.emit("device_discovered", {"device": dev.to_dict()},
                          room=f"user_{gw.user_id}")

    # ---------- 设备类型推断 ----------
    # device.type 现在是一个 JSON 数组,存储该设备可采集的指标列表。
    # 例如温湿度传感器: ["temperature", "humidity"]
    # 后端根据收到的数据报文动态累积推断,不依赖网关上报的静态类型。
    _DATA_SUFFIX_FIELDS = {
        "temperature": "temperature",
        "humidity":  "humidity",
        "light": "light",
    }

    def _infer_device_type(self, dev, suffix):
        """根据历史上报数据类型累积推断设备 type。

        Returns:
            list | None: 推断出的指标列表(如 ["temperature","humidity"]);若 suffix 不属于数据类型,返回 None
        """
        field = self._DATA_SUFFIX_FIELDS.get(suffix)
        if not field:
            return None
        existing = list(dev.type) if dev.type else []
        if field not in existing:
            existing.append(field)
        order = ["temperature", "humidity", "light"]
        existing = [x for x in order if x in existing]
        return existing if existing else None

    def _handle_data(self, gw_uuid, mac, suffix, data):
        gw = Gateway.query.filter_by(gw_uuid=gw_uuid).first()
        if not gw or not gw.user_id:
            return  # 未绑定用户的网关数据不处理
        dev = self._get_or_create_device(gw, mac)
        dev.last_seen = datetime.now()

        # 根据收到的数据类型动态推断并更新设备 type
        # 累积设备可上报的数据类型(温度/湿度/光照),不包含 LED/状态等控制字段
        new_type = self._infer_device_type(dev, suffix)
        if new_type is not None and sorted(dev.type or []) != sorted(new_type):
            dev.type = new_type
        db.session.commit()

        field = topics.TOPIC_SUFFIX_TO_FIELD[suffix]
        value = data.get("value")
        if field == "led_status":
            value = bool(value)
        ts = data.get("ts")

        # 缓冲并取该设备最新全部字段
        rec = extensions.data_buffer.update(dev.id, **{field: value, "_ts": ts})

        # 实时推送(不入库):按订阅表过滤已关闭的指标(使用缓存)
        enabled = self._get_enabled_metrics()
        _FIELD_TO_METRIC = {
            "temperature": "temperature", "humidity": "humidity", "light": "light",
            "led_status": "led_status", "device_status": "device_status",
        }
        payload = {
            "device_id": dev.id,
            "gw_uuid": gw_uuid,
            "dev_mac": mac,
            "device_name": dev.name,
            "device_type": dev.type,
            "ts": ts,
        }
        for f, m in _FIELD_TO_METRIC.items():
            val = rec.get(f)
            payload[f] = val if m in enabled else None

        socketio.emit("sensor_data", payload, room=f"user_{gw.user_id}")

        # 告警引擎:对当前设备最新字段集合评估启用规则
        try:
            alert_engine.evaluate(
                device_id=dev.id,
                user_id=gw.user_id,
                payload=rec,
                dev_mac=mac,
                ts=ts,
            )
        except Exception as e:
            print(f"[Alert] 评估异常 dev={mac} err={e}")
