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
