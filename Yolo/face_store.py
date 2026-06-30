# -*- coding: utf-8 -*-
"""从后端拉取 / 缓存 face_library。

设计文档第 10.2 节:
    Yolo 调后端 GET /api/vision/internal/faces?user_id=X
        (Authorization: Bearer <INTERNAL_TOKEN>)
      → 后端返回该用户 face_library [{name, embedding}]
    face_library 拉取可加内存缓存(TTL 30s),避免逐帧请求后端。

设计文档第 10.3 节注册后失效缓存:
    前端列表刷新 + 通知 Yolo 失效人脸库缓存(下次 recognize 重新拉取)
"""

import base64
import threading
import time

import numpy as np
import requests

from config import Config


class FaceStore:
    """face_library 拉取 + 内存缓存(TTL 30s)。"""

    def __init__(self):
        self._cache = {}  # {user_id: {"ts": float, "data": list}}
        self._lock = threading.Lock()
        self._ttl = Config.FACE_CACHE_TTL
        self._backend = Config.BACKEND_URL
        self._token = Config.INTERNAL_TOKEN

    def _fetch(self, user_id: int) -> list:
        """从后端拉取指定用户的人脸库,返回 [{name, embedding:np.ndarray}]。"""
        url = f"{self._backend}/api/vision/internal/faces"
        resp = requests.get(
            url,
            params={"user_id": user_id},
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=5,
        )
        resp.raise_for_status()
        payload = resp.json()
        # 后端返回 [{name, embedding:<base64 float32 串>}, ...]
        library = []
        for item in payload:
            emb_b64 = item.get("embedding")
            if not emb_b64:
                continue
            emb_bytes = base64.b64decode(emb_b64)
            emb = np.frombuffer(emb_bytes, dtype=np.float32)
            library.append({"name": item.get("name"), "embedding": emb})
        return library

    def get(self, user_id: int) -> list:
        """获取指定用户的人脸库(带 TTL 缓存)。

        Returns:
            list[{name, embedding:np.ndarray}]
        Raises:
            requests.RequestException: 后端不可达时
        """
        now = time.time()
        with self._lock:
            entry = self._cache.get(user_id)
            if entry and (now - entry["ts"]) < self._ttl:
                return entry["data"]

        # 缓存未命中或已过期,从后端拉取
        data = self._fetch(user_id)
        with self._lock:
            self._cache[user_id] = {"ts": now, "data": data}
        return data

    def invalidate(self, user_id: int = None):
        """失效缓存(注册/删除人脸后调用)。

        Args:
            user_id: 指定用户;None 表示清空全部缓存
        """
        with self._lock:
            if user_id is None:
                self._cache.clear()
            else:
                self._cache.pop(user_id, None)
