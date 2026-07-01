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

CPU 优化说明(网关集成场景):
    1. OPENVINO_MODEL: 指定 OpenVINO 导出模型目录路径。若设置且目录存在,
       Detector 会加载 OpenVINO 模型而非 PyTorch .pt,CPU 推理可提速 2-3 倍。
       导出方法: model.export(format="openvino", imgsz=480)
    2. IMGSZ: 降低推理分辨率可大幅提升 CPU 速度。480 对日常检测足够,
       320 适合极端低延迟场景(精度略降)。640 为标准值。
    3. HALF: GPU 时启用 FP16 加速;CPU 时自动忽略(CPU 无 FP16 硬件单元)。
    4. 运行时自动导出: 若 OPENVINO_MODEL 留空但 FORCE_OPENVINO=True,
       首次启动时自动导出 OpenVINO 模型到 weights 同级目录。
"""


class Config:
    # ============ YOLO26 目标检测 ============
    WEIGHTS = "yolo26n.pt"
    DEVICE = ""             # 空=自动检测(独显GPU/集显CPU);"cpu"=强制CPU;"0"=GPU0
    IMGSZ = 480             # 推理分辨率(480 兼顾速度与精度;320 极速;640 标准)
    CONF_THRES = 0.35
    IOU_THRES = 0.45
    END2END = True
    HALF = False            # FP16 在新版 ultralytics 已弃用且对 yolo26n 无提速,关闭

    # =========OpenVINO 加速(CPU 场景) ============
    # 指定 OpenVINO 导出模型目录(如 "yolo26n_openvino_model/")。
    # 留空则不使用 OpenVINO,除非 FORCE_OPENVINO=True 时首次自动导出。
    OPENVINO_MODEL = ""
    # True=首次启动时若未找到 OpenVINO 模型,自动从 .pt 导出(需联网下载依赖)
    FORCE_OPENVINO = True

    # ============ insightface 人脸识别 ============
    # buffalo_s: 轻量模型,CPU 上 ~100-200ms/帧,推荐日常使用
    # buffalo_l: 重量模型,CPU 上 ~1-3s/帧,仅 GPU 场景推荐
    FACE_MODEL = "buffalo_s"
    FACE_DET_SIZE = 320  # 240=极速(推荐), 320=均衡, 480=高精度
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
