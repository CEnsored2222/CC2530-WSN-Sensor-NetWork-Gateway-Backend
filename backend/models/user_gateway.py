# -*- coding: utf-8 -*-
"""用户-网关绑定中间表（多对多）"""
from extensions import db


class UserGateway(db.Model):
    __tablename__ = "user_gateways"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id"), nullable=False)
    gateway_id = db.Column(db.BigInteger, db.ForeignKey("gateways.id"), nullable=False)
    name = db.Column(db.String(64), nullable=True, comment="用户自定义网关名称")
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    __table_args__ = (
        db.UniqueConstraint("user_id", "gateway_id", name="uk_user_gateway"),
    )

    user = db.relationship("User", backref="user_gateways")
    gateway = db.relationship("Gateway", backref="user_gateways")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "gateway_id": self.gateway_id,
            "name": self.name,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }
