# -*- coding: utf-8 -*-
"""Yolo 视觉推理服务配置(硬编码,部署时手动修改本文件)。

不再使用环境变量,所有配置直接写死在下方。部署到不同机器时,直接编辑本文件。

两台设备适配说明:
    DEVICE 留空("")= 自动检测:
        - 独显机器(有 NVIDIA GPU + CUDA)→ 自动用 GPU
        - 集显机器(无 CUDA)→ 自动用 CPU
      两台设备可用同一份 config.py,无需为硬件改配置。
    如需强制指定:
        DEVICE = "cpu"   强制 CPU(集显机器若自动检测异常时用)
        DEVICE = "0"      强制 GPU 0(独显机器)
"""


class Config:
    # ============ YOLO26 目标检测 ============
    WEIGHTS = "yolo26n.pt"
    DEVICE = "cpu"          # 空=自动检测(独显GPU/集显CPU);"cpu"=强制CPU;"0"=GPU0
    IMGSZ = 640
    CONF_THRES = 0.35
    IOU_THRES = 0.45
    END2END = True

    # ============ insightface 人脸识别 ============
    FACE_MODEL = "buffalo_l"
    FACE_DET_SIZE = 640
    FACE_SIM_THRESHOLD = 0.5

    # ============ 服务与通信(★ 部署时必填) ============
    PORT = 6001
    HOST = "127.0.0.1"
    BACKEND_URL = "http://127.0.0.1:5000"  # 改为云端 Atmos 后端地址
    INTERNAL_TOKEN = "zheshiyigetoken"     # 与云端 .env 的 VISION_INTERNAL_TOKEN 保持一致

    # ============ face_library 缓存 ============
    FACE_CACHE_TTL = 30  # 秒

    # ============ 图像编解码 ============
    JPEG_QUALITY = 80

    @classmethod
    def validate(cls):
        """校验必填项,返回错误消息列表(空表示通过)。"""
        errs = []
        if not cls.BACKEND_URL:
            errs.append("BACKEND_URL 未设置(请编辑 config.py 填写云端后端地址)")
        if not cls.INTERNAL_TOKEN:
            errs.append("INTERNAL_TOKEN 未设置(请编辑 config.py 填写内部共享密钥)")
        return errs
