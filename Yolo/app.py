# -*- coding: utf-8 -*-
"""Yolo 视觉推理服务入口。

启动流程:
1. 校验必填配置(BACKEND_URL / INTERNAL_TOKEN,见 config.py 硬编码)。
2. 加载 YOLO26 检测器 + insightface 人脸识别器(首次运行自动下载权重)。
3. 初始化 face_store(从后端拉取人脸库的缓存)。
4. 注册 Flask 蓝图,监听 Config.PORT。

启动:
    先编辑 config.py 填写 BACKEND_URL 与 INTERNAL_TOKEN,然后:
    python app.py
"""

import os
import sys

# 将 torch 自带的 CUDA 运行时库(cuBLAS/cuDNN)加入 PATH,
# 使 onnxruntime-gpu 能找到 CUDA DLL,启用 insightface GPU 加速
try:
    import torch as _torch
    _torch_lib = os.path.join(os.path.dirname(_torch.__file__), 'lib')
    if os.path.isdir(_torch_lib):
        os.environ['PATH'] = _torch_lib + os.pathsep + os.environ.get('PATH', '')
except ImportError:
    pass

from flask import Flask
from flask_cors import CORS

from config import Config
from face_store import FaceStore


def create_app() -> Flask:
    app = Flask(__name__)
    # 允许前端跨域访问(前端直连 Yolo 服务)
    CORS(app)

    # 1. 校验配置
    errs = Config.validate()
    if errs:
        print("[Yolo] 配置校验失败:")
        for e in errs:
            print(f"  - {e}")
        print("[Yolo] 请通过环境变量设置后重试。")
        sys.exit(1)

    print(f"[Yolo] BACKEND_URL = {Config.BACKEND_URL}")
    print(f"[Yolo] WEIGHTS     = {Config.WEIGHTS}")
    print(f"[Yolo] DEVICE      = {Config.DEVICE or '(auto)'}")
    print(f"[Yolo] PORT         = {Config.PORT}")

    # 2. 加载模型(可能耗时较长,首次会下载权重)
    print("[Yolo] 正在加载 YOLO26 检测器...")
    try:
        from detector import Detector
        detector = Detector()
        app.detector = detector
        print(f"[Yolo] YOLO26 加载完成(device={detector.device_repr}, "
              f"classes={len(detector.names)})")
    except Exception as e:
        print(f"[Yolo] YOLO26 加载失败: {e}")
        app.detector = None

    print("[Yolo] 正在加载 insightface 人脸识别器...")
    try:
        from recognizer import Recognizer
        recognizer = Recognizer()
        app.recognizer = recognizer
        print(f"[Yolo] insightface 加载完成(model={Config.FACE_MODEL}, "
              f"dim={recognizer.embedding_dim})")
    except Exception as e:
        print(f"[Yolo] insightface 加载失败: {e}")
        app.recognizer = None

    # 3. 人脸库缓存(后端不可达不阻断启动,recognize 时再处理)
    app.face_store = FaceStore()
    print("[Yolo] face_store 已就绪")

    # 4. 注册路由
    from routes import bp
    app.register_blueprint(bp)

    return app


if __name__ == "__main__":
    app = create_app()
    print(f"[Yolo] 服务启动: http://{Config.HOST}:{Config.PORT}")
    # 前端直连不鉴权,需监听公网;threaded=True 支持并发逐帧请求
    app.run(host=Config.HOST, port=Config.PORT, threaded=True)
