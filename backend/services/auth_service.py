# -*- coding: utf-8 -*-
"""认证服务:注册/登录"""
import bcrypt

from extensions import db
from models.user import User
from utils.auth import encode_token


def register(username, password):
    if not username or not password:
        return None, "用户名和密码不能为空"
    if len(username) < 3 or len(password) < 6:
        return None, "用户名至少3位,密码至少6位"
    if User.query.filter_by(username=username).first():
        return None, "用户名已存在"

    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User(username=username, password_hash=pw_hash, role="user")
    db.session.add(user)
    db.session.commit()

    token = encode_token(user.id, user.role)
    return {"token": token, "user": user.to_dict()}, None


def login(username, password):
    user = User.query.filter_by(username=username).first()
    if not user:
        return None, "用户名或密码错误"
    if not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
        return None, "用户名或密码错误"

    token = encode_token(user.id, user.role)
    return {"token": token, "user": user.to_dict()}, None
