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

    def _fetch(self, user_id: int):
        """从后端拉取人脸库,返回 {entries, matrix}。

        entries: [{name, embedding:np.ndarray}]
        matrix: (M, 512) 已 L2 归一化的 np.ndarray
        """
        url = f"{self._backend}/api/vision/internal/faces"
        resp = requests.get(
            url,
            params={"user_id": user_id},
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=5,
        )
        resp.raise_for_status()
        payload = resp.json()
        library = []
        emb_list = []
        for item in payload:
            emb_b64 = item.get("embedding")
            if not emb_b64:
                continue
            emb_bytes = base64.b64decode(emb_b64)
            emb = np.frombuffer(emb_bytes, dtype=np.float32)
            library.append({"name": item.get("name"), "embedding": emb})
            emb_list.append(emb)

        # 预构建 (M, 512) 矩阵, L2 归一化
        if emb_list:
            matrix = np.stack(emb_list, axis=0)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            matrix = matrix / np.maximum(norms, 1e-12)
        else:
            matrix = np.empty((0, 512), dtype=np.float32)

        return {"entries": library, "matrix": matrix}

    def get(self, user_id: int):
        """获取人脸库(带 TTL 缓存)。

        Returns:
            dict: {"entries": [{name, embedding}], "matrix": (M,512) np.ndarray}
        Raises:
            requests.RequestException
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
