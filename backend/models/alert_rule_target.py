# -*- coding: utf-8 -*-
"""预警规则-设备绑定关联表。

一条规则可绑定多个网关或设备:
- device_id 为 NULL:表示绑定该网关下所有设备(含未来新增)
- device_id 非 NULL:表示仅绑定该具体设备

由 alert_engine 在评估时按 (rule, 当前设备) 过滤命中。
"""
from extensions import db


class AlertRuleTarget(db.Model):
    __tablename__ = "alert_rule_targets"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    rule_id = db.Column(db.BigInteger, db.ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False)
    gateway_id = db.Column(db.BigInteger, db.ForeignKey("gateways.id", ondelete="CASCADE"), nullable=False)
    # device_id 为 NULL 表示"绑定该网关下所有设备"
    device_id = db.Column(db.BigInteger, db.ForeignKey("devices.id", ondelete="CASCADE"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "gateway_id": self.gateway_id,
            "device_id": self.device_id,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }
