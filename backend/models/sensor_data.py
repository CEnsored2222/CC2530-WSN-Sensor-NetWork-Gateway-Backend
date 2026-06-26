# -*- coding: utf-8 -*-
"""数据表(温度/湿度/光照/LED状态/设备状态)
后端订阅数据每 10s 入库一次(节流)。"""
from extensions import db


class SensorData(db.Model):
    __tablename__ = "sensor_data"
    __table_args__ = (db.Index("idx_device_time", "device_id", "recorded_at"),)

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    device_id = db.Column(db.BigInteger, db.ForeignKey("devices.id"), nullable=False)
    temperature = db.Column(db.Numeric(5, 2), nullable=True)
    humidity = db.Column(db.Numeric(5, 2), nullable=True)
    light = db.Column(db.Integer, nullable=True)
    led_status = db.Column(db.Boolean, nullable=True)
    device_status = db.Column(db.Enum("active", "sleep"), nullable=True)
    recorded_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "temperature": float(self.temperature) if self.temperature is not None else None,
            "humidity": float(self.humidity) if self.humidity is not None else None,
            "light": self.light,
            "led_status": self.led_status,
            "device_status": self.device_status,
            "recorded_at": self.recorded_at.strftime("%Y-%m-%d %H:%M:%S") if self.recorded_at else None,
        }
