 # -*- coding: utf-8 -*-
"""认证接口:注册/登录/当前用户"""
from flask import Blueprint, g, jsonify, request

from services.auth_service import login as do_login, register as do_register
from utils.auth import jwt_required

bp = Blueprint("auth", __name__)


@bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    result, err = do_register(data.get("username"), data.get("password"))
    if err:
        return jsonify({"error": err}), 400
    return jsonify(result)


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    result, err = do_login(data.get("username"), data.get("password"))
    if err:
        return jsonify({"error": err}), 400
    return jsonify(result)


@bp.get("/me")
@jwt_required
def me():
    return jsonify(g.current_user.to_dict())
