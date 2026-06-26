# -*- coding: utf-8 -*-
"""告警接口。

- 规则列表/新建/修改/删除/启停(管理员可写,普通用户只读列表)
- 告警记录查询(所有登录用户,仅返回 action=alert 的 operation_logs)
"""
import json
from datetime import datetime

from flask import Blueprint, g, jsonify, request

from extensions import db
from models.alert_rule import AlertRule, METRICS, OPERATORS, LOGICS, SEVERITIES
from models.operation_log import OperationLog
from models.user import User
from services.alert_engine import alert_engine
from utils.auth import admin_required, jwt_required

bp = Blueprint("alert", __name__)


_ALLOWED_METRICS = set(METRICS)
_ALLOWED_OPS = set(OPERATORS)
_ALLOWED_LOGICS = set(LOGICS)
_ALLOWED_SEV = set(SEVERITIES)


def _validate_rule_payload(data, partial=False):
    """校验规则字段,返回 (rule_dict, error_msg)。"""
    fields = {}

    if not partial or "name" in data:
        name = (data.get("name") or "").strip()
        if not name or len(name) > 64:
            return None, "name 必填且不超过 64 字符"
        fields["name"] = name

    if not partial or "metric" in data:
        metric = data.get("metric")
        if metric not in _ALLOWED_METRICS:
            return None, f"metric 必须为 {METRICS} 之一"
        fields["metric"] = metric

    if not partial or "operator" in data:
        operator = data.get("operator")
        if operator not in _ALLOWED_OPS:
            return None, f"operator 必须为 {OPERATORS} 之一"
        fields["operator"] = operator

    if not partial or "threshold" in data:
        try:
            threshold = float(data.get("threshold"))
        except (TypeError, ValueError):
            return None, "threshold 必须为数字"
        fields["threshold"] = threshold

    logic = data.get("logic", "none")
    if logic not in _ALLOWED_LOGICS:
        return None, f"logic 必须为 {LOGICS} 之一"
    fields["logic"] = logic

    # 组合条件校验
    if logic in ("and", "or"):
        sm = data.get("second_metric")
        so = data.get("second_operator")
        st = data.get("second_threshold")
        if sm not in _ALLOWED_METRICS:
            return None, "组合逻辑需要有效的 second_metric"
        if so not in _ALLOWED_OPS:
            return None, "组合逻辑需要有效的 second_operator"
        try:
            st = float(st)
        except (TypeError, ValueError):
            return None, "second_threshold 必须为数字"
        fields["second_metric"] = sm
        fields["second_operator"] = so
        fields["second_threshold"] = st
    else:
        fields["second_metric"] = None
        fields["second_operator"] = None
        fields["second_threshold"] = None

    if not partial or "severity" in data:
        severity = data.get("severity", "warning")
        if severity not in _ALLOWED_SEV:
            return None, f"severity 必须为 {SEVERITIES} 之一"
        fields["severity"] = severity

    if "enabled" in data:
        fields["enabled"] = bool(data["enabled"])

    return fields, None


# ---------------- 规则列表 ----------------
@bp.get("/alerts/rules")
@jwt_required
def list_rules():
    rules = AlertRule.query.order_by(AlertRule.created_at.desc()).all()
    return jsonify([r.to_dict() for r in rules])


# ---------------- 新建规则 ----------------
@bp.post("/alerts/rules")
@admin_required
def create_rule():
    data = request.get_json(silent=True) or {}
    fields, err = _validate_rule_payload(data, partial=False)
    if err:
        return jsonify({"error": err}), 400

    rule = AlertRule(
        **fields,
        created_by=g.current_user.id,
    )
    db.session.add(rule)
    db.session.commit()
    alert_engine.invalidate_cache()

    db.session.add(OperationLog(
        user_id=g.current_user.id, action="create_alert_rule",
        target_type="alert_rule", target_id=rule.id,
        detail=json.dumps({"name": rule.name, "metric": rule.metric}, ensure_ascii=False),
    ))
    db.session.commit()
    return jsonify(rule.to_dict()), 201


# ---------------- 修改规则 ----------------
@bp.patch("/alerts/rules/<int:rid>")
@admin_required
def update_rule(rid):
    rule = db.session.get(AlertRule, rid)
    if not rule:
        return jsonify({"error": "规则不存在"}), 404

    data = request.get_json(silent=True) or {}
    fields, err = _validate_rule_payload(data, partial=True)
    if err:
        return jsonify({"error": err}), 400

    for k, v in fields.items():
        setattr(rule, k, v)
    db.session.commit()
    alert_engine.invalidate_cache()

    db.session.add(OperationLog(
        user_id=g.current_user.id, action="update_alert_rule",
        target_type="alert_rule", target_id=rule.id,
        detail=json.dumps({"name": rule.name}, ensure_ascii=False),
    ))
    db.session.commit()
    return jsonify(rule.to_dict())


# ---------------- 删除规则 ----------------
@bp.delete("/alerts/rules/<int:rid>")
@admin_required
def delete_rule(rid):
    rule = db.session.get(AlertRule, rid)
    if not rule:
        return jsonify({"error": "规则不存在"}), 404
    name = rule.name
    db.session.delete(rule)
    db.session.commit()
    alert_engine.invalidate_cache()

    db.session.add(OperationLog(
        user_id=g.current_user.id, action="delete_alert_rule",
        target_type="alert_rule", target_id=rid,
        detail=json.dumps({"name": name}, ensure_ascii=False),
    ))
    db.session.commit()
    return jsonify({"ok": True})


# ---------------- 启停规则(便捷接口) ----------------
@bp.patch("/alerts/rules/<int:rid>/toggle")
@admin_required
def toggle_rule(rid):
    rule = db.session.get(AlertRule, rid)
    if not rule:
        return jsonify({"error": "规则不存在"}), 404
    data = request.get_json(silent=True) or {}
    if "enabled" in data:
        rule.enabled = bool(data["enabled"])
    else:
        rule.enabled = not rule.enabled
    db.session.commit()
    alert_engine.invalidate_cache()

    db.session.add(OperationLog(
        user_id=g.current_user.id, action="toggle_alert_rule",
        target_type="alert_rule", target_id=rule.id,
        detail=json.dumps({"enabled": rule.enabled}, ensure_ascii=False),
    ))
    db.session.commit()
    return jsonify(rule.to_dict())


# ---------------- 告警记录 ----------------
@bp.get("/alerts/records")
@jwt_required
def list_records():
    """返回当前用户的告警记录(action=alert)。

    支持分页与 severity 筛选。
    """
    page = request.args.get("page", 1, type=int)
    size = request.args.get("size", 20, type=int)
    size = max(1, min(size, 100))
    severity = request.args.get("severity", "").strip()

    q = OperationLog.query.filter_by(user_id=g.current_user.id, action="alert")
    if severity:
        # severity 存在 detail JSON 中,用 LIKE 粗筛
        q = q.filter(OperationLog.detail.like(f'%"severity": "{severity}"%'))
    q = q.order_by(OperationLog.created_at.desc())

    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()

    items = []
    for r in rows:
        d = r.to_dict()
        try:
            d["detail_obj"] = json.loads(r.detail) if r.detail else {}
        except Exception:
            d["detail_obj"] = {}
        items.append(d)
    return jsonify({
        "total": total,
        "page": page,
        "size": size,
        "items": items,
    })


# ---------------- 统计(给前端 dashboard) ----------------
@bp.get("/alerts/stats")
@jwt_required
def stats():
    """返回当前用户告警统计:各级别数量与最近告警。"""
    rows = OperationLog.query.filter_by(
        user_id=g.current_user.id, action="alert"
    ).order_by(OperationLog.created_at.desc()).limit(200).all()

    counts = {"info": 0, "warning": 0, "critical": 0}
    recent = []
    for r in rows:
        try:
            obj = json.loads(r.detail) if r.detail else {}
        except Exception:
            obj = {}
        sev = obj.get("severity", "info")
        if sev in counts:
            counts[sev] += 1
        if len(recent) < 5:
            recent.append({
                "id": r.id,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
                **obj,
            })
    return jsonify({
        "counts": counts,
        "total": sum(counts.values()),
        "recent": recent,
    })
