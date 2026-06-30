# Yolo 视觉推理服务

本地部署的视觉推理服务(YOLO26 目标检测 + insightface 人脸识别),与 Atmos 云端后端分离部署。详见 [Yolo视觉模块设计文档.md](../Yolo视觉模块设计文档.md)。

## 环境要求

- Python ≥ 3.9(推荐 3.10 / 3.11)
- GPU 强烈推荐(NVIDIA + CUDA),CPU 可运行但帧率低
- 公网 IP(前端浏览器直连本服务,需放行端口)

## 安装

```bash
cd Yolo

# 1. 创建虚拟环境(可选,推荐 conda)
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/macOS

# 2. 安装 PyTorch(按 CUDA 版本选,见 https://pytorch.org)
# 例如 CUDA 12.1:
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# 3. 安装其余依赖
pip install -r requirements.txt
```

> 首次启动会自动下载 `yolo26n.pt` 与 `buffalo_l` 人脸模型,需要联网。

## 配置

直接编辑 `config.py` 填写(不使用环境变量)。必填项(标 ★):

```python
BACKEND_URL = "http://101.132.119.124:5000"  # ★ 改为云端 Atmos 后端地址
INTERNAL_TOKEN = "my-secret-token"            # ★ 与云端 .env 的 VISION_INTERNAL_TOKEN 一致
```

可选项(保持默认即可,需要时再改):

| 配置项 | 默认 | 说明 |
|------|------|------|
| `WEIGHTS` | `yolo26n.pt` | 可选 n/s/m/l/x |
| `DEVICE` | `""` | 空=自动检测(独显GPU/集显CPU);`0`=GPU0;`cpu`=强制CPU |
| `IMGSZ` | `640` | 推理输入尺寸 |
| `CONF_THRES` | `0.35` | 置信度阈值 |
| `IOU_THRES` | `0.45` | NMS 阈值 |
| `FACE_MODEL` | `buffalo_l` | insightface 模型包 |
| `FACE_DET_SIZE` | `640` | 人脸检测输入尺寸 |
| `FACE_SIM_THRESHOLD` | `0.5` | 人脸识别相似度阈值 |
| `PORT` | `6000` | 监听端口 |

### 两台设备适配(集显 / 独显)

`DEVICE = ""`(留空)时,服务启动会自动检测 CUDA:

- **独显机器**(有 NVIDIA GPU):自动用 GPU(`cuda:0`)
- **集显机器**(无 CUDA):自动用 CPU

两台设备可共用同一份 `config.py`,无需为硬件改任何配置。仅 `BACKEND_URL`、`INTERNAL_TOKEN` 需按实际部署填写。

## 启动

编辑好 `config.py` 后,直接运行(无需设环境变量):

```bash
python app.py
```

启动后监听 `http://0.0.0.0:6000`,健康检查:`GET http://<本机IP>:6000/health`。

## 防火墙放行(Windows)

```powershell
# 以管理员身份运行 PowerShell
New-NetFirewallRule -DisplayName "Yolo Vision 6000" -Direction Inbound `
  -Protocol TCP -LocalPort 6000 -Action Allow -Profile Any
```

## 后台运行

Windows 推荐使用 `pythonw` + `nssm` 注册为服务,或简单用 PowerShell 后台任务:

```powershell
Start-Process pythonw -ArgumentList "app.py" -WorkingDirectory $PWD
```

Linux 推荐 `nohup`、`systemd` 或 `tmux`:

```bash
nohup python app.py > yolo.log 2>&1 &
```

## API 一览

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/health` | 无 | 健康检查 |
| GET | `/api/model_info` | 无 | YOLO26 类别 + 人脸模型信息 |
| POST | `/api/detect` | 无 | 目标检测(前端直连) |
| POST | `/api/recognize` | 无 | 人脸识别(前端直连,内部拉人脸库) |
| POST | `/api/face/embed` | INTERNAL_TOKEN | 人脸特征提取(后端注册时调用) |

## 故障排查

- **模型下载慢/失败**:`yolo26n.pt` 来自 Ultralytics,可手动下载放到当前目录;`buffalo_l` 模型包默认存到 `~/.insightface/models/`。
- **CUDA 不可用**:检查 PyTorch 是否匹配 CUDA 版本,`python -c "import torch; print(torch.cuda.is_available())"`;集显机器会自动用 CPU,若想强制 CPU,编辑 `config.py` 设 `DEVICE = "cpu"`。
- **拉人脸库 502**:检查 `config.py` 的 `BACKEND_URL` 是否可达,`INTERNAL_TOKEN` 是否与云端 `.env` 的 `VISION_INTERNAL_TOKEN` 一致。
- **前端无法直连**:确认本机 6000 端口对公网开放,公网 IP 已填入云端 `YOLO_SERVICE_URL`。
