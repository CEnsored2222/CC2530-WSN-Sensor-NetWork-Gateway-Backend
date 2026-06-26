# -*- coding: utf-8 -*-
"""操作日志接口(管理员):分页查询与筛选"""
from flask import Blueprint, g, jsonify, request

from extensions import db
from models.operation_log import OperationLog
from models.user import User
from utils.auth import admin_required

bp = Blueprint("operation_log", __name__)


@bp.get("/operation-logs")
@admin_required
def list_logs():
    page = request.args.get("page", 1, type=int)
    size = request.args.get("size", 20, type=int)
    size = max(1, min(size, 100))
    action = request.args.get("action", "").strip()
    user_id = request.args.get("user_id", type=int)

    q = OperationLog.query
    if action:
        q = q.filter(OperationLog.action == action)
    if user_id:
        q = q.filter(OperationLog.user_id == user_id)
    q = q.order_by(OperationLog.created_at.desc())

    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()

    # 一次性查出涉及用户名,避免 N+1
    uids = {r.user_id for r in rows if r.user_id is not None}
    users = {u.id: u.username for u in User.query.filter(User.id.in_(uids)).all()} if uids else {}

    return jsonify({
        "total": total,
        "page": page,
        "size": size,
        "items": [
            {
                **r.to_dict(),
                "username": users.get(r.user_id) if r.user_id else None,
            }
            for r in rows
        ],
    })


@bp.get("/operation-logs/actions")
@admin_required
def list_actions():
    """返回数据库中已出现过的 action 类型,用于筛选项。"""
    rows = db.session.query(OperationLog.action).distinct().all()
    return jsonify([r[0] for r in rows if r[0]])


@bp.delete("/operation-logs/<int:lid>")
@admin_required
def delete_log(lid):
    """删除单条日志(数据库物理删除,不记录该删除动作)。"""
    log = db.session.get(OperationLog, lid)
    if not log:
        return jsonify({"error": "日志不存在"}), 404
    db.session.delete(log)
    db.session.commit()
    return jsonify({"ok": True})


@bp.delete("/operation-logs")
@admin_required
def delete_logs_batch():
    """批量删除日志(数据库物理删除,不记录该删除动作)。

    请求体:{"ids": [1, 2, 3]}
    """
    data = request.get_json(silent=True) or {}
    ids = data.get("ids")
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "ids 必须为非空数组"}), 400
    # 过滤非法 id
    clean_ids = [int(i) for i in ids if isinstance(i, (int, str)) and str(i).isdigit()]
    if not clean_ids:
        return jsonify({"error": "ids 必须为非空数组"}), 400
    OperationLog.query.filter(OperationLog.id.in_(clean_ids)).delete(
        synchronize_session=False
    )
    db.session.commit()
    return jsonify({"ok": True, "deleted": len(clean_ids)})
