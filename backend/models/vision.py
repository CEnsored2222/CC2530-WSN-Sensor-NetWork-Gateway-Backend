# -*- coding: utf-8 -*-
"""视觉模块数据模型:face_library 人脸库表。

字段与设计文档第 5.2 节一致:
    id / user_id / name / embedding(LONGBLOB) / sample_snapshot / created_at
    UNIQUE(user_id, name)  同一用户姓名不重复
    FK user_id → users.id ON DELETE CASCADE

to_dict() 不返回 embedding 原始向量(避免泄露生物特征)。
"""
from extensions import db


class FaceLibrary(db.Model):
    __tablename__ = "face_library"
    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="uk_user_name"),
        db.Index("idx_user", "user_id"),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.BigInteger,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="注册者",
    )
    name = db.Column(db.String(64), nullable=False, comment="姓名")
    embedding = db.Column(
        db.LargeBinary,
        nullable=False,
        comment="insightface 512 维特征向量(序列化)",
    )
    sample_snapshot = db.Column(db.Text, nullable=True, comment="注册样张 base64")
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    def to_dict(self, include_snapshot=True):
        """转 dict。

        Args:
            include_snapshot: 是否返回 sample_snapshot(列表场景可关闭以减小体积)
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "sample_snapshot": self.sample_snapshot if include_snapshot else None,
            "created_at": self.created_at.strftime("%Y-%m-%dT%H:%M:%S") if self.created_at else None,
        }
