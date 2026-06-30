# -*- coding: utf-8 -*-
"""后端配置:所有参数均可通过环境变量覆盖"""
import os


class Config:
    # ============ 版本 ============
    VERSION = "2.8"

    # ============ Flask ============
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:1234@127.0.0.1:3306/smart_home?charset=utf8mb4",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ============ JWT ============
    JWT_SECRET = os.getenv("JWT_SECRET", "jwt-secret-change-me")
    JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

    # ============ MQTT ============
    MQTT_HOST = os.getenv("EMQX_HOST", "127.0.0.1")
    MQTT_PORT = int(os.getenv("EMQX_PORT", "1883"))
    MQTT_USERNAME = os.getenv("EMQX_USERNAME", "")
    MQTT_PASSWORD = os.getenv("EMQX_PASSWORD", "")
    MQTT_KEEPALIVE = int(os.getenv("EMQX_KEEPALIVE", "60"))

    # ============ 业务参数 ============
    TOPIC_PREFIX = "smart_home/gateway"
    DATA_FLUSH_INTERVAL = 600          # 数据入库节流间隔(秒)

    # ============ 邮箱验证码 ============
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
    SMTP_USER = os.getenv("SMTP_USER", "2186277326@qq.com")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "wbffjlmiznypecei")
    CODE_EXPIRE_MINUTES = int(os.getenv("CODE_EXPIRE_MINUTES", "5"))
    CODE_RATE_LIMIT_SECONDS = int(os.getenv("CODE_RATE_LIMIT_SECONDS", "60"))

    # ============ 启动行为 ============
    SEED_ADMIN = os.getenv("SEED_ADMIN", "true").lower() == "true"
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

    # ============ MLP 机器学习参数 ============
    MLP_FORECAST_STEPS = (10, 20, 30, 40, 50, 60)  # 6步,60min预测窗口
    MLP_DEFAULT_HORIZON = 60             # 默认预测60分钟
    MLP_TRAIN_LR = 1e-3
    MLP_FINETUNE_LR = 1e-5               # 微调学习率更小,避免破坏预训练权重
    MLP_EPOCHS = 300                      # 预训练 epoch 数(增强特征需更多轮次收敛)
    MLP_EARLY_STOP_PATIENCE = 30          # 早停耐心(配合 epochs 增大)
    MLP_FINETUNE_EPOCHS = 5              # 微调 epoch 数
    MLP_MIN_SAMPLES = 12                 # 预训练最小样本数
    MLP_BATCH_SIZE = 16                  # 训练 batch_size 上限(实际用 max(2, min(16, len(X))))
    MLP_PRETRAIN_HOURS = 48              # 预训练取最近48h(覆盖>=2个日周期)
    MLP_FINETUNE_HOURS = 2               # 微调取 last_train_time 之后最多2h
    MLP_LOOKBACK_HOURS = 12              # 推理取最近12h数据
    MLP_FINETUNE_MIN_SAMPLES = 15        # 微调最少新数据条数
    MLP_FINETUNE_INTERVAL = 1800         # 自动微调最小间隔30分钟
    MLP_EVAL_MIN_SAMPLES = 3             # 评估最少留出样本条数
    MLP_EVAL_SPLIT_RATIO = 0.2           # 评估留出集比例(后20%)
    MLP_RING_BUFFER_CAPACITY = 800       # 每设备保留条数(约40min @3s/条)
    MLP_SCHEDULER_CHECK_INTERVAL = 60    # 调度器检查间隔
    MLP_MODELS_DIR = "ml/models"  # 模型文件根目录(相对于 backend 运行目录)
    MLP_ONNX_OPSET_VERSION = 14          # ONNX 导出 opset 版本

    # ============ 视觉模块 ============
    # 本地 Yolo 服务公网地址(下发给前端直连,见设计文档第 6.5 节)
    YOLO_SERVICE_URL = os.getenv("YOLO_SERVICE_URL", "http://127.0.0.1:6001")
    # Yolo↔后端内部通信共享密钥(两端必须一致)
    VISION_INTERNAL_TOKEN = os.getenv("VISION_INTERNAL_TOKEN", "zheshiyigetoken")
