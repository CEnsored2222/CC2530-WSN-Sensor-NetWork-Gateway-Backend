# -*- coding: utf-8 -*-
"""人脸特征提取 + 本地余弦比对(基于 insightface)。

设计文档第 4.4 节:
    [recognize] insightface app.get(frame) → faces[].bbox/embedding/det_score
              → 拉 face_library → 余弦比对 → name
    [face/embed] insightface 提特征 → 返回 embedding

设计文档第 10.2 节比对逻辑:
    对每张脸:与 face_library 逐一余弦相似度 → 取最大值
    ≥ FACE_SIM_THRESHOLD → 命中(name=匹配名);否则 name=null
"""

import numpy as np

from config import Config


class Recognizer:
    """insightface 人脸特征提取与比对封装。"""

    def __init__(self):
        import insightface as face_app
        from insightface.app import FaceAnalysis

        ctx_id = -1  # -1=CPU
        try:
            import onnxruntime as ort
            # onnxruntime-gpu 可用时优先 GPU
            if "CUDAExecutionProvider" in ort.get_available_providers():
                ctx_id = Config.DEVICE or 0
                if ctx_id == "":
                    ctx_id = 0
        except Exception:
            pass
        if Config.DEVICE and str(Config.DEVICE).lower() == "cpu":
            ctx_id = -1

        self.app = FaceAnalysis(
            name=Config.FACE_MODEL,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
            if ctx_id != -1 else ["CPUExecutionProvider"],
        )
        self.app.prepare(ctx_id=ctx_id, det_size=(Config.FACE_DET_SIZE, Config.FACE_DET_SIZE))
        self.face_model = Config.FACE_MODEL
        self.sim_threshold = Config.FACE_SIM_THRESHOLD
        # 推断 embedding 维度(buffalo_l 为 512)
        self.embedding_dim = 512

    def extract(self, frame_bgr: np.ndarray):
        """人脸检测 + 特征提取。

        Returns:
            list[dict]: 每项 {bbox:[x1,y1,x2,y2], embedding:np.ndarray, score:float}
        """
        faces = self.app.get(frame_bgr)
        out = []
        for f in faces:
            x1, y1, x2, y2 = [int(v) for v in f.bbox.tolist()]
            emb = f.normed_embedding  # 已归一化的 512 维向量
            if emb is None:
                continue
            out.append({
                "bbox": [x1, y1, x2, y2],
                "embedding": emb.astype(np.float32),
                "score": float(f.det_score),
            })
        return out

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """余弦相似度(输入已归一化时等价于点积)。"""
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na < 1e-12 or nb < 1e-12:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def match(self, embedding: np.ndarray, face_library: list):
        """与 face_library 逐一比对,返回最佳匹配。

        Args:
            embedding: 当前人脸的 512 维向量
            face_library: [{name, embedding:np.ndarray}, ...]

        Returns:
            (name:str|None, similarity:float)  未命中 name=None,similarity=最佳相似度
        """
        best_name = None
        best_sim = -1.0
        for item in face_library:
            sim = self.cosine_similarity(embedding, item["embedding"])
            if sim > best_sim:
                best_sim = sim
                best_name = item["name"]
        if best_sim < self.sim_threshold:
            return None, best_sim
        return best_name, best_sim

    def recognize(self, frame_bgr: np.ndarray, face_library: list):
        """人脸识别:检测 + 提特征 + 本地比对。

        Args:
            frame_bgr: BGR 图像
            face_library: 本地缓存的人脸库 [{name, embedding:np.ndarray}]

        Returns:
            list[dict]: 每项 {bbox, name, similarity, score}
        """
        extracted = self.extract(frame_bgr)
        results = []
        for f in extracted:
            name, sim = self.match(f["embedding"], face_library)
            results.append({
                "bbox": f["bbox"],
                "name": name,
                "similarity": round(float(sim), 4),
                "score": round(f["score"], 4),
            })
        return results

    def info(self):
        return {
            "face_model": self.face_model,
            "embedding_dim": self.embedding_dim,
            "sim_threshold": self.sim_threshold,
        }
