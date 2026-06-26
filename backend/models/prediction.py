# -*- coding: utf-8 -*-
"""预测表(温度/湿度/光照)。

每次触发预测时,后端拉取最近 N 条历史数据,
即时训练模型并预测未来若干时间点,结果写入此表。
"""
from extensions import db

METRICS = ("temperature", "humidity", "light")
MODELS = ("linear", "svr")


class Prediction(db.Model):
    __tablename__ = "predictions"
    __table_args__ = (
        db.Index("idx_dev_metric_time", "device_id", "metric", "predicted_at"),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    device_id = db.Column(db.BigInteger, db.ForeignKey("devices.id"), nullable=False)
    metric = db.Column(db.Enum("temperature", "humidity", "light"), nullable=False)
    horizon_minutes = db.Column(db.Integer, nullable=False, default=30)
    predicted_values = db.Column(db.JSON, nullable=False)
    history_snapshot = db.Column(db.JSON, nullable=True)
    model_name = db.Column(db.String(64), nullable=False)
    mae = db.Column(db.Float, nullable=True)
    r2 = db.Column(db.Float, nullable=True)
    predicted_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "device_id": self.device_id,
            "metric": self.metric,
            "horizon_minutes": self.horizon_minutes,
            "predicted_values": self.predicted_values or {},
            "history_snapshot": self.history_snapshot or {},
            "model_name": self.model_name,
            "mae": self.mae,
            "r2": self.r2,
            "predicted_at": self.predicted_at.strftime("%Y-%m-%d %H:%M:%S") if self.predicted_at else None,
        }
