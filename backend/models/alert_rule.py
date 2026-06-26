# -*- coding: utf-8 -*-
"""预警规则表。

支持单条件阈值与组合条件,分三级 severity(info/warning/critical)。
命中规则后由 alert_engine 写入 operation_logs(action=alert) 并 WebSocket 推送。
"""
from extensions import db


METRICS = ("temperature", "humidity", "light")
OPERATORS = ("gt", "lt", "gte", "lte", "eq")
LOGICS = ("and", "or", "none")
SEVERITIES = ("info", "warning", "critical")


class AlertRule(db.Model):
    __tablename__ = "alert_rules"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(64), nullable=False)
    metric = db.Column(db.Enum(*METRICS), nullable=False)
    operator = db.Column(db.Enum(*OPERATORS), nullable=False)
    threshold = db.Column(db.Numeric(10, 2), nullable=False)
    logic = db.Column(db.Enum(*LOGICS), nullable=False, default="none")
    second_metric = db.Column(db.Enum(*METRICS), nullable=True)
    second_operator = db.Column(db.Enum(*OPERATORS), nullable=True)
    second_threshold = db.Column(db.Numeric(10, 2), nullable=True)
    severity = db.Column(db.Enum(*SEVERITIES), nullable=False, default="warning")
    # 通报设置:为 True 时命中规则会向用户右下角推送通报弹窗(3s 自动消失)
    notify = db.Column(db.Boolean, nullable=False, default=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    # 规则所属用户(触发后只推送给该用户),不许为空
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    # 绑定设备:一对多关联表。device_id 为 NULL 表示绑定该网关下所有设备
    targets = db.relationship(
        "AlertRuleTarget",
        backref="rule",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def to_dict(self, with_targets=True):
        d = {
            "id": self.id,
            "name": self.name,
            "metric": self.metric,
            "operator": self.operator,
            "threshold": float(self.threshold) if self.threshold is not None else None,
            "logic": self.logic,
            "second_metric": self.second_metric,
            "second_operator": self.second_operator,
            "second_threshold": float(self.second_threshold) if self.second_threshold is not None else None,
            "severity": self.severity,
            "notify": bool(self.notify),
            "enabled": bool(self.enabled),
            "user_id": self.user_id,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }
        if with_targets:
            d["targets"] = [t.to_dict() for t in self.targets]
        return d
