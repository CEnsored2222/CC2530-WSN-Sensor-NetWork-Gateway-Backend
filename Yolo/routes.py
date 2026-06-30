# -*- coding: utf-8 -*-
"""Yolo 推理服务 API 路由。

设计文档第 4.3 节 API 清单:
    GET  /health                   健康检查(不鉴权)
    GET  /api/model_info           YOLO26 类别 + 人脸模型信息(不鉴权)
    POST /api/detect               目标检测(前端直连,不鉴权)
    POST /api/recognize            人脸识别(前端直连,不鉴权;内部拉人脸库)
    POST /api/face/embed           人脸特征提取(后端注册时调用,需 INTERNAL_TOKEN)

设计文档第 4.5 节错误处理:
    frame 缺失/解码失败 → 400 {"error":"invalid frame"}
    模型未加载 → 503 {"error":"model not ready"}
    拉取 face_library 失败 → 502 {"error":"backend unreachable"}
    推理异常 → 500 {"error":"<msg>"}
"""

import base64
import io

import cv2
import numpy as np
import requests
from flask import Blueprint, jsonify, request

from config import Config

bp = Blueprint("yolo", __name__)


# ============ 工具函数 ============

def _decode_frame(frame_str: str):
    """base64 JPEG → BGR numpy 数组。

    接受带 `data:image/jpeg;base64,` 前缀或纯 base64 字符串。
    返回 (frame_bgr, None) 或 (None, error_msg)。
    """
    if not frame_str or not isinstance(frame_str, str):
        return None, "frame 缺失"
    s = frame_str.strip()
    # 去除 data: 前缀
    if s.startswith("data:"):
        # 格式 data:image/jpeg;base64,<...>
        try:
            _, b64 = s.split(",", 1)
        except ValueError:
            return None, "frame 格式错误"
        s = b64
    try:
        raw = base64.b64decode(s)
    except Exception:
        return None, "frame base64 解码失败"
    if not raw:
        return None, "frame 为空"
    arr = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return None, "frame 图像解码失败"
    return frame, None


def _parse_classes(classes_str: str):
    """解析 "0,2,5" → [0, 2, 5];空 → None。"""
    if not classes_str:
        return None
    out = []
    for part in str(classes_str).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out or None


def _check_internal_token():
    """校验 Yolo↔后端内部通信 token。返回 (ok:bool, err_response|None)。"""
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip() if auth.startswith("Bearer ") else auth
    if not Config.INTERNAL_TOKEN or token != Config.INTERNAL_TOKEN:
        return False, (jsonify({"error": "unauthorized"}), 401)
    return True, None


def _model_state():
    """从 app 上下文取已加载的模型(由 app.py 注入)。"""
    from flask import current_app
    return {
        "detector": getattr(current_app, "detector", None),
        "recognizer": getattr(current_app, "recognizer", None),
        "face_store": getattr(current_app, "face_store", None),
    }


# ============ 路由 ============

@bp.get("/health")
def health():
    """健康检查。"""
    state = _model_state()
    det = state["detector"]
    rec = state["recognizer"]
    return jsonify({
        "ok": bool(det and rec),
        "device": det.device_repr if det else "n/a",
        "yolo_model": det.weights if det else Config.WEIGHTS,
        "face_model": Config.FACE_MODEL,
    })


@bp.get("/api/model_info")
def model_info():
    """YOLO26 类别列表 + 人脸模型信息。"""
    state = _model_state()
    det = state["detector"]
    rec = state["recognizer"]
    if not det:
        return jsonify({"error": "model not ready"}), 503
    info = det.model_info()
    if rec:
        info.update(rec.info())
    return jsonify(info)


@bp.post("/api/detect")
def detect():
    """目标检测(前端直连,不鉴权)。"""
    state = _model_state()
    det = state["detector"]
    if not det:
        return jsonify({"error": "model not ready"}), 503

    data = request.get_json(silent=True) or {}
    frame, err = _decode_frame(data.get("frame", ""))
    if err:
        return jsonify({"error": "invalid frame", "detail": err}), 400

    conf = data.get("conf")
    iou = data.get("iou")
    classes = _parse_classes(data.get("classes", ""))

    try:
        detections, annotated = det.detect(frame, conf=conf, iou=iou, classes=classes)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    from detector import encode_image_b64
    return jsonify({
        "detections": detections,
        "annotated": encode_image_b64(annotated),
        "count": len(detections),
    })


@bp.post("/api/recognize")
def recognize():
    """人脸识别(前端直连,不鉴权;内部拉 face_library)。"""
    state = _model_state()
    rec = state["recognizer"]
    store = state["face_store"]
    if not rec or not store:
        return jsonify({"error": "model not ready"}), 503

    data = request.get_json(silent=True) or {}
    frame, err = _decode_frame(data.get("frame", ""))
    if err:
        return jsonify({"error": "invalid frame", "detail": err}), 400

    user_id = data.get("user_id")
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid frame", "detail": "user_id 缺失或非整数"}), 400

    # 拉取该用户的人脸库(带 TTL 缓存)
    try:
        face_library = store.get(user_id)
    except requests.RequestException:
        return jsonify({"error": "backend unreachable"}), 502
    except Exception as e:
        return jsonify({"error": f"face library load failed: {e}"}), 502

    try:
        faces = rec.recognize(frame, face_library)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"faces": faces, "count": len(faces)})


@bp.post("/api/face/embed")
def face_embed():
    """人脸特征提取(后端注册时调用,需 INTERNAL_TOKEN)。"""
    ok, err = _check_internal_token()
    if not ok:
        return err

    state = _model_state()
    rec = state["recognizer"]
    if not rec:
        return jsonify({"error": "model not ready"}), 503

    data = request.get_json(silent=True) or {}
    frame, err = _decode_frame(data.get("frame", ""))
    if err:
        return jsonify({"error": "invalid frame", "detail": err}), 400

    try:
        extracted = rec.extract(frame)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    faces_out = []
    for f in extracted:
        emb = f["embedding"]
        # embedding 用 base64 编码的 float32 二进制串(便于 HTTP 传输)
        emb_b64 = base64.b64encode(emb.tobytes()).decode("ascii")
        faces_out.append({
            "bbox": f["bbox"],
            "embedding": emb_b64,
            "score": f["score"],
        })
    return jsonify({"faces": faces_out, "count": len(faces_out)})
