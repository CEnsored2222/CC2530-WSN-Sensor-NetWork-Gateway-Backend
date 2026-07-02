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

import time

import cv2
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
            providers = ort.get_available_providers()
            # onnxruntime-gpu 可用时优先 GPU
            if "CUDAExecutionProvider" in providers:
                raw = Config.DEVICE or "0"
                ctx_id = int(raw) if str(raw).strip().isdigit() else 0
                print(f"[Yolo] Recognizer GPU 已启用: ctx_id={ctx_id}, "
                      f"providers={providers}")
            else:
                print(f"[Yolo] Recognizer 未检测到 CUDA, 使用 CPU 推理。"
                      f"可用 providers: {providers}")
                print(f"[Yolo] 如需 GPU 加速请安装 onnxruntime-gpu")
        except Exception as e:
            print(f"[Yolo] Recognizer GPU 检测异常, 回退 CPU: {e}")
        if Config.DEVICE and str(Config.DEVICE).lower() == "cpu":
            ctx_id = -1

        self.app = FaceAnalysis(
            name=Config.FACE_MODEL,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
            if ctx_id != -1 else ["CPUExecutionProvider"],
        )
        self.app.prepare(ctx_id=ctx_id, det_size=(Config.FACE_DET_SIZE, Config.FACE_DET_SIZE))
        self.face_model = Config.FACE_MODEL
        self.det_size = (Config.FACE_DET_SIZE, Config.FACE_DET_SIZE)
        self.sim_threshold = Config.FACE_SIM_THRESHOLD
        # 推断 embedding 维度(buffalo_s/l 均为 512)
        self.embedding_dim = 512

        # 方案6:帧级去抖缓存——相邻帧若几乎无变化直接复用上一帧结果,
        # 跳过 insightface 完整 extract(检测+提特征),静止画面 ~0ms 返回。
        self._prev_sig = None        # 上一帧降采样灰度签名 (32x32 uint8)
        self._prev_results = None    # 上一帧识别结果
        self._reuse_threshold = 8.0  # 帧间灰度 MAD 阈值,< 此值认为静止

        # 预热推理(触发 ONNX 图优化,避免首帧冷启动)
        self._warmup()

    @staticmethod
    def _frame_sig(frame_bgr, size=32):
        """降采样灰度图作为帧签名(用于帧间相似度判断)。

        32x32 足以捕捉画面整体变化,计算开销 < 0.3ms。
        """
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray, (size, size))

    def _warmup(self):
        """预热推理:跑一帧 dummy,触发 ONNX 图编译/模型加载。"""
        try:
            import cv2
            ds = self.det_size[0]
            dummy = np.zeros((ds, ds, 3), dtype=np.uint8)
            t0 = time.time()
            _ = self.app.get(dummy)
            elapsed = (time.time() - t0) * 1000
            print(f"[Yolo] insightface 预热完成(model={self.face_model}, "
                  f"det_size={ds}, warmup={elapsed:.0f}ms)")
        except Exception as e:
            print(f"[Yolo] insightface 预热失败(不影响后续推理): {e}")

    def extract(self, frame_bgr: np.ndarray):
        """人脸检测 + 特征提取。

        Returns:
            list[dict]: 每项 {bbox:[x1,y1,x2,y2], embedding:np.ndarray, score:float}
        """
        faces = self.app.get(frame_bgr)
        out = []
        for f in faces:
            x1, y1, x2, y2 = [int(v) for v in f.bbox.tolist()]
            emb = f.normed_embedding  # 已 L2 归一化的 float32,无需拷贝
            if emb is None:
                continue
            out.append({
                "bbox": [x1, y1, x2, y2],
                "embedding": emb,
                "score": float(f.det_score),
            })
        return out

    def match_batch(self, embeddings, lib_matrix, threshold):
        """矢量化批量比对:一次 np.dot 完成全部匹配。

        Args:
            embeddings: list of (512,) np.ndarray (已归一化)
            lib_matrix: (M, 512) np.ndarray (已归一化)
            threshold: 相似度阈值

        Returns:
            list[(name|None, sim)] 与 embeddings 等长
        """
        if len(lib_matrix) == 0:
            return [(None, -1.0)] * len(embeddings)

        emb_stack = np.stack(embeddings, axis=0)            # (N, 512)
        sims = np.dot(lib_matrix, emb_stack.T)               # (M, N)
        best_idx = np.argmax(sims, axis=0)                   # (N,)
        best_sims = sims[best_idx, np.arange(len(embeddings))]

        results = []
        for i in range(len(embeddings)):
            s = float(best_sims[i])
            if s >= threshold:
                results.append((self._lib_names[best_idx[i]], s))
            else:
                results.append((None, s))
        return results

    def match(self, embedding: np.ndarray, face_library: list):
        """逐条比对(兜底,库为 list 格式时)。"""
        best_name = None
        best_sim = -1.0
        for item in face_library:
            # embedding 已归一化,直接用点积
            sim = float(np.dot(embedding, item["embedding"]))
            if sim > best_sim:
                best_sim = sim
                best_name = item["name"]
        if best_sim < self.sim_threshold:
            return None, best_sim
        return best_name, best_sim

    def recognize(self, frame_bgr: np.ndarray, face_library):
        """人脸识别:检测 + 提特征 + 本地比对。

        方案6:帧级去抖——与上一帧签名比对,几乎无变化则直接复用结果,
        跳过 insightface 完整 extract,静止画面 ~0ms 返回。

        Args:
            frame_bgr: BGR 图像
            face_library: FaceStore.get() 返回的 dict
                          {"entries": [...], "matrix": ndarray}
                          或旧版 list [{name, embedding}]

        Returns:
            list[dict]: 每项 {bbox, name, similarity, score}
        """
        t0 = time.time()

        # ---- 方案6:帧级去抖,静止画面跳过推理 ----
        sig = self._frame_sig(frame_bgr)
        if self._prev_sig is not None and self._prev_results is not None:
            diff = float(np.mean(np.abs(sig.astype(np.int16)
                                        - self._prev_sig.astype(np.int16))))
            if diff < self._reuse_threshold:
                reused_ms = (time.time() - t0) * 1000
                if reused_ms > 5:
                    print(f"[Yolo] recognize reused (diff={diff:.1f} "
                          f"{reused_ms:.1f}ms)")
                return self._prev_results

        # 预缩放到 det_size,减少 insightface 内部 resize+padding 开销
        orig_h, orig_w = frame_bgr.shape[:2]
        ds = self.det_size[0]
        scale = ds / max(orig_h, orig_w)
        if scale < 1.0:
            new_w, new_h = int(orig_w * scale), int(orig_h * scale)
            frame_bgr = cv2.resize(frame_bgr, (new_w, new_h))
            sx, sy = orig_w / new_w, orig_h / new_h
        else:
            sx = sy = 1.0

        extracted = self.extract(frame_bgr)
        t1 = time.time()
        if not extracted:
            # 无人脸也更新缓存,避免下一帧重复推理空帧
            self._prev_sig = sig
            self._prev_results = []
            return []

        lib_matrix = face_library.get("matrix", None) if isinstance(face_library, dict) else None
        lib_entries = face_library["entries"] if isinstance(face_library, dict) else face_library

        # 矢量化路径(库非空)
        if lib_matrix is not None and lib_matrix.shape[0] > 0:
            self._lib_names = [e["name"] for e in lib_entries]
            matches = self.match_batch(
                [f["embedding"] for f in extracted],
                lib_matrix, self.sim_threshold,
            )
        else:
            matches = [self.match(f["embedding"], lib_entries) for f in extracted]
        t2 = time.time()

        results = []
        for f, (name, sim) in zip(extracted, matches):
            x1, y1, x2, y2 = f["bbox"]
            results.append({
                "bbox": [int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy)],
                "name": name,
                "similarity": round(sim, 4),
                "score": round(f["score"], 4),
            })

        # ---- 更新去抖缓存 ----
        self._prev_sig = sig
        self._prev_results = results

        # 诊断日志(仅耗时 >200ms 打印,避免高频帧刷屏)
        total_ms = (t2 - t0) * 1000
        if total_ms > 200:
            m = lib_matrix.shape[0] if lib_matrix is not None else len(lib_entries)
            print(f"[Yolo] recognize {total_ms:.0f}ms "
                  f"(extract={(t1-t0)*1000:.0f}ms match={(t2-t1)*1000:.1f}ms "
                  f"faces={len(extracted)} lib={m})")

        return results

    def info(self):
        return {
            "face_model": self.face_model,
            "embedding_dim": self.embedding_dim,
            "sim_threshold": self.sim_threshold,
        }
