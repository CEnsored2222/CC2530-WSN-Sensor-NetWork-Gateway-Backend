# -*- coding: utf-8 -*-
"""网关表"""
from extensions import db


class Gateway(db.Model):
    __tablename__ = "gateways"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    gw_uuid = db.Column(db.String(36), unique=True, nullable=False)
    status = db.Column(
        db.Enum("pending", "approved", "rejected", "offline", "online"),
        nullable=False, default="pending",
    )
    hostname = db.Column(db.String(128), nullable=True)
    ip = db.Column(db.String(45), nullable=True)
    last_seen = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    devices = db.relationship("Device", backref="gateway", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "gw_uuid": self.gw_uuid,
            "status": self.status,
            "hostname": self.hostname,
            "ip": self.ip,
            "last_seen": self.last_seen.strftime("%Y-%m-%d %H:%M:%S") if self.last_seen else None,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }
