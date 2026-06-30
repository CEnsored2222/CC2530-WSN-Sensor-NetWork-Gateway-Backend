# -*- coding: utf-8 -*-
"""YOLO26 目标检测封装(基于 ultralytics)。

设计文档第 4.4 节图像处理流程:
    BGR numpy 数组 → YOLO26 model(frame) → results.boxes → 类别/置信度/bbox
"""

import cv2
import numpy as np

from config import Config


class Detector:
    """YOLO26 检测器封装。"""

    def __init__(self):
        # 延迟导入,避免模块加载时即触发模型下载
        from ultralytics import YOLO

        weights = Config.WEIGHTS
        # ultralytics 包会自动处理 yolo26n.pt 文件名(若不存在则下载)
        self.model = YOLO(weights)
        self.weights = weights
        self.device = Config.DEVICE or None  # None=自动
        self.imgsz = Config.IMGSZ
        self.default_conf = Config.CONF_THRES
        self.default_iou = Config.IOU_THRES
        self.end2end = Config.END2END

        # 类别表 {id: name}
        self.names = self.model.names if hasattr(self.model, "names") else {}
        # 缓存设备信息(供 /health 返回)
        try:
            import torch
            if torch.cuda.is_available() and not (Config.DEVICE or "").lower() == "cpu":
                self.device_repr = "cuda:0" if Config.DEVICE in ("", None) else Config.DEVICE
            else:
                self.device_repr = "cpu"
        except Exception:
            self.device_repr = Config.DEVICE or "cpu"

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
            annotated_bgr: 画好框的 BGR 图像
        """
        kwargs = dict(
            conf=conf if conf is not None else self.default_conf,
            iou=iou if iou is not None else self.default_iou,
            imgsz=self.imgsz,
            verbose=False,
        )
        if self.device:
            kwargs["device"] = self.device
        if classes:
            kwargs["classes"] = classes
        # END2END 模式下 ultralytics 默认无需 NMS;非端到端时 iou 参数生效

        results = self.model(frame_bgr, **kwargs)
        detections = []
        annotated = frame_bgr.copy()

        if not results:
            return detections, annotated

        res = results[0]
        boxes = res.boxes
        if boxes is None or len(boxes) == 0:
            return detections, annotated

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

        # 用 ultralytics 内置绘图(等价于 res.plot())
        try:
            annotated = res.plot()
        except Exception:
            # 降级:手动绘制
            for d in detections:
                x1, y1, x2, y2 = d["bbox"]
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"{d['class']} {d['confidence']:.2f}"
                cv2.putText(annotated, label, (x1, max(y1 - 6, 12)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        return detections, annotated

    def model_info(self):
        """返回模型信息(供 /api/model_info 接口)。"""
        classes_list = [{"id": i, "name": n} for i, n in self.names.items()]
        return {
            "classes": classes_list,
            "total": len(classes_list),
            "weights": self.weights,
            "device": self.device_repr,
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
