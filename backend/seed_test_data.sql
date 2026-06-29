-- ============================================
-- MLP 测试数据初始化脚本
-- 创建测试网关绑定 + 设备 + 模拟传感器数据
-- ============================================

USE smart_home;

-- 1. 绑定 admin 用户( id=2 )到网关1
INSERT IGNORE INTO user_gateways (user_id, gateway_id, name)
VALUES (2, 1, 'MLP测试网关');

-- 2. 创建4个新设备（id=33,34,35,36）到网关1
INSERT IGNORE INTO devices (id, gateway_id, mac, name, type, bound, last_seen) VALUES
(33, 1, 'SEED:AA:BB:CC:01', 'MLP-温度湿度-1', '["temperature","humidity","light"]', 1, NOW()),
(34, 1, 'SEED:AA:BB:CC:02', 'MLP-温度湿度-2', '["temperature","humidity","light"]', 1, NOW()),
(35, 1, 'SEED:AA:BB:CC:03', 'MLP-温度湿度-3', '["temperature","humidity","light"]', 1, NOW()),
(36, 1, 'SEED:AA:BB:CC:04', 'MLP-温度湿度-4', '["temperature","humidity","light"]', 1, NOW());

-- 3. 校验
SELECT '=== devices ===' AS info;
SELECT id, mac, name FROM devices WHERE id IN (33,34,35,36);
SELECT '=== user_gateways ===' AS info;
SELECT * FROM user_gateways;
