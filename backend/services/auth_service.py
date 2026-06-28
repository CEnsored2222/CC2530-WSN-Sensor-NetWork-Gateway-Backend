# -*- coding: utf-8 -*-
"""认证服务:注册/登录"""
import bcrypt

from extensions import db
from models.user import User
from utils.auth import encode_token
from utils.verification import generate_code, make_verify_token, verify_code
from utils.email_sender import check_rate_limit, send_code_email


def send_code(email: str):
    """向指定邮箱发送6位验证码，返回 JWT 令牌"""
    import re

    if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return None, "邮箱格式不正确"

    # 检查该邮箱是否已被注册
    if User.query.filter_by(email=email).first():
        return None, "该邮箱已被注册"

    # 频率限制
    wait = check_rate_limit(email)
    if wait is not None:
        return None, f"发送过于频繁，请 {wait} 秒后再试"

    code = generate_code()
    token = make_verify_token(email, code)

    try:
        send_code_email(email, code)
    except Exception:
        return None, "验证码发送失败，请检查邮箱地址或稍后重试"

    return {"token": token, "message": f"验证码已发送至 {email}，{5} 分钟内有效"}, None


def register(username, password, email, code, verify_token):
    """注册新用户（需验证邮箱验证码）"""
    import re

    if not username or not password or not email or not code or not verify_token:
        return None, "请填写所有必填项"
    if len(username) < 3 or len(password) < 6:
        return None, "用户名至少3位，密码至少6位"
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return None, "邮箱格式不正确"
    if len(code) != 6 or not code.isdigit():
        return None, "验证码格式不正确"

    if User.query.filter_by(username=username).first():
        return None, "用户名已存在"
    if User.query.filter_by(email=email).first():
        return None, "该邮箱已被注册"

    # 验证邮箱验证码
    ok, err = verify_code(verify_token, email, code)
    if not ok:
        return None, err

    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User(
        username=username,
        password_hash=pw_hash,
        email=email,
        email_verified=True,
        role="user",
    )
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
