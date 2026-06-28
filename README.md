# Smart Home IoT — 基于 MQTT 与机器学习的智能家居监测控制系统

> 端-管-云一体化智能家居物联网平台，贯通「传感器采集 → 边缘处理 → MQTT 通信 → 云平台可视化 → 远程控制」全链路。

---

## 系统架构

```
┌─────────────────────────────────────────────────┐
│  前端  Vue 3 + Element Plus + ECharts            │
│  实时监控 · 设备管理 · 历史曲线 · 告警 · 预测 · 订阅  │
└──────────▲────────────────────▲─────────────────┘
    HTTP REST (JWT)       WebSocket (实时推送)
┌──────────┴────────────────────┴─────────────────┐
│  后端  Python Flask + Flask-SocketIO             │
│  REST API · MQTT 订阅 · WS 推送 · 机器学习预测    │
│  ┌──────────────────────────────────────────┐    │
│  │  MySQL 8.0 · 11 张表 · 10 分钟节流入库    │    │
│  └──────────────────────────────────────────┘    │
└──────────────────────▲──────────────────────────┘
                 MQTT 3.1.1
┌──────────────────────┴──────────────────────────┐
│  消息层  EMQX Broker                             │
│  主题: smart_home/gateway/{gw_uuid}/...          │
└──────────────────────▲──────────────────────────┘
                 MQTT
┌──────────────────────┴──────────────────────────┐
│  感知层  本地网关 (Python) + 终端节点 (串口)       │
│  温湿度传感器 · 光照传感器 · LED 控制              │
└─────────────────────────────────────────────────┘
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 通信 | MQTT 3.1.1 / EMQX |
| 后端 | Python Flask + Flask-SocketIO + Flask-CORS |
| 数据库 | MySQL 8.0 + SQLAlchemy ORM |
| 认证 | JWT (PyJWT + bcrypt) |
| 机器学习 | Scikit-learn (LinearRegression / SVR) + PyTorch + ONNX Runtime + NumPy |
| 前端 | Vue 3 + Vite + Element Plus + ECharts |
| 网关 | Python pyserial + paho-mqtt |

---

## 快速开始

### 方式一：Docker 一键部署（推荐，Linux 服务器）

> 适合服务器部署，一条命令拉起 MySQL + EMQX + 后端 + 前端全部服务。

**环境要求**：已安装 `Docker` 和 `Docker Compose v2+`。

```bash
# 1. 克隆代码
git clone <repo-url> smart-home && cd smart-home

# 2. 复制环境变量并修改密码（强烈建议修改默认值）
cp .env.example .env
vim .env

# 3. 一键构建并启动
docker compose up -d --build

# 4. 查看运行状态
docker compose ps
docker compose logs -f backend
```

启动完成后：

| 服务 | 访问地址 | 说明 |
|------|----------|------|
| 前端 | http://服务器IP/ | 浏览器访问 |
| 后端 API | http://服务器IP:5000/api/health | 健康检查 |
| EMQX Dashboard | http://服务器IP:18083 | 默认 admin / public |
| MySQL | 服务器IP:3306 | 默认 root / root1234 |

数据库会在 MySQL 容器首次启动时自动执行 [backend/init_db.sql](backend/init_db.sql) 完成建表与默认数据初始化。

常用运维命令：

```bash
docker compose down              # 停止并删除容器(保留数据)
docker compose down -v           # 停止并清空所有数据卷(慎用)
docker compose restart backend   # 重启后端
docker compose logs -f frontend  # 查看某服务日志
docker compose up -d --build     # 代码更新后重新构建
```

> 网关（gateway）需要本地串口硬件，**不参与 Docker 部署**，请在具备硬件的设备上单独运行。

---

### 方式二：本地开发部署

### 环境要求

- Python 3.9+
- Node.js 18+
- MySQL 8.0+
- EMQX 5.x

### 1. 初始化数据库

```bash
mysql -u root -p < backend/init_db.sql
```

脚本会创建 `smart_home` 库及全部 11 张表，并插入默认订阅数据。

### 2. 启动后端

```bash
cd backend
pip install -r requirements.txt

# 配置环境变量（可选，使用默认值即可）
# DATABASE_URL=mysql+pymysql://root:1234@127.0.0.1:3306/smart_home?charset=utf8mb4
# EMQX_HOST=127.0.0.1
# EMQX_PORT=1883

python app.py
# 默认运行在 http://0.0.0.0:5000
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
# 默认运行在 http://localhost:5173
```

### 4. 启动本地网关（可选）

```bash
cd gateway
pip install -r requirements.txt
python main.py
```

### 5. 注册 & 使用

1. 访问前端 → 注册账号 → 登录
2. 设备管理 → 点击「寻找网关」→ 审批网关注册请求
3. 设备卡片中执行「命名/绑定」
4. 回到首页查看实时数据流
5. 进入历史曲线 / 智能预测 / 告警管理 / 订阅管理

---

## 功能页面

| 页面 | 路由 | 说明 |
|------|------|------|
| **登录注册** | `/login` | JWT 认证，角色 user/admin |
| **首页实时监控** | `/` | WebSocket 推送实时数据流 + 30 分钟滚动折线图 + 设备卡片 |
| **设备管理** | `/devices` | 网关审批/解绑、设备命名绑定、LED/休眠下发控制 |
| **历史曲线** | `/history` | 按设备·指标·时间范围查询历史趋势，支持 CSV 导出 |
| **告警管理** | `/alerts` | 阈值规则 CRUD、支持双条件组合逻辑、三级 severity |
| **智能预测** | `/prediction` | 即时训练预测，LinearRegression / SVR / MLP ONNX 可选，历史预测记录 |
| **订阅管理** | `/admin/subscription` | 管理员控制后端 MQTT 订阅的数据类型 |
| **操作日志** | `/admin/logs` | 管理员查看用户操作审计记录 |

---

## 数据库表结构

| 表名 | 说明 |
|------|------|
| `users` | 用户表（角色 user/admin） |
| `gateways` | 网关表（UUID 标识、待审绑定） |
| `devices` | 设备表（MAC 标识、type 为 JSON 指标列表） |
| `sensor_data` | 传感器数据表（温度/湿度/光照，10 分钟节流入库） |
| `alert_rules` | 预警规则表（单/双条件组合 + severity） |
| `alert_rule_targets` | 规则-设备绑定关联表 |
| `predictions` | 预测结果表（JSON 预测点 + 历史快照） |
| `subscriptions` | 订阅管理表 |
| `operation_logs` | 操作日志表 |
| `ml_models` | MLP 模型元数据表（模型类型/版本/文件路径/训练时间） |
| `ml_evaluations` | MLP 模型评估记录表（MAE/R²/留出集指标 JSON） |

**一键建库**: `mysql -u root -p < backend/init_db.sql`

---

## MQTT 主题设计

```
smart_home/gateway/{gw_uuid}/
  ├── register                  # 上行：网关注册
  ├── register/resp             # 下行：审批结果
  ├── heartbeat                 # 上行：心跳（30s）
  ├── subscription              # 下行：订阅配置
  └── device/{dev_mac}/
        ├── discovery           # 上行：设备发现
        ├── temperature         # 上行：温度 (°C)
        ├── humidity            # 上行：湿度 (%)
        ├── light               # 上行：光照 (lx)
        ├── led                 # 上行：LED 状态 (0/1)
        ├── status              # 上行：设备状态 (active/sleep)
        └── cmd                 # 下行：控制指令 (LED/STATUS)
```

**订阅管理**：管理员在前端关闭某指标订阅时，后端执行 MQTT `unsubscribe` 对应通配符主题。

---

## 机器学习预测

系统提供两套独立的预测引擎，分别适用于轻量即时预测与高精度持续学习场景。

### 引擎一：Scikit-learn 即时预测（`/prediction`）

| 模型 | 说明 |
|------|------|
| **LinearRegression** | 线性回归基线模型，适合趋势明显的数据 |
| **SVR (RBF)** | 支持向量回归，能捕捉非线性周期波动 |

实现特点：

- **多变量特征**：每条记录构造 `[t_sec, temperature, humidity, light]` 4 维特征
- **递归多步预测**：预测 t+10 / t+20 / ... / t+60 分钟，上一步预测值影响下一步
- **即时训练**：每次点击从数据库拉取 144 条（~24h）历史数据，即训即测
- **评估指标**：MAE（平均绝对误差）+ R²（决定系数）
- **前端可视化**：历史实线 + 预测橙色虚线 双线对比图

### 引擎二：MLP ONNX 持续学习管线（`/api/predictions/mlp`）

基于 PyTorch 训练 + ONNX 导出 + onnxruntime 推理的三阶段管线，由后台调度器自动维护。

| 模型类型 | 输入特征 | 输出 |
|------|------|------|
| `mlp_temp_hum` | `[t_sec, temperature, humidity]` | 未来 6 步温湿度（10~60min） |
| `mlp_light` | `[t_sec, light]` | 未来 6 步光照（10~60min） |

实现特点：

- **预训练**：取最近 48h 数据训练 MLP，导出 ONNX + `scaler.json` + `.prev` 回滚备份
- **6 步原子写入**：`.pt.tmp` → `.onnx.tmp` → `scaler.json.tmp` → 校验 → prev 退位 → 原子替换，断电可恢复
- **自动微调**：调度器每 30min 检查，新数据 ≥15 条则用 ring buffer 微调 5 epoch（小学习率 1e-5）
- **评估触发**：微调后在同子线程立即评估，留出集后 20%，写入 `ml_evaluations` 表
- **推理缓存**：onnxruntime Session 缓存复用，避免重复加载开销
- **线程安全 ring buffer**：每设备保留 800 条（~40min @3s/条），供微调与推理快速读取
- **优雅降级**：PyTorch / onnxruntime 未安装时 MLP 引擎静默关闭，不影响 Scikit-learn 引擎

---

## 项目目录

```
End/
├── backend/              # Flask 后端
│   ├── api/              # REST 蓝图 (auth/gateway/device/data/alert/prediction/mlp/subscription)
│   ├── models/           # SQLAlchemy 模型 (含 ml.py MLP 元数据表)
│   ├── mqtt/             # MQTT 客户端 & 消息分发处理器
│   ├── ml/               # 机器学习模块
│   │   ├── mlp_models.py     # MLP 网络结构 (PyTorch)
│   │   ├── onnx_trainer.py   # 训练/微调/评估/推理/原子写入
│   │   ├── scheduler.py      # 后台调度器 (微调+评估触发)
│   │   └── models/           # 模型文件目录 (.onnx/.pt/scaler.json)
│   ├── services/         # 告警引擎 & 数据入库缓冲 & ring buffer
│   ├── ws/               # WebSocket 事件推送
│   ├── utils/            # JWT 鉴权工具
│   ├── tests/            # pytest 单元测试 (66 用例)
│   ├── app.py            # 应用工厂入口
│   ├── config.py         # 配置（环境变量覆盖 + 19 个 MLP_* 参数）
│   ├── init_db.sql       # 数据库一键初始化脚本 (11 张表)
│   ├── requirements.txt      # 生产依赖
│   └── requirements-dev.txt # 开发依赖 (pytest 等)
├── frontend/             # Vue 3 前端
│   └── src/
│       ├── views/        # 页面组件 (Home/Devices/History/Alerts/Prediction/Login + admin/)
│       ├── components/   # 通用组件 (LineChart/AlertNotify)
│       ├── api/          # HTTP 请求封装
│       ├── stores/       # Pinia 状态管理
│       ├── ws/           # WebSocket 客户端
│       └── router/       # Vue Router 路由配置
├── gateway/              # 本地网关（Python）
│   ├── main.py           # 网关入口
│   ├── mqtt_client.py    # MQTT 上行/下行封装
│   ├── serial_reader.py  # 串口读取 + 数据转发
│   ├── serial_writer.py  # 下行控制指令写入串口
│   ├── serial_parser.py  # 串口报文解析器
│   └── mac_registry.py   # MAC 列表管理（超时检测）
├── 设计文档.md           # 完整设计文档
└── README.md
```

---

## License

MIT
