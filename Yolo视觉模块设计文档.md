# Atmos 视觉模块(YOLO26 + 人脸识别)设计文档

> 版本:v1.1  日期:2026-06-30
> 主文档:[设计文档.md](file:///d:/Code/End/设计文档.md)(Atmos 平台 v2.4)
> 参考文档:`YOLOv5_Flask部署使用说明.docx`
> YOLO26 官方文档:`https://docs.ultralytics.com/zh/models/yolo26`

---

## 一、项目概述

### 1.1 背景

Atmos 智能家居平台已具备传感器采集、MQTT 通信、Web 可视化、机器学习预测等能力,但缺少**视觉感知**维度。本设计在现有平台基础上新增"目标检测 + 人脸身份识别"能力,参考 `YOLOv5_Flask部署使用说明.docx` 的 Flask + 检测模型方案,将其中的 YOLOv5 替换为最新的 **YOLO26**,并扩展人脸身份识别、接入 Atmos 统一鉴权与云端人脸库。

### 1.2 设计目标

1. 提供基于 **YOLO26** 的实时目标检测(浏览器摄像头逐帧推理,返回边界框 + 类别 + 置信度)。
2. 提供基于 **insightface** 的人脸身份识别(提取 512 维特征,与云端人脸库比对,返回姓名 + 相似度)。
3. 视觉推理服务**部署在本地机器**(具备公网 IP 与 GPU),不部署在云端服务器(服务器性能不足)。
4. **前端直连 Yolo 服务**做实时检测/识别(低延迟,不经后端);仅在人脸绑定/身份认证等需要云端数据时,Yolo 才与后端通信。
5. 人脸库**持久化到云端 MySQL**,实时检测结果不持久化(仅看实时画面)。

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| 实时链路最短 | 前端 ↔ Yolo 直连(公网 IP),避免后端转发带来的延迟与带宽压力 |
| Yolo 按需连后端 | 仅"人脸识别拉取人脸库""人脸注册提特征"两类场景 Yolo ↔ 后端通信 |
| Yolo 做本地比对 | 人脸识别时 Yolo 从后端拉取该用户 `face_library` 后本地余弦比对,不逐帧请求后端 |
| 数据云端化 | 人脸库存云端 MySQL(管理操作走后端);实时检测/识别结果不持久化 |
| 简化实现 | 移除参考文档"连续帧告警";输入仅浏览器摄像头;前端直连 Yolo 不鉴权 |

### 1.4 与参考文档(YOLOv5_Flask)的差异

| 维度 | 参考文档(YOLOv5) | 本设计(YOLO26) |
|------|--------------------|-------------------|
| 检测模型 | YOLOv5s.pt(`torch.hub`/DetectMultiBackend) | YOLO26n.pt(`ultralytics` 包,原生端到端无需 NMS) |
| 识别能力 | 仅目标检测 | 目标检测 + 人脸身份识别(insightface) |
| 输入模式 | 摄像头 / 视频 / 图片 三种 | 仅浏览器摄像头(逐帧 base64) |
| 告警模块 | 连续帧告警(默认 15 帧,红色脉冲) | **删除**(本模块不做告警) |
| 前端链路 | 前端 → Flask 后端 → 模型 | 前端 → Yolo(直连);Yolo ↔ 后端(仅人脸库/注册) |
| 鉴权 | 无 | 前端↔Yolo 不鉴权;前端↔后端 JWT;Yolo↔后端 服务 token |
| 数据持久化 | 无 | 仅人脸库存云端 MySQL;实时结果不持久化 |
| 部署位置 | 单机 | 云端(Atmos)+ 本地(Yolo 推理)分离部署 |

---

## 二、系统架构

### 2.1 架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│  用户浏览器  /vision 页                                              │
│   getUserMedia 采集 → Canvas 绘框                                    │
└───▲───────────────────────▲───────────────────────▲──────────────┘
    │ [1] 实时检测/识别(直连) │ [2] 人脸库管理(JWT)    │ [2] 取 Yolo 地址(JWT)
    │   base64 帧 / 无鉴权     │   注册/列表/删除        │
    │                         │                        │
    │              ┌──────────┴───────────┐            │
    │              │                      │            │
    │              ▼                      ▼            ▼
┌───┴────────────────────────┐  ┌──────────────────────────────────┐
│  本地 Yolo 服务(公网 IP)    │  │  云端 Atmos 后端(Flask)            │
│  - POST /api/detect        │  │  - GET  /api/vision/endpoint       │
│  - POST /api/recognize     │  │    (返回 Yolo 公网地址给前端)       │
│    [3] 内部拉 face_library │─▶│  - GET  /api/vision/internal/faces │
│    本地余弦比对             │  │    (Yolo 拉人脸库,服务 token)       │
│  - POST /api/face/embed    │◀─│  - POST /api/vision/faces          │
│    [3] 后端注册时调用提特征 │  │    (注册:后端调 Yolo 提特征→存库)  │
│  - GET /api/model_info     │  │  - GET  /api/vision/faces (列表)   │
│  - GET /health             │  │  - DELETE /api/vision/faces/{id}   │
└────────────────────────────┘  └───────────────────────▲──────────┘
                                                         │ SQLAlchemy
                                                  ┌──────┴───────┐
                                                  │ MySQL(云端)  │
                                                  │ users         │
                                                  │ face_library  │
                                                  └──────────────┘
```

> 链路编号说明:[1] 前端↔Yolo 直连(不鉴权);[2] 前端↔后端(JWT);[3] Yolo↔后端(服务 token)。图中 [3] 标注的两条箭头分别是 Yolo 拉人脸库与后端调 Yolo 提特征。

### 2.2 三类通信链路

| 链路 | 场景 | 协议 | 鉴权 |
|------|------|------|------|
| [1] 前端 ↔ Yolo | 实时目标检测、实时人脸识别 | HTTP REST(JSON + base64) | **不鉴权**(公网直连) |
| [2] 前端 ↔ 后端 | 获取 Yolo 地址、人脸库 CRUD | HTTP REST | JWT |
| [3] Yolo ↔ 后端 | Yolo 拉取 face_library(识别时);后端调 Yolo 提特征(注册时) | HTTP REST | 服务 token(共享密钥) |

> 实时检测/识别走链路 [1](直连,低延迟);人脸库管理与 Yolo 地址获取走链路 [2];人脸识别所需的 face_library 拉取与人脸注册时的特征提取走链路 [3]。

### 2.3 分层职责

| 层 | 组件 | 职责 |
|----|------|------|
| 表现层 | Atmos 前端 `Vision.vue` | 摄像头采集、直连 Yolo 逐帧推理、Canvas 绘制标注、人脸库管理 UI |
| 推理层 | 本地 Yolo 服务 | YOLO26 目标检测、insightface 人脸特征提取、**本地人脸比对**、图像编解码、标注图生成 |
| 业务层 | Atmos 后端 `api/vision.py` | JWT 鉴权、人脸库 CRUD、下发 Yolo 地址、供 Yolo 拉取人脸库的内部接口 |
| 数据层 | 云端 MySQL | users / face_library(实时结果不入库) |

### 2.4 部署拓扑

| 组件 | 部署位置 | 端口 | 网络 |
|------|----------|------|------|
| Atmos 前端 (Nginx) | 云端服务器 | 80 / 81 | 公网 |
| Atmos 后端 (Flask) | 云端服务器 | 5000 | 公网/内网 |
| MySQL 8.0 | 云端服务器 | 3306 | 内网 |
| EMQX | 云端服务器 | 1883 | 内网 |
| **Yolo 推理服务** | **本地机器** | **6000** | **公网 IP**(用户后续提供),前端直连 |

---

## 三、模块划分与目录结构

```
End/
├── Yolo/                          # 【新增】本地视觉推理服务(不进 docker-compose)
│   ├── app.py                     # Flask 入口 + 路由注册 + 模型加载
│   ├── config.py                  # 配置(权重/设备/阈值/端口/后端地址/服务 token)
│   ├── detector.py                # YOLO26 检测封装(ultralytics)
│   ├── recognizer.py              # 人脸特征提取 + 本地余弦比对(insightface)
│   ├── face_store.py              # 从后端拉取/缓存 face_library
│   ├── routes.py                  # 推理 API 路由
│   ├── requirements.txt           # ultralytics / insightface / flask / opencv / numpy / requests
│   └── README.md                  # 本地部署说明(公网 IP / GPU / 启动)
│
├── backend/                       # 【改动】新增视觉业务蓝图 + 模型 + 配置 + 建表
│   ├── api/vision.py              # 【新增】人脸库 CRUD + Yolo 地址下发 + 内部人脸库接口
│   ├── models/vision.py           # 【新增】FaceLibrary 模型
│   ├── models/__init__.py         # 【改动】导入 FaceLibrary
│   ├── config.py                  # 【改动】新增 YOLO_SERVICE_URL / VISION_INTERNAL_TOKEN
│   ├── app.py                     # 【改动】注册 vision 蓝图
│   ├── init_db.sql                # 【改动】追加 face_library 表
│   └── requirements.txt           # 【改动】新增 requests(若未安装)
│
└── frontend/                      # 【改动】新增视觉检测页(frontend-v2 按需同步)
    ├── src/views/Vision.vue       # 【新增】视觉检测页(直连 Yolo)
    ├── src/api/vision.js          # 【新增】视觉相关 HTTP 封装(后端部分)
    ├── src/api/yolo.js            # 【新增】Yolo 直连 HTTP 封装(独立 axios 实例)
    ├── src/router/index.js        # 【改动】新增 /vision 路由
    └── src/layouts/AppLayout.vue  # 【改动】侧边栏加入"视觉检测"菜单项
```

> 说明:项目存在 `frontend/` 与 `frontend-v2/` 两套前端,本设计以 `frontend/` 为准,`frontend-v2/` 按需同步同名文件改动。

---

## 四、Yolo 本地服务设计(End/Yolo/)

### 4.1 技术栈

| 依赖 | 用途 |
|------|------|
| Python ≥ 3.9 | 运行环境 |
| Flask | Web 框架(仅推理 API,无前端) |
| ultralytics | YOLO26 模型加载与推理 |
| insightface | 人脸检测 + 512 维特征提取(ONNX 后端) |
| opencv-python | 图像编解码、标注框绘制 |
| numpy | 数组运算、余弦相似度 |
| requests | 调用后端拉取 face_library |
| Pillow | 图像辅助 |

### 4.2 配置项(config.py,环境变量覆盖)

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| WEIGHTS | `YOLO_WEIGHTS` | `yolo26n.pt` | YOLO26 权重,可选 n/s/m/l/x |
| DEVICE | `YOLO_DEVICE` | `""` | 空=自动(cuda 优先);`cpu`=强制 CPU;`0`=GPU 0 |
| IMGSZ | `YOLO_IMGSZ` | `640` | 推理输入尺寸 |
| CONF_THRES | `YOLO_CONF_THRES` | `0.35` | 置信度阈值 |
| IOU_THRES | `YOLO_IOU_THRES` | `0.45` | NMS 阈值(切换一对多头时生效) |
| END2END | `YOLO_END2END` | `true` | 是否使用端到端头(默认 true,无需 NMS) |
| FACE_MODEL | `FACE_MODEL` | `buffalo_l` | insightface 模型包 |
| FACE_DET_SIZE | `FACE_DET_SIZE` | `640` | 人脸检测输入尺寸 |
| FACE_SIM_THRESHOLD | `FACE_SIM_THRESHOLD` | `0.5` | 人脸识别相似度阈值 |
| PORT | `YOLO_PORT` | `6000` | 监听端口 |
| BACKEND_URL | `BACKEND_URL` | (必填) | Atmos 后端地址,用于拉取 face_library |
| INTERNAL_TOKEN | `VISION_INTERNAL_TOKEN` | (必填) | Yolo↔后端内部通信共享 token |

> 说明:前端 ↔ Yolo 直连**不鉴权**;`INTERNAL_TOKEN` 仅用于 Yolo ↔ 后端的内部调用(链路 [3])。

### 4.3 API 设计

#### 4.3.1 GET /health

健康检查。**响应**:
```json
{"ok": true, "device": "cuda:0", "yolo_model": "yolo26n.pt", "face_model": "buffalo_l"}
```

#### 4.3.2 GET /api/model_info

获取 YOLO26 类别列表与人脸模型信息。**响应**:
```json
{
  "classes": [{"id": 0, "name": "person"}, {"id": 1, "name": "bicycle"}],
  "total": 80,
  "face_model": "buffalo_l",
  "embedding_dim": 512
}
```

#### 4.3.3 POST /api/detect  (前端直连)

YOLO26 目标检测,返回检测结果与标注图。

**请求**(JSON):
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| frame | string | 是 | base64 JPEG,可带 `data:image/jpeg;base64,` 前缀 |
| conf | float | 否 | 置信度阈值,默认取配置 |
| iou | float | 否 | IoU 阈值,默认取配置 |
| classes | string | 否 | 逗号分隔类别 ID,如 `"0,2,5"` |

**响应**:
```json
{
  "detections": [{"class": "person", "class_id": 0, "confidence": 0.8921, "bbox": [120, 80, 400, 500]}],
  "annotated": "data:image/jpeg;base64,/9j/4AAQ...",
  "count": 1
}
```

> `bbox` 为 `[x1, y1, x2, y2]` 像素坐标;`annotated` 为画好框的标注图 base64。

#### 4.3.4 POST /api/recognize  (前端直连,内部拉人脸库)

人脸身份识别。前端传入 `user_id`,Yolo 内部调用后端拉取该用户 `face_library`,本地余弦比对后返回姓名。

**请求**(JSON):
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| frame | string | 是 | base64 JPEG |
| user_id | int | 是 | 当前用户 ID(前端从 JWT 解出后传入) |

**响应**:
```json
{
  "faces": [
    {"bbox": [120, 80, 200, 200], "name": "张三", "similarity": 0.78, "score": 0.98}
  ],
  "count": 1
}
```

> `name` 为 `null` 表示未命中(未知);`score` 为人脸检测置信度。

**内部流程**:
```
1. Yolo 收到 {frame, user_id}
2. insightface 检测人脸 + 提 512 维 embedding
3. 调后端 GET /api/vision/internal/faces?user_id=X (Authorization: Bearer <INTERNAL_TOKEN>)
   → 拉取该用户 face_library [{name, embedding}]
4. 对每张脸:与 face_library 逐一余弦相似度 → 取最大值
   ≥ FACE_SIM_THRESHOLD → 命中(name=匹配名);否则 name=null
5. 返回 {faces:[...]}(不持久化)
```

> face_library 拉取可加内存缓存(TTL 30s),避免逐帧请求后端。

#### 4.3.5 POST /api/face/embed  (后端注册时调用)

人脸特征提取(供后端人脸注册使用,不做比对)。

**请求**(JSON):`{frame}`(base64 JPEG)
**响应**:
```json
{"faces": [{"bbox": [120, 80, 200, 200], "embedding": [0.0123, "..."], "score": 0.98}], "count": 1}
```

> 仅在链路 [3](后端注册人脸)时由 Atmos 后端调用,需 `Authorization: Bearer <INTERNAL_TOKEN>`。

### 4.4 图像处理流程

```
base64 字符串
  → 去除 data: 前缀 → base64.b64decode → 字节
  → cv2.imdecode(np.frombuffer) → BGR numpy 数组
  → [detect] YOLO26 model(frame, conf, iou, classes)
            → results.boxes → 类别/置信度/bbox
            → cv2 画框+标签 → annotated
  → [recognize] insightface app.get(frame)
            → faces[].bbox / embedding / det_score
            → 拉 face_library → 余弦比对 → name
  → [face/embed] insightface 提特征 → 返回 embedding
  → cv2.imencode(.jpg) → base64 编码 → 返回 JSON
```

### 4.5 错误处理

| 场景 | HTTP 状态 | 响应 |
|------|-----------|------|
| frame 缺失或解码失败 | 400 | `{"error": "invalid frame"}` |
| 模型未加载完成 | 503 | `{"error": "model not ready"}` |
| 拉取 face_library 失败(后端不可达) | 502 | `{"error": "backend unreachable"}` |
| 推理异常 | 500 | `{"error": "<msg>"}` |

> 前端 ↔ Yolo 的 `/api/detect`、`/api/recognize`、`/api/model_info`、`/health` 不鉴权;`/api/face/embed` 需 `INTERNAL_TOKEN`。

### 4.6 启动与运行

```bash
cd Yolo
pip install -r requirements.txt
# 首次运行自动下载 yolo26n.pt 与 insightface buffalo_l 模型
set BACKEND_URL=http://<云端服务器IP>:5000
set VISION_INTERNAL_TOKEN=<共享密钥>
set YOLO_DEVICE=0
python app.py
# 监听 http://0.0.0.0:6000
```

Windows 后台运行 / 防火墙放行 6000 端口的说明见 `Yolo/README.md`。

---

## 五、数据库设计(云端 MySQL)

> 在现有 [backend/init_db.sql](file:///d:/Code/End/backend/init_db.sql) 末尾追加 **1 张表**。实时检测/识别结果不持久化,故仅保留人脸库表。

### 5.1 表关系

```
users 1───n face_library(人脸库,每个用户注册多张人脸)
```

### 5.2 face_library 人脸库表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK, AUTO_INCREMENT | 人脸ID |
| user_id | BIGINT | FK→users.id, NOT NULL | 注册者 |
| name | VARCHAR(64) | NOT NULL | 姓名 |
| embedding | LONGBLOB | NOT NULL | insightface 512 维特征向量(二进制序列化) |
| sample_snapshot | LONGTEXT | NULL | 注册样张 base64 |
| created_at | DATETIME | NOT NULL DEFAULT CURRENT_TIMESTAMP | 注册时间 |
| INDEX | | (user_id) | 查询索引 |
| UNIQUE | | (user_id, name) | 同一用户姓名不重复 |

### 5.3 建表 SQL

```sql
-- ============================================
-- 12. face_library  人脸库表(视觉模块)
-- ============================================
CREATE TABLE IF NOT EXISTS face_library (
    id              BIGINT          NOT NULL AUTO_INCREMENT,
    user_id         BIGINT          NOT NULL,
    name            VARCHAR(64)     NOT NULL,
    embedding       LONGBLOB        NOT NULL COMMENT 'insightface 512 维特征向量(序列化)',
    sample_snapshot LONGTEXT        NULL COMMENT '注册样张 base64',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_user_name (user_id, name),
    KEY idx_user (user_id),
    CONSTRAINT fk_face_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

## 六、Atmos 后端设计(backend/api/vision.py)

### 6.1 角色变更

后端**不再代理**实时检测/识别请求(改由前端直连 Yolo)。后端职责收敛为:
1. 下发 Yolo 服务地址给前端(`/api/vision/endpoint`)。
2. 人脸库 CRUD(注册/列表/删除)。
3. 供 Yolo 拉取人脸库的内部接口(`/api/vision/internal/faces`)。

### 6.2 蓝图与鉴权

```python
bp = Blueprint("vision", __name__)
```

挂在 `/api` 前缀。人脸库管理与地址下发接口加 `@jwt_required`;内部接口用 `INTERNAL_TOKEN` 校验。蓝图注册见 [backend/app.py](file:///d:/Code/End/backend/app.py):

```python
from api import vision
app.register_blueprint(vision.bp, url_prefix="/api")
```

### 6.3 接口清单

| 方法 | 路径 | 说明 | 鉴权 | 链路 |
|------|------|------|------|------|
| GET | `/api/vision/endpoint` | 返回 Yolo 公网地址给前端 | JWT | [2] |
| GET | `/api/vision/faces` | 当前用户人脸库列表 | JWT | [2] |
| POST | `/api/vision/faces` | 注册人脸(frame+name → 调 Yolo 提特征 → 存库) | JWT | [2]+[3] |
| DELETE | `/api/vision/faces/{id}` | 删除人脸(仅本人) | JWT | [2] |
| GET | `/api/vision/internal/faces` | Yolo 拉取指定用户人脸库(返回 embedding) | INTERNAL_TOKEN | [3] |

#### 6.3.1 GET /api/vision/endpoint
```json
{"yolo_url": "http://<本地公网IP>:6000"}
```

#### 6.3.2 GET /api/vision/faces
返回当前用户人脸库列表(不含 embedding 原始向量,含样张缩略图):
```json
[{"id": 1, "name": "张三", "sample_snapshot": "...", "created_at": "2026-06-30T10:00:00"}]
```

#### 6.3.3 POST /api/vision/faces  (人脸注册/绑定)
**请求**:`{frame: <base64>, name: <姓名>}`
**流程**:
1. 校验当前用户 + 姓名不重复。
2. 调 Yolo `POST /api/face/embed`(Authorization: Bearer `<INTERNAL_TOKEN>`)提特征。
3. 取第一个 face 的 embedding,序列化存 `face_library`。
4. 返回 `{id, name, created_at}`。

#### 6.3.4 GET /api/vision/internal/faces  (Yolo 拉取)
**请求**:`?user_id=<int>`,Header `Authorization: Bearer <INTERNAL_TOKEN>`
**响应**:
```json
[{"name": "张三", "embedding": "<base64 编码的 512 维 float32 向量>"}]
```
> 内部接口,仅供 Yolo 在 `/api/recognize` 时拉取。embedding 用 base64 编码便于 HTTP 传输。

### 6.4 内部 token 校验

```python
def _check_internal_token():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token != Config.VISION_INTERNAL_TOKEN:
        return False, (jsonify({"error": "unauthorized"}), 401)
    return True, None
```

### 6.5 新增配置项(backend/config.py 追加)

```python
# ============ 视觉模块 ============
YOLO_SERVICE_URL = os.getenv("YOLO_SERVICE_URL", "http://127.0.0.1:6000")
VISION_INTERNAL_TOKEN = os.getenv("VISION_INTERNAL_TOKEN", "")  # Yolo↔后端内部共享密钥
```

### 6.6 .env.example 追加

```ini
# ====== 视觉模块 ======
YOLO_SERVICE_URL=http://127.0.0.1:6000   # 本地 Yolo 服务公网地址(用户后续提供),前端直连
VISION_INTERNAL_TOKEN=                    # Yolo↔后端内部通信共享密钥(两端一致)
```

### 6.7 模型定义(backend/models/vision.py)

`FaceLibrary` 模型,字段与第 5.2 节一致,`embedding` 用 `db.LargeBinary`,`to_dict()` 不返回 embedding 原始向量。在 [backend/models/__init__.py](file:///d:/Code/End/backend/models/__init__.py) 追加导入。

---

## 七、前端设计(Vision.vue)

### 7.1 路由

在 [frontend/src/router/index.js](file:///d:/Code/End/frontend/src/router/index.js) 的 `AppLayout` children 中追加:

```js
{ path: 'vision', name: 'vision', component: () => import('@/views/Vision.vue') }
```

登录可见,无需 admin。侧边栏 `AppLayout.vue` 菜单加入"视觉检测"项(图标:Camera)。

### 7.2 双 HTTP 实例

前端需要两个 axios 实例:
- `src/api/vision.js`:调后端(带 JWT),用于人脸库管理 + 获取 Yolo 地址。
- `src/api/yolo.js`:直连 Yolo(不带 token),用于实时检测/识别。Yolo 地址从 `/api/vision/endpoint` 动态获取。

```js
// src/api/yolo.js(动态 baseURL)
import axios from 'axios'
let yoloBase = ''
export const setYoloUrl = (url) => { yoloBase = url }
const yolo = axios.create({ baseURL: '', timeout: 15000 })
yolo.interceptors.request.use(cfg => { cfg.baseURL = yoloBase; return cfg })

export const detectFrame = (data) => yolo.post('/api/detect', data)
export const recognizeFrame = (data) => yolo.post('/api/recognize', data)
export const modelInfo = () => yolo.get('/api/model_info')
```

```js
// src/api/vision.js(调后端,带 JWT)
import req from './request'
export const getEndpoint = () => req.get('/vision/endpoint')
export const listFaces = () => req.get('/vision/faces')
export const addFace = (data) => req.post('/vision/faces', data)
export const removeFace = (id) => req.delete(`/vision/faces/${id}`)
```

### 7.3 页面布局

对齐参考文档双栏风格:

```
┌────────────────────┬─────────────────────────────────────┐
│  左栏(控制面板)    │  右栏(显示区域)                       │
│  模式切换          │   ┌─────────────────────────────┐    │
│   ○ 目标检测       │   │     摄像头实时画面 + 标注框   │    │
│   ○ 人脸识别       │   └─────────────────────────────┘    │
│  [开启摄像头]      │   FPS: 12.3                           │
│  [停止]            │   检测结果 / 识别结果                 │
│  置信度阈值        │   - person 0.89                       │
│  [人脸库管理]      │   - 张三 0.78                         │
└────────────────────┴─────────────────────────────────────┘
```

### 7.4 功能详述

#### 7.4.1 页面初始化
- 进入页面 → `GET /api/vision/endpoint`(JWT)→ 拿到 `yolo_url` → `setYoloUrl(url)`。
- `GET /api/vision/faces` 加载人脸库列表(供人脸识别模式参考)。
- 若 endpoint 返回空或 Yolo `/health` 不可达,显示"视觉服务离线"徽标。

#### 7.4.2 摄像头采集与逐帧推理(直连 Yolo)
- `navigator.mediaDevices.getUserMedia({video: true})` → `<video>` 实时播放。
- 定时器(默认 100ms)抓帧到 `<canvas>` → `canvas.toDataURL('image/jpeg', 0.8)` → base64。
- 根据模式直连 Yolo:
  - 目标检测:`POST {yolo_url}/api/detect {frame, conf}` → 绘 bbox + class + confidence。
  - 人脸识别:`POST {yolo_url}/api/recognize {frame, user_id}`(user_id 从 user store 解出)→ 绘 bbox + name(未知则"未识别")+ similarity。
- FPS:最近 30 帧耗时均值倒数。

#### 7.4.3 模式切换
- 目标检测:调 `/api/detect`。
- 人脸识别:调 `/api/recognize`(Yolo 内部拉人脸库比对)。

#### 7.4.4 人脸库管理(走后端,JWT)
- 列表:`GET /api/vision/faces`(姓名、注册时间、样张缩略图)。
- 注册:输入姓名 → 摄像头采一帧 → `POST /api/vision/faces {frame, name}`(后端调 Yolo 提特征存库)。
- 删除:`DELETE /api/vision/faces/{id}`。

#### 7.4.5 降级提示
- Yolo 不可达(直连超时):前端显示"视觉服务离线"徽标,停止逐帧请求,保留摄像头预览与人脸库管理(后端可用即可)。

### 7.5 不持久化说明
- 实时检测/识别结果仅用于画面绘制,**不调用后端写入**,无历史记录查询页。
- 仅人脸库(注册数据)存云端 MySQL。

---

## 八、配置项汇总

### 8.1 Atmos 后端新增(2 项)

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| YOLO_SERVICE_URL | `YOLO_SERVICE_URL` | `http://127.0.0.1:6000` | 本地 Yolo 公网地址(下发给前端直连) |
| VISION_INTERNAL_TOKEN | `VISION_INTERNAL_TOKEN` | `""` | Yolo↔后端内部通信共享密钥 |

### 8.2 Yolo 服务配置(12 项)

见 [第 4.2 节](#42-配置项configpy环境变量覆盖)。

### 8.3 环境变量改动
- [.env.example](file:///d:/Code/End/.env.example) 追加 8.1 节两个变量。
- Yolo 模块自带 `Yolo/config.py`,通过本地环境变量配置 8.2 节变量。
- `VISION_INTERNAL_TOKEN` 在云端(.env)与本地(Yolo config)必须一致。

---

## 九、部署方案

### 9.1 Yolo 模块(本地机器)

```bash
# 1. 同步 End/Yolo 目录到本地机器(具备 GPU + 公网 IP)
cd Yolo

# 2. 安装依赖(推荐 conda 环境)
pip install -r requirements.txt
# PyTorch 按 CUDA 版本从 https://pytorch.org 安装
# insightface 依赖 onnxruntime-gpu(或 onnxruntime)

# 3. 配置环境变量
set BACKEND_URL=http://<云端服务器IP>:5000
set VISION_INTERNAL_TOKEN=<与云端 .env 一致>
set YOLO_DEVICE=0              # GPU 0;无 GPU 用 cpu
set YOLO_WEIGHTS=yolo26n.pt    # 首次启动自动下载

# 4. 启动
python app.py
# 监听 http://0.0.0.0:6000
```

- **公网访问**:本地机器开放 6000 端口(Windows 防火墙入站规则);公网 IP 由用户后续提供,填入云端 Atmos 的 `YOLO_SERVICE_URL`(前端会通过 `/api/vision/endpoint` 拿到)。
- **不进 docker-compose**:Yolo 模块独立部署,与云端 docker-compose 解耦。
- **可选加固**:生产可在本地加 Nginx 反代 + HTTPS + IP 白名单(本设计默认不鉴权,故建议至少限制来源 IP)。

### 9.2 Atmos 端(云端服务器)

```bash
# 1. 修改 .env
YOLO_SERVICE_URL=http://<本地公网IP>:6000
VISION_INTERNAL_TOKEN=<与 Yolo 端一致>

# 2. 重建 backend + frontend(新增蓝图/路由/页面/建表)
docker compose up -d --build backend frontend frontend-v2

# 3. 数据库迁移(新增 face_library 表)
docker exec -i sh-mysql mysql -uroot -p<密码> smart_home < backend/init_db.sql
# (init_db.sql 使用 CREATE TABLE IF NOT EXISTS,可安全重跑)
```

### 9.3 启动顺序

1. 本地机器启动 Yolo 服务(`python app.py`),确认 `/health` 返回 ok,且能访问 `BACKEND_URL`。
2. 云端 Atmos 配置 `YOLO_SERVICE_URL` + `VISION_INTERNAL_TOKEN`,重建服务,执行 init_db.sql。
3. 用户登录 Atmos 前端 → `/vision` → 后端下发 Yolo 地址 → 前端直连 Yolo 开摄像头使用。

---

## 十、关键业务流程

### 10.1 实时目标检测流程(前端直连 Yolo)

```
用户在 /vision 页选"目标检测" → 点"开启摄像头"
→ 浏览器 getUserMedia 采集视频流
→ 定时器每 100ms 抓一帧 → Canvas → JPEG base64
→ 前端直连 POST {yolo_url}/api/detect {frame, conf}   (无鉴权,链路 [1])
→ Yolo YOLO26 推理 → 返回 {detections, annotated, count}
→ 前端 Canvas 绘制 bbox + class + confidence,更新 FPS
→ 不持久化(不入库)
```

### 10.2 实时人脸识别流程(前端直连 Yolo + Yolo 拉人脸库)

```
用户选"人脸识别"模式 → 开启摄像头 → 逐帧 base64 + user_id
→ 前端直连 POST {yolo_url}/api/recognize {frame, user_id}   (链路 [1])
→ Yolo insightface 提特征
→ Yolo 调后端 GET /api/vision/internal/faces?user_id=X (Authorization: Bearer <INTERNAL_TOKEN>,链路 [3])
  → 后端返回该用户 face_library [{name, embedding}]
→ Yolo 本地余弦比对 → 每张脸 best_sim ≥ 0.5 命中,否则 name=null
→ 返回 {faces:[{bbox, name, similarity, score}]}
→ 前端 Canvas 绘框 + 姓名/未知 + 相似度
→ 不持久化(不入库)
```

> face_library 拉取可在 Yolo 内存缓存(TTL 30s),避免逐帧请求后端。

### 10.3 人脸注册流程(前端 → 后端 → Yolo)

```
用户在"人脸库管理" → 输入姓名 → 点"采集注册"
→ 摄像头采一帧 → POST /api/vision/faces {frame, name}  (Authorization: Bearer <JWT>,链路 [2])
→ Atmos 后端鉴权 + 校验姓名不重复
→ 后端调 Yolo POST {yolo_url}/api/face/embed {frame}  (Authorization: Bearer <INTERNAL_TOKEN>,链路 [3])
→ Yolo insightface 提特征 → 返回 {faces:[{embedding,...}]}
→ 后端取首个 embedding 序列化 → 存 face_library(user_id, name, embedding, sample_snapshot?)
→ 返回 {id, name, created_at}
→ 前端列表刷新 + 通知 Yolo 失效人脸库缓存(下次 recognize 重新拉取)
```

### 10.4 Yolo 服务不可达降级

```
前端直连 Yolo 超时/连接失败 → 显示"视觉服务离线"徽标,停止逐帧请求
→ 摄像头预览与人脸库管理(走后端)不受影响
→ Atmos 其他模块(设备/告警/预测)完全不受影响
```

### 10.5 后端不可达降级(Yolo 侧)

```
Yolo /api/recognize 时拉 face_library 失败(后端不可达)
→ 返回 502 {error:"backend unreachable"}
→ 前端提示"人脸库加载失败",目标检测模式不受影响
```

---

## 十一、与参考文档差异 & 后续优化

### 11.1 差异总表

| # | 参考文档(YOLOv5) | 本设计(YOLO26) | 说明 |
|---|--------------------|-------------------|------|
| 1 | YOLOv5s.pt(`DetectMultiBackend`) | YOLO26n.pt(`ultralytics` 包) | 模型升级,API 更简洁,默认端到端无需 NMS |
| 2 | 仅目标检测 | 目标检测 + 人脸身份识别 | 新增 insightface 人脸特征提取 + 本地比对 |
| 3 | 摄像头 / 视频 / 图片 三种输入 | 仅浏览器摄像头 | 简化,聚焦实时场景 |
| 4 | 连续帧告警(15 帧 + 红色脉冲) | **删除告警模块** | 简化实现 |
| 5 | 前端 → Flask 后端 → 模型 | 前端 → Yolo 直连;Yolo ↔ 后端(仅人脸库/注册) | 实时链路最短 |
| 6 | 无鉴权 | 前端↔Yolo 不鉴权;前端↔后端 JWT;Yolo↔后端 服务 token | 分层鉴权 |
| 7 | 不持久化 | 仅人脸库存云端 MySQL;实时结果不持久化 | 人脸库可管理 |
| 8 | 单机部署 | 云端 + 本地分离部署 | 适配服务器性能不足 |

### 11.2 后续优化方向

- **face_library 增量同步**:Yolo 启动时全量拉取 + 后续注册时后端主动推送失效,避免 TTL 内识别不到新人脸。
- **Yolo 加固**:不鉴权存在被滥用风险,后续可加 IP 白名单 / Nginx HTTPS / 限流。
- **HTTPS/WSS**:Yolo 服务加 Nginx + HTTPS;前端逐帧改 WebSocket 推流降低 HTTP 开销。
- **检测帧率自适应**:根据 Yolo 响应耗时动态调整抓帧间隔,避免请求堆积。
- **可选持久化**:若需检测/识别历史,可前端异步上报后端入库(本次不做)。
- **与 Atmos 告警联动**(可选):未来可将"检测到 person"作为 Atmos 告警引擎输入源(本次不做)。

---

## 附录:假设与决策

| # | 假设/决策 | 依据 |
|---|-----------|------|
| A1 | "删除告警模块"= 移除参考文档的连续帧告警,**不**改动 Atmos 已有告警系统 | 任务上下文为 Yolo 模块设计 + "简化实现" |
| A2 | Yolo 默认权重 `yolo26n.pt`(最快),可配置升级 | 本地部署追求速度,YOLO26 文档 n 尺度最快 |
| A3 | 前端 ↔ Yolo 直连,不鉴权 | 用户选择(实时低延迟) |
| A4 | 人脸识别时 Yolo 拉取 face_library 本地比对 | 用户选择(Yolo 拉人脸库 + 本地比对) |
| A5 | 实时检测/识别结果不持久化,仅人脸库存云端 | 用户选择(实时结果不持久化) |
| A6 | Yolo ↔ 后端内部通信用共享 `INTERNAL_TOKEN` | 防止内部接口被第三方调用 |
| A7 | 前端从后端 `/api/vision/endpoint` 动态获取 Yolo 地址 | Yolo 地址变更不用重新构建前端 |
| A8 | 人脸注册由后端编排(后端调 Yolo 提特征) | "用户绑定人脸"属 Yolo↔后端通信场景 |
| A9 | frontend 与 frontend-v2 按需同步 | 项目存在两套前端 |
