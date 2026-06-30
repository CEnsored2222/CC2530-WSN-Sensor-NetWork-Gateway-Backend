# -*- coding: utf-8 -*-
"""视觉模块接口(人脸库 CRUD + Yolo 地址下发 + 内部人脸库接口)。

设计文档第 6 节接口清单:
    GET    /api/vision/endpoint          返回 Yolo 公网地址给前端(JWT,[2])
    GET    /api/vision/faces             当前用户人脸库列表(JWT,[2])
    POST   /api/vision/faces             注册人脸(frame+name → 调 Yolo 提特征 → 存库)
                                          (JWT + INTERNAL_TOKEN,[2]+[3])
    DELETE /api/vision/faces/{id}        删除人脸(仅本人)(JWT,[2])
    GET    /api/vision/internal/faces    Yolo 拉取指定用户人脸库(INTERNAL_TOKEN,[3])

链路编号说明:
    [2] 前端 ↔ 后端(JWT)
    [3] Yolo ↔ 后端(服务 token)
"""
import base64

import requests
from flask import Blueprint, g, jsonify, request

from config import Config
from extensions import db
from models.vision import FaceLibrary
from utils.auth import jwt_required

bp = Blueprint("vision", __name__)


# ============ 内部工具 ============

def _check_internal_token():
    """校验 Yolo↔后端内部通信 token。返回 (ok:bool, err_response|None)。"""
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not Config.VISION_INTERNAL_TOKEN or token != Config.VISION_INTERNAL_TOKEN:
        return False, (jsonify({"error": "unauthorized"}), 401)
    return True, None


def _call_yolo_embed(frame_b64: str):
    """调用 Yolo POST /api/face/embed 提取人脸特征。

    Returns:
        (faces:list, error:str|None)
        faces 每项 {bbox, embedding:bytes, score}
    """
    url = f"{Config.YOLO_SERVICE_URL}/api/face/embed"
    try:
        resp = requests.post(
            url,
            json={"frame": frame_b64},
            headers={"Authorization": f"Bearer {Config.VISION_INTERNAL_TOKEN}"},
            timeout=10,
        )
    except requests.RequestException as e:
        return None, f"yolo unreachable: {e}"

    if resp.status_code != 200:
        try:
            msg = resp.json().get("error", resp.text)
        except Exception:
            msg = resp.text
        return None, f"yolo error: {msg}"

    payload = resp.json()
    faces = []
    for f in payload.get("faces", []):
        emb_b64 = f.get("embedding")
        if not emb_b64:
            continue
        emb_bytes = base64.b64decode(emb_b64)
        faces.append({
            "bbox": f.get("bbox"),
            "embedding": emb_bytes,
            "score": f.get("score"),
        })
    return faces, None


# ============ 接口:Yolo 地址下发(链路 [2]) ============

@bp.get("/vision/endpoint")
@jwt_required
def get_endpoint():
    """返回 Yolo 公网地址给前端直连。"""
    return jsonify({"yolo_url": Config.YOLO_SERVICE_URL})


# ============ 接口:人脸库 CRUD(链路 [2] + 注册时 [3]) ============

@bp.get("/vision/faces")
@jwt_required
def list_faces():
    """当前用户人脸库列表(不含 embedding 原始向量)。"""
    rows = (
        FaceLibrary.query
        .filter_by(user_id=g.current_user.id)
        .order_by(FaceLibrary.created_at.desc())
        .all()
    )
    return jsonify([r.to_dict() for r in rows])


@bp.post("/vision/faces")
@jwt_required
def add_face():
    """人脸注册:校验姓名不重复 → 调 Yolo 提特征 → 存库。

    入参 JSON:
        frame: str (base64 JPEG)
        name:  str (姓名,1-64 字符)
    """
    data = request.get_json(silent=True) or {}
    frame_b64 = data.get("frame", "")
    name = (data.get("name") or "").strip()

    if not frame_b64:
        return jsonify({"error": "frame 必填"}), 400
    if not name or len(name) > 64:
        return jsonify({"error": "name 必填且长度 1-64"}), 400

    # 校验同一用户姓名不重复
    exists = FaceLibrary.query.filter_by(
        user_id=g.current_user.id, name=name
    ).first()
    if exists:
        return jsonify({"error": f"姓名 '{name}' 已存在"}), 400

    # 调 Yolo 提特征(链路 [3])
    faces, err = _call_yolo_embed(frame_b64)
    if err:
        return jsonify({"error": err}), 502
    if not faces:
        return jsonify({"error": "未检测到人脸,请重新采集"}), 400

    # 取第一个 face 的 embedding 存库
    emb_bytes = faces[0]["embedding"]
    # 样张:截断 data: 前缀的 base64,直接存 base64 串(便于前端 <img :src>)
    snapshot = frame_b64 if len(frame_b64) < 200000 else None

    face = FaceLibrary(
        user_id=g.current_user.id,
        name=name,
        embedding=emb_bytes,
        sample_snapshot=snapshot,
    )
    db.session.add(face)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"保存失败: {e}"}), 500

    return jsonify(face.to_dict()), 201


@bp.delete("/vision/faces/<int:face_id>")
@jwt_required
def delete_face(face_id):
    """删除人脸(仅本人)。"""
    face = db.session.get(FaceLibrary, face_id)
    if not face or face.user_id != g.current_user.id:
        return jsonify({"error": "人脸记录不存在或无权操作"}), 404
    db.session.delete(face)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"删除失败: {e}"}), 500
    return jsonify({"ok": True})


# ============ 接口:Yolo 拉取人脸库(链路 [3]) ============

@bp.get("/vision/internal/faces")
def internal_list_faces():
    """Yolo 在 /api/recognize 时拉取指定用户人脸库(返回 embedding)。

    Query: ?user_id=<int>
    Header: Authorization: Bearer <INTERNAL_TOKEN>

    Returns:
        [{name, embedding:<base64 float32 串>}, ...]
    """
    ok, err = _check_internal_token()
    if not ok:
        return err

    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id 必填"}), 400

    rows = (
        FaceLibrary.query
        .filter_by(user_id=user_id)
        .all()
    )
    out = []
    for r in rows:
        emb_b64 = base64.b64encode(r.embedding or b"").decode("ascii")
        out.append({"name": r.name, "embedding": emb_b64})
    return jsonify(out)
