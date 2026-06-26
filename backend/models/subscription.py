# -*- coding: utf-8 -*-
"""订阅管理表(管理员控制后端订阅哪些数据类型)"""
from extensions import db


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    metric = db.Column(
        db.Enum("temperature", "humidity", "light", "led_status", "device_status"),
        unique=True, nullable=False,
    )
    subscribed = db.Column(db.Boolean, nullable=False, default=True)
    updated_by = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "metric": self.metric,
            "subscribed": self.subscribed,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }
