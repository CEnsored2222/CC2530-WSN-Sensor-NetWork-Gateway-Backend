# -*- coding: utf-8 -*-
"""JWT 认证工具:签发/校验 token,以及 @jwt_required / @admin_required 装饰器。"""
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import g, jsonify, request

from config import Config
from extensions import db
from models.user import User


def encode_token(user_id: int, role: str) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=Config.JWT_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")


def decode_token(token: str):
    try:
        return jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def _extract_user():
    """从请求头解析 token 并返回 User,失败返回 (None, error_response)。"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, (jsonify({"error": "未认证"}), 401)
    token = auth[7:].strip()
    payload = decode_token(token)
    if not payload:
        return None, (jsonify({"error": "token无效或已过期"}), 401)
    user = db.session.get(User, payload.get("user_id"))
    if not user:
        return None, (jsonify({"error": "用户不存在"}), 401)
    return user, None


def jwt_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user, err = _extract_user()
        if err:
            return err
        g.current_user = user
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user, err = _extract_user()
        if err:
            return err
        if user.role != "admin":
            return jsonify({"error": "需要管理员权限"}), 403
        g.current_user = user
        return f(*args, **kwargs)
    return wrapper
