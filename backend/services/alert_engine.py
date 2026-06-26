# -*- coding: utf-8 -*-
"""告警引擎:规则匹配 + 告警记录写入 + WebSocket 推送。

匹配逻辑:
- 单条件 (logic='none'): 仅判断 metric operator threshold
- 组合条件 (logic='and'/'or'): 主条件 logic 第二指标 second_operator second_threshold

每次设备上报数据后调用 evaluate(device_id, user_id, payload),
payload 为该设备最新字段集合 {temperature, humidity, light, led_status, device_status}。

为避免同一规则对同一设备的高频重复告警,对 (rule_id, device_id) 做 60s 节流。
"""
import json
import threading
import time
from datetime import datetime

from extensions import db, socketio
from models.alert_rule import AlertRule
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
        # 缓存启用规则,避免每条数据都查库
        self._rules_cache = None
        self._rules_cache_ts = 0
        self._cache_ttl = 5  # 5s 缓存

    def _load_enabled_rules(self):
        now = time.time()
        if self._rules_cache is None or now - self._rules_cache_ts > self._cache_ttl:
            rules = AlertRule.query.filter_by(enabled=True).all()
            self._rules_cache = rules
            self._rules_cache_ts = now
        return self._rules_cache

    def invalidate_cache(self):
        self._rules_cache = None

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
        """对一台设备的最新数据评估所有启用规则。

        必须在 app context 中调用。
        """
        rules = self._load_enabled_rules()
        if not rules:
            return []

        now = time.time()
        fired = []
        for rule in rules:
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

            # WebSocket 推送给绑定用户
            socketio.emit("alert", detail, room=f"user_{user_id}")
            fired.append(detail)
            print(f"[Alert] 命中规则 #{rule.id} '{rule.name}' severity={rule.severity} "
                  f"dev={dev_mac} {rule.metric}={value}")
        return fired


alert_engine = AlertEngine()
