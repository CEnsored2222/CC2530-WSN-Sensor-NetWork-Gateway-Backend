# -*- coding: utf-8 -*-
"""Yolo 适配层：单例封装 Detector/Recognizer/FaceStore，支持懒加载和设备切换。"""
import base64
import threading

import numpy as np

import config as gateway_config
import yolo_config


class YoloService:
    """Yolo 适配层：单例封装 Detector/Recognizer/FaceStore，支持懒加载和设备切换。"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # __init__ 会被多次调用（即使单例），用 _initialized 标志保护
        if getattr(self, "_initialized", False):
            return
        self._detector = None
        self._recognizer = None
        self._face_store = None
        self._initialized = False
        self._device = None

    def _ensure_initialized(self) -> bool:
        """懒加载核心：按需加载 Detector/Recognizer/FaceStore。"""
        if self._initialized:
            return True
        if not gateway_config.YOLO_ENABLED:
            print("[yolo_service] yolo disabled (YOLO_ENABLED=False)")
            return False
        if not yolo_config.inject_to_yolo():
            print("[yolo_service] inject_to_yolo failed")
            return False
        yolo_config.setup_yolo_path()
        try:
            from detector import Detector
            from recognizer import Recognizer
            from face_store import FaceStore
            self._detector = Detector()
            self._recognizer = Recognizer()
            self._face_store = FaceStore()
        except Exception as e:
            print(f"[yolo_service] init failed: {e}")
            self._detector = None
            self._recognizer = None
            self._face_store = None
            return False
        self._initialized = True
        self._device = gateway_config.YOLO_DEVICE
        print("[yolo_service] initialized")
        return True

    def detect(self, frame_bgr, conf=None, iou=None, classes=None) -> dict:
        """目标检测。"""
        if not self._ensure_initialized():
            return {"status": "error", "error": "yolo not initialized"}
        try:
            detections = self._detector.detect(frame_bgr, conf, iou, classes)
            return {"status": "ok", "data": detections}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def recognize(self, frame_bgr, user_id) -> dict:
        """人脸识别：拉取人脸库 + 本地比对。"""
        if not self._ensure_initialized():
            return {"status": "error", "error": "yolo not initialized"}
        try:
            face_library = self._face_store.get(user_id)
        except Exception as e:
            return {"status": "error", "error": f"face library fetch failed: {e}"}
        try:
            results = self._recognizer.recognize(frame_bgr, face_library)
            return {"status": "ok", "data": results}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def extract_embedding(self, frame_bgr) -> dict:
        """人脸特征提取，embedding 转 base64 float32 串便于 JSON 序列化。"""
        if not self._ensure_initialized():
            return {"status": "error", "error": "yolo not initialized"}
        try:
            extracted = self._recognizer.extract(frame_bgr)
            data = []
            for f in extracted:
                emb = f["embedding"]
                emb_bytes = emb.astype(np.float32).tobytes()
                emb_b64 = base64.b64encode(emb_bytes).decode("ascii")
                data.append({
                    "bbox": f["bbox"],
                    "embedding": emb_b64,
                    "score": f["score"],
                })
            return {"status": "ok", "data": data}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def invalidate_face_cache(self, user_id=None) -> dict:
        """失效人脸库缓存。"""
        if not self._ensure_initialized():
            return {"status": "error", "error": "yolo not initialized"}
        try:
            self._face_store.invalidate(user_id)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def status(self) -> dict:
        """报告当前状态（不触发初始化）。"""
        return {
            "ready": self._initialized,
            "enabled": gateway_config.YOLO_ENABLED,
            "device": self._device or "(auto)",
            "yolo_model": self._detector.weights if self._detector else None,
            "imgsz": gateway_config.YOLO_IMGSZ,
            "face_model": gateway_config.FACE_MODEL,
            "detector_loaded": self._detector is not None,
            "recognizer_loaded": self._recognizer is not None,
        }

    def switch_device(self, device) -> dict:
        """切换推理设备：持久化配置 + 重置懒加载状态，下次调用时自动重新初始化。"""
        gateway_config.set_config_value("YOLO_DEVICE", device)
        gateway_config.save_to_file()
        self._initialized = False
        self._detector = None
        self._recognizer = None
        self._face_store = None
        self._device = device
        print(f"[yolo_service] device switched to '{device}', will reload on next call")
        return {"status": "ok", "device": device}

    def check_gpu_available(self) -> dict:
        """检查 GPU 是否可用（不加载模型）。"""
        try:
            import torch
            available = bool(torch.cuda.is_available())
            count = int(torch.cuda.device_count())
            devices = [torch.cuda.get_device_name(i) for i in range(count)]
            return {"gpu_available": available, "device_count": count, "devices": devices}
        except ImportError:
            return {"gpu_available": False, "device_count": 0, "devices": [], "error": "torch not installed"}
        except Exception as e:
            print(f"[yolo_service] gpu check failed: {e}")
            return {"gpu_available": False, "device_count": 0, "devices": [], "error": str(e)}
