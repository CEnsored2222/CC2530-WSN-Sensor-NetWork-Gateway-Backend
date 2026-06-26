# -*- coding: utf-8 -*-
"""告警引擎:规则匹配 + 告警记录写入 + WebSocket 推送。

匹配逻辑:
- 单条件 (logic='none'): 仅判断 metric operator threshold
- 组合条件 (logic='and'/'or'): 主条件 logic 第二指标 second_operator second_threshold

规则按用户隔离:仅评估属于"设备所属用户"的启用规则。
设备绑定过滤:规则通过 alert_rule_targets 绑定到网关/设备。
- target.device_id 为 NULL:绑定该网关下所有设备(含未来新增)
- target.device_id 非 NULL:仅绑定该具体设备
只有设备命中的规则才会评估。

命中后:
- 写 operation_logs(action=alert)
- WebSocket 推送给规则所属用户(user_{user_id})
- 若规则 notify=True,额外推送 alert_notify 事件触发右下角弹窗

为避免同一规则对同一设备的高频重复告警,对 (rule_id, device_id) 做 60s 节流。
"""
import json
import threading
import time
from datetime import datetime

from sqlalchemy.orm import joinedload

from extensions import db, socketio
from models.alert_rule import AlertRule
from models.device import Device
from models.operation_log import OperationLog


_OPS = {
    "gt":  lambda a, b: a is not None and a > b,
    "lt":  lambda a, b: a is not None and a < b,
    "gte": lambda a, b: a is not None and a >= b,
    "lte": lambda a, b: a is not None and a <= b,
    "eq":  lambda a, b: a is not None and a == b,
}


class AlertEngine:
    def __init__(self):
        self._lock = threading.Lock()
        # 节流: {(rule_id, device_id): last_alert_ts}
        self._recent = {}
        self._throttle_seconds = 60
        # 规则缓存按 user_id 分桶: {user_id: (rules, cache_ts)}
        self._rules_cache = {}
        self._cache_ttl = 5  # 5s 缓存

    def _load_user_rules(self, user_id):
        """加载某用户的启用规则(含 targets),带缓存。"""
        now = time.time()
        cache = self._rules_cache.get(user_id)
        if cache is None or now - cache[1] > self._cache_ttl:
            rules = (
                AlertRule.query
                .options(joinedload(AlertRule.targets))
                .filter_by(enabled=True, user_id=user_id)
                .all()
            )
            self._rules_cache[user_id] = (rules, now)
            cache = (rules, now)
        return cache[0]

    def invalidate_cache(self):
        self._rules_cache = {}

    def _rule_matches_device(self, rule, device_id, gateway_id):
        """规则的设备绑定是否包含当前设备。"""
        if not rule.targets:
            return False  # 无绑定则不触发
        for t in rule.targets:
            if t.device_id is not None:
                # 设备级绑定
                if t.device_id == device_id:
                    return True
            else:
                # 网关级绑定:该网关下所有设备
                if t.gateway_id == gateway_id:
                    return True
        return False

    def _match(self, rule, payload):
        """判断规则是否命中。"""
        primary_val = payload.get(rule.metric)
        primary_hit = _OPS[rule.operator](primary_val, float(rule.threshold))

        if rule.logic == "none" or not rule.second_metric:
            return primary_hit, primary_val

        second_val = payload.get(rule.second_metric)
        second_hit = _OPS[rule.second_operator](second_val, float(rule.second_threshold))

        if rule.logic == "and":
            hit = primary_hit and second_hit
        else:  # or
            hit = primary_hit or second_hit
        # 命中值取主指标值用于展示
        return hit, primary_val

    def evaluate(self, device_id, user_id, payload, dev_mac=None, ts=None):
        """对一台设备的最新数据评估该用户名下绑定该设备的启用规则。

        必须在 app context 中调用。
        """
        rules = self._load_user_rules(user_id)
        if not rules:
            return []

        # 查当前设备的 gateway_id,用于网关级绑定匹配
        dev = db.session.get(Device, device_id)
        if not dev:
            return []
        gateway_id = dev.gateway_id

        now = time.time()
        fired = []
        for rule in rules:
            # 设备绑定过滤:规则必须绑定当前设备才评估
            if not self._rule_matches_device(rule, device_id, gateway_id):
                continue

            key = (rule.id, device_id)
            with self._lock:
                last = self._recent.get(key, 0)
                if now - last < self._throttle_seconds:
                    continue

            hit, value = self._match(rule, payload)
            if not hit:
                continue

            with self._lock:
                self._recent[key] = now

            detail = {
                "rule_id": rule.id,
                "rule_name": rule.name,
                "severity": rule.severity,
                "metric": rule.metric,
                "value": float(value) if value is not None else None,
                "device_id": device_id,
                "dev_mac": dev_mac,
                "ts": ts,
                "notify": bool(rule.notify),
            }
            # 写 operation_logs(action=alert)
            db.session.add(OperationLog(
                user_id=user_id,
                action="alert",
                target_type="alert_rule",
                target_id=rule.id,
                detail=json.dumps(detail, ensure_ascii=False),
            ))
            db.session.commit()

            # WebSocket 推送给规则所属用户(== 设备所属用户)
            socketio.emit("alert", detail, room=f"user_{user_id}")
            # 若规则开启通报设置,额外推送 alert_notify 事件触发右下角弹窗
            if rule.notify:
                socketio.emit("alert_notify", detail, room=f"user_{user_id}")
            fired.append(detail)
            print(f"[Alert] 命中规则 #{rule.id} '{rule.name}' severity={rule.severity} "
                  f"dev={dev_mac} {rule.metric}={value}")
        return fired


alert_engine = AlertEngine()
