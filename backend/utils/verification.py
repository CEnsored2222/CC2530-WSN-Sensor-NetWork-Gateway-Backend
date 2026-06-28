# -*- coding: utf-8 -*-
"""验证码生成与 JWT 自包含令牌工具"""
import random
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config import Config


def generate_code() -> str:
    """生成 6 位数字验证码"""
    return str(random.randint(100000, 999999))


def make_verify_token(email: str, code: str) -> str:
    """
    将邮箱 + 验证码哈希签入短期 JWT，作为注册凭证。
    前端需同时提交 code 和 token，后端验签比对。
    """
    code_hash = bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    payload = {
        "email": email,
        "code_hash": code_hash,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=Config.CODE_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")


def verify_code(token: str, email: str, code: str) -> tuple[bool, str | None]:
    """
    校验验证码：
    1. 解析 JWT 是否合法、未过期
    2. 比对邮箱是否一致
    3. bcrypt 比对验证码是否匹配

    返回 (是否通过, 错误信息)
    """
    try:
        payload = jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return False, "验证码已过期，请重新获取"
    except jwt.PyJWTError:
        return False, "验证凭证无效，请重新获取验证码"

    if payload.get("email") != email:
        return False, "邮箱与验证码不匹配"

    code_hash = payload.get("code_hash", "")
    if not bcrypt.checkpw(code.encode("utf-8"), code_hash.encode("utf-8")):
        return False, "验证码错误"

    return True, None
