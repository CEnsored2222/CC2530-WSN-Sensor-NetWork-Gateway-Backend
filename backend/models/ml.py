# -*- coding: utf-8 -*-
"""MLP 机器学习模型状态表与评估事件表。

ml_models: 固定2行(UPSERT,主键 model_type),记录模型训练/微调状态。
ml_evaluations: 追加INSERT,记录每次评估的新旧模型对比结果。
"""
from extensions import db


class MlModel(db.Model):
    __tablename__ = "ml_models"

    # model_type 作主键,每类型一行(全局模型不绑定 device_id)
    model_type = db.Column(db.Enum("mlp_temp_hum", "mlp_light"), primary_key=True)
    last_train_time = db.Column(db.DateTime, nullable=True,
                                comment="数据分界线:此时间之前=已训练,之后=未训练")
    last_finetune_time = db.Column(db.DateTime, nullable=True,
                                   comment="上次微调成功时间(仅微调成功时更新,用于重启恢复)")
    num_samples_trained = db.Column(db.Integer, default=0,
                                    comment="预训练聚合总样本数(训练集+验证集),微调不更新")
    train_loss = db.Column(db.Float, nullable=True,
                           comment="预训练最终epoch训练集平均loss,微调不更新")
    val_loss = db.Column(db.Float, nullable=True,
                         comment="预训练最终epoch验证集平均loss(早停依据),微调不更新")
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False,
                           server_default=db.func.now(), onupdate=db.func.now())

    def to_dict(self):
        return {
            "model_type": self.model_type,
            "last_train_time": self.last_train_time.strftime("%Y-%m-%d %H:%M:%S") if self.last_train_time else None,
            "last_finetune_time": self.last_finetune_time.strftime("%Y-%m-%d %H:%M:%S") if self.last_finetune_time else None,
            "num_samples_trained": self.num_samples_trained,
            "train_loss": self.train_loss,
            "val_loss": self.val_loss,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }


class MlEvaluation(db.Model):
    __tablename__ = "ml_evaluations"
    __table_args__ = (
        db.Index("idx_model_time", "model_type", "eval_time"),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    model_type = db.Column(db.Enum("mlp_temp_hum", "mlp_light"), nullable=False)
    eval_time = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    new_mae = db.Column(db.Float, nullable=True)
    new_r2 = db.Column(db.Float, nullable=True)
    new_rmse = db.Column(db.Float, nullable=True)
    old_mae = db.Column(db.Float, nullable=True)
    old_r2 = db.Column(db.Float, nullable=True)
    old_rmse = db.Column(db.Float, nullable=True)
    winner = db.Column(db.Enum("new", "old", "tie"), nullable=False)
    data_start = db.Column(db.DateTime, nullable=True)
    data_end = db.Column(db.DateTime, nullable=True)
    num_samples = db.Column(db.Integer, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "model_type": self.model_type,
            "eval_time": self.eval_time.strftime("%Y-%m-%d %H:%M:%S") if self.eval_time else None,
            "new_mae": self.new_mae,
            "new_r2": self.new_r2,
            "new_rmse": self.new_rmse,
            "old_mae": self.old_mae,
            "old_r2": self.old_r2,
            "old_rmse": self.old_rmse,
            "winner": self.winner,
            "data_start": self.data_start.strftime("%Y-%m-%d %H:%M:%S") if self.data_start else None,
            "data_end": self.data_end.strftime("%Y-%m-%d %H:%M:%S") if self.data_end else None,
            "num_samples": self.num_samples,
        }
