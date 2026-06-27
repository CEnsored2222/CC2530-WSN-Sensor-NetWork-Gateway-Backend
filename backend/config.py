# -*- coding: utf-8 -*-
"""后端配置:所有参数均可通过环境变量覆盖"""
import os


class Config:
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

    # ============ 启动行为 ============
    SEED_ADMIN = os.getenv("SEED_ADMIN", "true").lower() == "true"
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

    # ============ MLP 机器学习参数 ============
    MLP_FORECAST_STEPS = (10, 20, 30, 40, 50, 60)  # 6步,60min预测窗口
    MLP_DEFAULT_HORIZON = 60             # 默认预测60分钟
    MLP_TRAIN_LR = 1e-3
    MLP_FINETUNE_LR = 1e-5               # 微调学习率更小,避免破坏预训练权重
    MLP_EPOCHS = 100
    MLP_EARLY_STOP_PATIENCE = 20
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
    MLP_MODELS_DIR = "backend/ml/models"  # 模型文件根目录
    MLP_ONNX_OPSET_VERSION = 14          # ONNX 导出 opset 版本
