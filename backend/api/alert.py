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
from models.alert_rule_target import AlertRuleTarget
from models.gateway import Gateway
from models.device import Device
from models.operation_log import OperationLog
from models.user import User
from services.alert_engine import alert_engine
from utils.auth import jwt_required

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

    if "notify" in data:
        fields["notify"] = bool(data["notify"])

    return fields, None


def _validate_and_sync_targets(user_id, rule, targets):
    """校验并同步规则的设备绑定。

    targets 格式: [{"gateway_id": 1, "device_id": null}, {"gateway_id": 1, "device_id": 5}]
    - device_id 为 null 表示绑定该网关下所有设备
    - 校验:每个 gateway 必须属于当前用户;device_id 非 null 时该设备必须属于该网关且属于用户
    - targets 为空或未传:默认绑定该用户所有网关(device_id=null)

    返回 (targets_list, error_msg)。targets_list 为标准化后的列表。
    """
    # 取用户拥有的网关 {id: gateway},以及网关下的设备
    user_gws = Gateway.query.filter_by(user_id=user_id).all()
    user_gw_ids = {gw.id for gw in user_gws}
    if not user_gws:
        # 用户没有任何网关,规则无法绑定设备(将不触发任何设备)
        return [], None

    # 未传或空:默认绑定所有网关
    if not targets:
        return [{"gateway_id": gw.id, "device_id": None} for gw in user_gws], None

    if not isinstance(targets, list):
        return None, "targets 必须为数组"

    normalized = []
    for t in targets:
        if not isinstance(t, dict):
            return None, "targets 元素必须为对象"
        gw_id = t.get("gateway_id")
        dev_id = t.get("device_id")
        try:
            gw_id = int(gw_id)
        except (TypeError, ValueError):
            return None, "gateway_id 必须为整数"
        if gw_id not in user_gw_ids:
            return None, f"网关 {gw_id} 不属于当前用户或不存在"

        if dev_id is not None:
            try:
                dev_id = int(dev_id)
            except (TypeError, ValueError):
                return None, "device_id 必须为整数或 null"
            # 校验设备属于该网关
            dev = Device.query.filter_by(id=dev_id, gateway_id=gw_id).first()
            if not dev:
                return None, f"设备 {dev_id} 不属于网关 {gw_id}"
        normalized.append({"gateway_id": gw_id, "device_id": dev_id})

    if not normalized:
        return None, "targets 不能为空"
    return normalized, None


def _apply_targets(rule, normalized_targets):
    """把标准化后的 targets 写入数据库(先清空旧的)。"""
    AlertRuleTarget.query.filter_by(rule_id=rule.id).delete()
    for t in normalized_targets:
        db.session.add(AlertRuleTarget(
            rule_id=rule.id, gateway_id=t["gateway_id"], device_id=t["device_id"],
        ))
    db.session.flush()


def _rule_owned_by_current(rule):
    """规则是否属于当前用户(管理员可访问任意规则)。"""
    if g.current_user.role == "admin":
        return True
    return rule.user_id == g.current_user.id


# ---------------- 规则列表 ----------------
@bp.get("/alerts/rules")
@jwt_required
def list_rules():
    """普通用户只返回自己的规则;管理员返回全部。"""
    if g.current_user.role == "admin":
        rules = AlertRule.query.order_by(AlertRule.created_at.desc()).all()
    else:
        rules = (
            AlertRule.query.filter_by(user_id=g.current_user.id)
            .order_by(AlertRule.created_at.desc()).all()
        )
    return jsonify([r.to_dict() for r in rules])


# ---------------- 新建规则 ----------------
@bp.post("/alerts/rules")
@jwt_required
def create_rule():
    """普通用户可创建自己的规则。默认绑定该用户所有网关。"""
    data = request.get_json(silent=True) or {}
    fields, err = _validate_rule_payload(data, partial=False)
    if err:
        return jsonify({"error": err}), 400

    # 校验设备绑定
    targets, err = _validate_and_sync_targets(g.current_user.id, None, data.get("targets"))
    if err:
        return jsonify({"error": err}), 400

    rule = AlertRule(
        **fields,
        user_id=g.current_user.id,
    )
    db.session.add(rule)
    db.session.flush()  # 拿到 rule.id
    _apply_targets(rule, targets)
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
@jwt_required
def update_rule(rid):
    rule = db.session.get(AlertRule, rid)
    if not rule:
        return jsonify({"error": "规则不存在"}), 404
    if not _rule_owned_by_current(rule):
        return jsonify({"error": "无权操作此规则"}), 403

    data = request.get_json(silent=True) or {}
    fields, err = _validate_rule_payload(data, partial=True)
    if err:
        return jsonify({"error": err}), 400

    for k, v in fields.items():
        setattr(rule, k, v)

    # 若传入 targets,更新设备绑定
    if "targets" in data:
        targets, err = _validate_and_sync_targets(rule.user_id, rule, data.get("targets"))
        if err:
            return jsonify({"error": err}), 400
        _apply_targets(rule, targets)

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
@jwt_required
def delete_rule(rid):
    rule = db.session.get(AlertRule, rid)
    if not rule:
        return jsonify({"error": "规则不存在"}), 404
    if not _rule_owned_by_current(rule):
        return jsonify({"error": "无权操作此规则"}), 403
    name = rule.name
    db.session.delete(rule)  # cascade 会自动删除 targets
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
@jwt_required
def toggle_rule(rid):
    rule = db.session.get(AlertRule, rid)
    if not rule:
        return jsonify({"error": "规则不存在"}), 404
    if not _rule_owned_by_current(rule):
        return jsonify({"error": "无权操作此规则"}), 403
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
