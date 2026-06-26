# -*- coding: utf-8 -*-
"""数据表(温度/湿度/光照)
后端订阅采集数据每 60s 入库一次(去空 + 去重)。

注:led_status / device_status 不入库,仅由后端订阅 led/status 主题后
通过 data_buffer 内存缓冲 + WebSocket 直推前端(实时状态管理)。
"""
from extensions import db


class SensorData(db.Model):
    __tablename__ = "sensor_data"
    __table_args__ = (db.Index("idx_device_time", "device_id", "recorded_at"),)

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    device_id = db.Column(db.BigInteger, db.ForeignKey("devices.id"), nullable=False)
    temperature = db.Column(db.Numeric(5, 2), nullable=True)
    humidity = db.Column(db.Numeric(5, 2), nullable=True)
    light = db.Column(db.Integer, nullable=True)
    recorded_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "temperature": float(self.temperature) if self.temperature is not None else None,
            "humidity": float(self.humidity) if self.humidity is not None else None,
            "light": self.light,
            "recorded_at": self.recorded_at.strftime("%Y-%m-%d %H:%M:%S") if self.recorded_at else None,
        }
