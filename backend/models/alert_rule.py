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
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_by = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    def to_dict(self):
        return {
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
            "enabled": bool(self.enabled),
            "created_by": self.created_by,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }
