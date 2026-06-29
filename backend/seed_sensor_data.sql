-- ============================================================
-- sensor_data 模拟数据填充脚本
-- 4 个设备 (id=33,34,35,36) × 历史 72h × 每 10min 一组
-- 共 432 × 4 = 1728 条
--
-- 用法:
--   mysql -u root -p smart_home < seed_sensor_data.sql
-- 或在已USE smart_home后:  SOURCE seed_sensor_data.sql;
-- ============================================================

USE smart_home;

-- 清空旧模拟数据(可选,注释掉则追加)
DELETE FROM sensor_data WHERE device_id IN (33, 34, 35, 36);

-- 自定义函数:4 小时余数(用于昼夜节律)
DROP FUNCTION IF EXISTS mod4h;
DELIMITER $$
CREATE FUNCTION mod4h(n INT) RETURNS INT DETERMINISTIC
BEGIN
    RETURN n - FLOOR(n / 4) * 4;
END$$
DELIMITER ;

-- ============================================================
-- 存储过程:批量插入模拟数据
-- ============================================================
DROP PROCEDURE IF EXISTS seed_sensor_data;
DELIMITER $$
CREATE PROCEDURE seed_sensor_data()
BEGIN
    DECLARE i INT DEFAULT 0;          -- 时间偏移(0=72h前, 431=最近)
    DECLARE d INT DEFAULT 33;         -- 当前 device_id
    DECLARE ts DATETIME;
    DECLARE t DECIMAL(5,2);
    DECLARE h DECIMAL(5,2);
    DECLARE l INT;
    DECLARE tBase DECIMAL(5,2);

    WHILE i < 432 DO
        -- 当前样本时间戳:从 NOW() 往前推 (431 - i) * 10 分钟
        SET ts = DATE_SUB(NOW(), INTERVAL (431 - i) * 10 MINUTE);

        WHILE d <= 36 DO
            -- 每个设备基线略不同(33:凉, 34:中, 35:暖, 36:最暖)
            SET tBase = 22.00 + (d - 33) * 1.50;

            -- 温度:基线 + 昼夜正弦波 + 每设备相位偏移 + 微噪声
            SET t = tBase
                  + 4.00 * SIN(2 * PI() * mod4h(FLOOR(i / 6)) / 4)
                  + 0.50 * (d - 33)
                  + ROUND((RAND() - 0.5) * 1.0, 2);

            -- 湿度:与温度反相关,基线 55% ± 昼夜波动 ± 噪声
            SET h = 55.00
                  - 8.00 * SIN(2 * PI() * mod4h(FLOOR(i / 6)) / 4)
                  + (d - 33) * 2.00
                  + ROUND((RAND() - 0.5) * 3.0, 2);

            -- 光照:白天高 / 夜晚低,带噪声;白天定义为 6-18 时
            IF HOUR(ts) BETWEEN 6 AND 18 THEN
                SET l = 400 + FLOOR(RAND() * 350);   -- 400~750 lux
            ELSE
                SET l = FLOOR(RAND() * 30);           -- 0~29 lux
            END IF;

            INSERT INTO sensor_data (device_id, temperature, humidity, light, recorded_at)
            VALUES (d, t, h, l, ts);

            SET d = d + 1;
        END WHILE;

        SET d = 33;
        SET i = i + 1;
    END WHILE;
END$$
DELIMITER ;

-- 执行
CALL seed_sensor_data();

-- 清理临时对象
DROP PROCEDURE IF EXISTS seed_sensor_data;
DROP FUNCTION IF EXISTS mod4h;

-- 校验
SELECT device_id, COUNT(*) AS cnt, MIN(recorded_at) AS oldest, MAX(recorded_at) AS newest
FROM sensor_data
WHERE device_id IN (33, 34, 35, 36)
GROUP BY device_id
ORDER BY device_id;
