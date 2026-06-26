# -*- coding: utf-8 -*-
"""设备表"""
from extensions import db


class Device(db.Model):
    __tablename__ = "devices"
    __table_args__ = (db.UniqueConstraint("gateway_id", "mac"),)

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    gateway_id = db.Column(db.BigInteger, db.ForeignKey("gateways.id"), nullable=False)
    mac = db.Column(db.String(32), nullable=False)
    name = db.Column(db.String(64), nullable=True)
    type = db.Column(db.JSON, nullable=True, comment="设备可采集的数据类型列表,如['temperature','humidity']")
    bound = db.Column(db.Boolean, nullable=False, default=False)
    last_seen = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "gateway_id": self.gateway_id,
            "mac": self.mac,
            "name": self.name,
            "type": self.type,
            "bound": self.bound,
            "last_seen": self.last_seen.strftime("%Y-%m-%d %H:%M:%S") if self.last_seen else None,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }
