 # -*- coding: utf-8 -*-
"""认证接口:注册/登录/当前用户/邮箱验证码"""
import json

from flask import Blueprint, g, jsonify, request

from extensions import db
from models.operation_log import OperationLog
from services.auth_service import login as do_login, register as do_register, send_code as do_send_code
from utils.auth import jwt_required

bp = Blueprint("auth", __name__)

_IP = lambda: request.remote_addr or ""


@bp.post("/send-code")
def send_code():
    """发送邮箱验证码"""
    data = request.get_json(silent=True) or {}
    result, err = do_send_code(data.get("email"))
    if err:
        return jsonify({"error": err}), 400
    # 记操作日志(发送验证码尚无用户,记录目标邮箱)
    db.session.add(OperationLog(
        user_id=None, action="send_code",
        target_type="email",
        detail=json.dumps({"email": (data.get("email") or "")}, ensure_ascii=False),
        ip=_IP(),
    ))
    db.session.commit()
    return jsonify(result)


@bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    result, err = do_register(
        username=data.get("username"),
        password=data.get("password"),
        email=data.get("email"),
        code=data.get("code"),
        verify_token=data.get("token"),
    )
    if err:
        return jsonify({"error": err}), 400
    # 记操作日志(用户已创建,从 result 取 user.id)
    user_id = (result.get("user") or {}).get("id")
    db.session.add(OperationLog(
        user_id=user_id, action="register",
        target_type="user", target_id=user_id,
        detail=json.dumps({"username": data.get("username")}, ensure_ascii=False),
        ip=_IP(),
    ))
    db.session.commit()
    return jsonify(result)


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    result, err = do_login(data.get("username"), data.get("password"))
    if err:
        return jsonify({"error": err}), 400
    # 记操作日志
    user_id = (result.get("user") or {}).get("id")
    db.session.add(OperationLog(
        user_id=user_id, action="login",
        target_type="user", target_id=user_id,
        ip=_IP(),
    ))
    db.session.commit()
    return jsonify(result)


@bp.get("/me")
@jwt_required
def me():
    return jsonify(g.current_user.to_dict())
