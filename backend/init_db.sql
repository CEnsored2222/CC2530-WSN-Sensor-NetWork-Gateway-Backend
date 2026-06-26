-- ============================================
-- Smart Home 数据库一键初始化脚本
-- 用法: mysql -u root -p < init_db.sql
-- ============================================

CREATE DATABASE IF NOT EXISTS smart_home
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE smart_home;

-- ============================================
-- 1. users  用户表
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id          BIGINT          NOT NULL AUTO_INCREMENT,
    username    VARCHAR(64)     NOT NULL,
    password_hash VARCHAR(255)  NOT NULL,
    role        ENUM('user','admin') NOT NULL DEFAULT 'user',
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 2. gateways  网关表
-- ============================================
CREATE TABLE IF NOT EXISTS gateways (
    id          BIGINT          NOT NULL AUTO_INCREMENT,
    gw_uuid     VARCHAR(36)     NOT NULL,
    user_id     BIGINT          NULL,
    name        VARCHAR(64)     NULL,
    status      ENUM('pending','approved','rejected','offline','online') NOT NULL DEFAULT 'pending',
    hostname    VARCHAR(128)    NULL,
    ip          VARCHAR(45)     NULL,
    last_seen   DATETIME        NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at DATETIME        NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_gw_uuid (gw_uuid),
    CONSTRAINT fk_gateways_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 3. devices  设备表
-- ============================================
CREATE TABLE IF NOT EXISTS devices (
    id          BIGINT          NOT NULL AUTO_INCREMENT,
    gateway_id  BIGINT          NOT NULL,
    mac         VARCHAR(32)     NOT NULL,
    name        VARCHAR(64)     NULL,
    type        JSON            NULL COMMENT '设备可采集的数据类型列表,如["temperature","humidity"]',
    bound       TINYINT(1)      NOT NULL DEFAULT 0,
    last_seen   DATETIME        NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_gateway_mac (gateway_id, mac),
    CONSTRAINT fk_devices_gateway FOREIGN KEY (gateway_id) REFERENCES gateways(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 4. subscriptions  订阅管理表
-- ============================================
CREATE TABLE IF NOT EXISTS subscriptions (
    id          BIGINT          NOT NULL AUTO_INCREMENT,
    metric      ENUM('temperature','humidity','light','led_status','device_status') NOT NULL,
    subscribed  TINYINT(1)      NOT NULL DEFAULT 1,
    updated_by  BIGINT          NULL,
    updated_at  DATETIME        NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_metric (metric),
    CONSTRAINT fk_subscriptions_user FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- subscriptions 默认数据：全部指标默认订阅
INSERT INTO subscriptions (metric, subscribed) VALUES
    ('temperature',    1),
    ('humidity',       1),
    ('light',          1),
    ('led_status',     1),
    ('device_status',  1)
ON DUPLICATE KEY UPDATE subscribed = VALUES(subscribed);

-- ============================================
-- 5. sensor_data  传感器数据表
-- ============================================
CREATE TABLE IF NOT EXISTS sensor_data (
    id          BIGINT          NOT NULL AUTO_INCREMENT,
    device_id   BIGINT          NOT NULL,
    temperature DECIMAL(5,2)    NULL,
    humidity    DECIMAL(5,2)    NULL,
    light       INT             NULL,
    recorded_at DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_device_time (device_id, recorded_at),
    CONSTRAINT fk_sensor_data_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 6. predictions  预测结果表
-- ============================================
CREATE TABLE IF NOT EXISTS predictions (
    id              BIGINT          NOT NULL AUTO_INCREMENT,
    device_id       BIGINT          NOT NULL,
    metric          ENUM('temperature','humidity','light') NOT NULL,
    horizon_minutes INT             NOT NULL DEFAULT 30,
    predicted_values JSON           NOT NULL,
    history_snapshot JSON           NULL,
    model_name      VARCHAR(64)     NOT NULL,
    mae             FLOAT           NULL,
    r2              FLOAT           NULL,
    predicted_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_dev_metric_time (device_id, metric, predicted_at),
    CONSTRAINT fk_predictions_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 7. operation_logs  操作日志表
-- ============================================
CREATE TABLE IF NOT EXISTS operation_logs (
    id          BIGINT          NOT NULL AUTO_INCREMENT,
    user_id     BIGINT          NULL,
    action      VARCHAR(64)     NOT NULL,
    target_type VARCHAR(32)     NULL,
    target_id   BIGINT          NULL,
    detail      TEXT            NULL,
    ip          VARCHAR(45)     NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_operation_logs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 8. alert_rules  预警规则表
-- ============================================
CREATE TABLE IF NOT EXISTS alert_rules (
    id              BIGINT          NOT NULL AUTO_INCREMENT,
    name            VARCHAR(64)     NOT NULL,
    metric          ENUM('temperature','humidity','light') NOT NULL,
    operator        ENUM('gt','lt','gte','lte','eq') NOT NULL,
    threshold       DECIMAL(10,2)   NOT NULL,
    logic           ENUM('and','or','none') NOT NULL DEFAULT 'none',
    second_metric   ENUM('temperature','humidity','light') NULL,
    second_operator ENUM('gt','lt','gte','lte','eq') NULL,
    second_threshold DECIMAL(10,2)  NULL,
    severity        ENUM('info','warning','critical') NOT NULL DEFAULT 'warning',
    notify          TINYINT(1)      NOT NULL DEFAULT 0,
    enabled         TINYINT(1)      NOT NULL DEFAULT 1,
    user_id         BIGINT          NOT NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_alert_rules_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 9. alert_rule_targets  预警规则 - 设备绑定表
-- ============================================
CREATE TABLE IF NOT EXISTS alert_rule_targets (
    id          BIGINT          NOT NULL AUTO_INCREMENT,
    rule_id     BIGINT          NOT NULL,
    gateway_id  BIGINT          NOT NULL,
    device_id   BIGINT          NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX ix_alert_rule_targets_rule (rule_id),
    INDEX ix_alert_rule_targets_lookup (gateway_id, device_id),
    CONSTRAINT fk_art_rule    FOREIGN KEY (rule_id)    REFERENCES alert_rules(id) ON DELETE CASCADE,
    CONSTRAINT fk_art_gateway FOREIGN KEY (gateway_id) REFERENCES gateways(id)    ON DELETE CASCADE,
    CONSTRAINT fk_art_device  FOREIGN KEY (device_id)  REFERENCES devices(id)     ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
