# -*- coding: utf-8 -*-
"""YOLO26 目标检测封装(基于 ultralytics)。

设计文档第 4.4 节图像处理流程:
    BGR numpy 数组 → YOLO26 model(frame) → results.boxes → 类别/置信度/bbox

性能优化:
    1. 显式设备管理: 修复 DEVICE="" 时未传 device 导致默认跑 CPU 的 bug
    2. OpenVINO 加速: CPU 场景下自动加载 OpenVINO 导出模型,提速 2-3 倍
    3. FP16 半精度: 可配置(HALF=True 时 GPU 启用;CPU 自动忽略)
    4. 降低 imgsz: 默认 480(可配置),减少计算量
    5. 预热推理: 启动时跑一帧 dummy,避免首帧冷启动延迟
    6. 轻量返回: detect() 不再生成标注图,由前端本地绘制(省去 JPEG 编解码往返)
"""

import os

import cv2
import numpy as np

from config import Config


class Detector:
    """YOLO26 检测器封装。"""

    def __init__(self):
        from ultralytics import YOLO
        import torch

        weights = Config.WEIGHTS
        self.weights = weights  # 供 /health 返回
        self.imgsz = Config.IMGSZ
        self.default_conf = Config.CONF_THRES
        self.default_iou = Config.IOU_THRES
        self.end2end = Config.END2END

        # ---- 显式解析设备 ----
        # 修复根因: 原代码 self.device = Config.DEVICE or None,
        # 当 DEVICE="" 时 device=None (falsy),detect() 中 if self.device 不执行,
        # 导致 model() 不传 device 参数,ultralytics 默认在 CPU 推理。
        device_cfg = (Config.DEVICE or "").strip()
        if device_cfg.lower() == "cpu":
            self.device = "cpu"
        elif device_cfg:  # 如 "0", "cuda:0", "cuda:1"
            self.device = device_cfg
        else:  # 空=自动检测
            self.device = "0" if torch.cuda.is_available() else "cpu"

        self.is_gpu = self.device != "cpu"
        # FP16 仅在 GPU 时有意义;CPU 无 FP16 硬件单元,启用反而可能变慢
        self.use_half = Config.HALF and self.is_gpu

        # ---- 加载模型(优先 OpenVINO 加速 CPU) ----
        self.model = self._load_model(weights)

        # 类别表 {id: name}
        self.names = self.model.names if hasattr(self.model, "names") else {}

        # 设备信息(供 /health 返回)
        if self.is_gpu:
            self.device_repr = f"cuda:{self.device}" if self.device.isdigit() else self.device
        else:
            self.device_repr = "cpu"
        if self._using_openvino:
            self.device_repr += " (OpenVINO)"

        # ---- 预热推理(避免首帧冷启动延迟) ----
        self._warmup()

    def _load_model(self, weights: str):
        """加载模型,优先 OpenVINO(CPU 场景),回退 PyTorch .pt。"""
        self._using_openvino = False

        # CPU 场景:尝试加载 OpenVINO 导出模型
        if not self.is_gpu:
            ov_path = Config.OPENVINO_MODEL
            if not ov_path and Config.FORCE_OPENVINO:
                # 自动导出 OpenVINO 模型
                ov_path = self._try_export_openvino(weights)
            if ov_path and os.path.isdir(ov_path):
                from ultralytics import YOLO
                print(f"[Yolo] 加载 OpenVINO 模型: {ov_path}")
                model = YOLO(ov_path, task="detect")
                self._using_openvino = True
                return model

        # GPU 或无 OpenVINO:加载 PyTorch .pt
        from ultralytics import YOLO
        model = YOLO(weights)
        # 显式将模型移至目标设备(GPU 时必须,否则权重留在 CPU)
        if self.is_gpu:
            target = f"cuda:{self.device}" if self.device.isdigit() else self.device
            model.to(target)
        return model

    def _try_export_openvino(self, weights: str) -> str:
        """首次启动时自动导出 OpenVINO 模型,返回导出目录路径。失败返回空串。"""
        try:
            from ultralytics import YOLO
            print(f"[Yolo] 首次启动,自动导出 OpenVINO 模型(imgsz={self.imgsz})...")
            pt_model = YOLO(weights)
            export_path = pt_model.export(
                format="openvino",
                imgsz=self.imgsz,
                half=False,  # CPU 无需 FP16
                dynamic=False,
            )
            print(f"[Yolo] OpenVINO 导出完成: {export_path}")
            return str(export_path)
        except Exception as e:
            print(f"[Yolo] OpenVINO 自动导出失败(回退 PyTorch): {e}")
            return ""

    def _warmup(self):
        """预热推理:跑一帧 dummy 数据,触发 CUDA kernel 编译 / OpenVINO 图优化。"""
        try:
            dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
            kwargs = dict(
                conf=self.default_conf,
                iou=self.default_iou,
                imgsz=self.imgsz,
                verbose=False,
                device=self.device,
            )
            if self.use_half:
                kwargs["half"] = True
            self.model(dummy, **kwargs)
            print(f"[Yolo] 预热完成(device={self.device_repr})")
        except Exception as e:
            print(f"[Yolo] 预热失败(不影响后续推理): {e}")

    def detect(self, frame_bgr: np.ndarray, conf: float = None, iou: float = None,
               classes: list = None):
        """执行目标检测。

        Args:
            frame_bgr: BGR 格式 numpy 数组
            conf: 置信度阈值,None 取配置默认
            iou: IoU 阈值,None 取配置默认
            classes: 限定类别 ID 列表(如 [0, 2, 5]),None 表示全部

        Returns:
            list[dict]: 每项 {class, class_id, confidence, bbox:[x1,y1,x2,y2]}
        """
        kwargs = dict(
            conf=conf if conf is not None else self.default_conf,
            iou=iou if iou is not None else self.default_iou,
            imgsz=self.imgsz,
            verbose=False,
            device=self.device,  # 始终显式传入设备
        )
        if self.use_half:
            kwargs["half"] = True
        if classes:
            kwargs["classes"] = classes
        # END2END 模式下 ultralytics 默认无需 NMS;非端到端时 iou 参数生效

        results = self.model(frame_bgr, **kwargs)
        detections = []

        if not results:
            return detections

        res = results[0]
        boxes = res.boxes
        if boxes is None or len(boxes) == 0:
            return detections

        # 遍历每个检测框
        for i in range(len(boxes)):
            cls_id = int(boxes.cls[i].item())
            conf_val = float(boxes.conf[i].item())
            x1, y1, x2, y2 = boxes.xyxy[i].tolist()
            cls_name = self.names.get(cls_id, str(cls_id))
            detections.append({
                "class": cls_name,
                "class_id": cls_id,
                "confidence": round(conf_val, 4),
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
            })

        return detections

    def model_info(self):
        """返回模型信息(供 /api/model_info 接口)。"""
        classes_list = [{"id": i, "name": n} for i, n in self.names.items()]
        return {
            "classes": classes_list,
            "total": len(classes_list),
            "weights": Config.WEIGHTS,
            "device": self.device_repr,
            "imgsz": self.imgsz,
            "half": self.use_half,
            "openvino": self._using_openvino,
        }


def encode_image_b64(frame_bgr: np.ndarray, quality: int = None) -> str:
    """BGR 图像 → JPEG base64(带 data: 前缀)。"""
    if quality is None:
        quality = Config.JPEG_QUALITY
    ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return ""
    import base64
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")
