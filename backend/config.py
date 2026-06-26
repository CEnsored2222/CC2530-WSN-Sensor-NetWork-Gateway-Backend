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
    DATA_FLUSH_INTERVAL = 10          # 数据入库节流间隔(秒)
    MAC_TIMEOUT_SECONDS = 10          # 设备离线判定(秒)

    # ============ 启动行为 ============
    CREATE_TABLES_ON_START = os.getenv("CREATE_TABLES", "true").lower() == "true"
    SEED_ADMIN = os.getenv("SEED_ADMIN", "true").lower() == "true"
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
