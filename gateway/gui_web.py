# -*- coding: utf-8 -*-
"""WSN-Gateway GUI (pywebview) — Atmos Design System。

使用 pywebview 渲染真实 HTML/CSS，精确复用前端 Atmos 设计系统。
Python ↔ JavaScript 通过 pywebview js_api 桥接：
  - JS 调用 Python: window.pywebview.api.method_name(args)
  - Python 推送 JS: window.evaluate_js(code)

布局：左侧设置面板(360px) + 右侧大屏日志终端。
窗口：1200×900，可缩放。
"""
import os
import queue
import sys

import serial.tools.list_ports

import config
from gateway_core import GatewayCore, reset_uuid
from log_handler import log, log_queue
from state import gateway_state


def resource_path(relative_name: str) -> str:
    """获取资源文件的绝对路径（兼容 PyInstaller 打包）。

    - 开发环境: 返回脚本所在目录下的文件
    - exe 环境: 返回 sys._MEIPASS 下的文件（PyInstaller --onefile 解包目录）
    """
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_name)


class GatewayApi:
    """暴露给 JavaScript 的 Python API。

    JS 端通过 window.pywebview.api.xxx() 调用，返回值为 JSON 序列化。
    """

    def __init__(self):
        self._core = None
        self._serial_open = False
        self._serial_port_obj = None
        self._gateway_running = False
        self._window = None
        self._maximized = False
        self._http = None
        self._yolo = None
        self._ws_bridge = None
        # Yolo 子进程(Flask + waitress,监听 6001)。None 表示未启动。
        self._yolo_proc = None

    def set_window(self, window):
        """设置 webview 窗口引用（用于 evaluate_js 和 closing 事件）。"""
        self._window = window
        # ws_bridge 已实例化时同步窗口引用
        if self._ws_bridge is not None:
            try:
                self._ws_bridge.set_window(window)
            except Exception:
                pass

    # ==================== 懒加载（避免未安装依赖时崩溃） ====================

    def _get_http(self):
        """懒加载 HttpProxy 单例。"""
        if self._http is None:
            from http_proxy import HttpProxy
            self._http = HttpProxy()
        return self._http

    def _get_yolo(self):
        """懒加载 YoloService 单例。"""
        if self._yolo is None:
            from yolo_service import YoloService
            self._yolo = YoloService()
        return self._yolo

    def _get_ws_bridge(self):
        """懒加载 WsBridge 单例。"""
        if self._ws_bridge is None:
            from ws_bridge import WsBridge
            self._ws_bridge = WsBridge(window=self._window)
        return self._ws_bridge

    # ==================== 配置 ====================

    def get_config(self):
        """返回当前配置值供 JS 填充表单。"""
        return {
            "SERIAL_PORT": config.SERIAL_PORT,
            "SERIAL_BAUDRATE": str(config.SERIAL_BAUDRATE),
            "EMQX_HOST": config.EMQX_HOST,
            "EMQX_PORT": str(config.EMQX_PORT),
            "EMQX_USERNAME": config.EMQX_USERNAME,
            "EMQX_PASSWORD": config.EMQX_PASSWORD,
            # 新增字段（HTTP 代理 / Yolo 视觉）
            "BACKEND_URL": config.BACKEND_URL,
            "YOLO_DEVICE": config.YOLO_DEVICE,
            "YOLO_ENABLED": config.YOLO_ENABLED,
            "YOLO_IMGSZ": str(config.YOLO_IMGSZ),
            "YOLO_SERVICE_URL": config.YOLO_SERVICE_URL,
            "FACE_MODEL": config.FACE_MODEL,
            "FACE_SIM_THRESHOLD": str(config.FACE_SIM_THRESHOLD),
        }

    def save_config(self, data):
        """从 JS 接收配置字典并保存到 gateway.ini。

        采用「合并语义」: 仅更新 data 中实际存在的字段,
        缺失的字段保持原值不变。这样部分保存(如仅串口)不会清空 EMQX/Yolo 等其他配置。
        """
        try:
            # 串口配置
            if "SERIAL_PORT" in data:
                config.set_config_value("SERIAL_PORT", data.get("SERIAL_PORT", ""))
            if "SERIAL_BAUDRATE" in data:
                config.set_config_value("SERIAL_BAUDRATE", int(data.get("SERIAL_BAUDRATE", 38400)))
            # EMQX 配置
            if "EMQX_HOST" in data:
                config.set_config_value("EMQX_HOST", data.get("EMQX_HOST", ""))
            if "EMQX_PORT" in data:
                config.set_config_value("EMQX_PORT", int(data.get("EMQX_PORT", 1883)))
            if "EMQX_USERNAME" in data:
                config.set_config_value("EMQX_USERNAME", data.get("EMQX_USERNAME", ""))
            if "EMQX_PASSWORD" in data:
                config.set_config_value("EMQX_PASSWORD", data.get("EMQX_PASSWORD", ""))
            # 后端地址（兼容前端 SetupCard 的驼峰命名）
            if "BACKEND_URL" in data or "backendUrl" in data:
                config.set_config_value(
                    "BACKEND_URL",
                    data.get("BACKEND_URL") or data.get("backendUrl", ""),
                )
            # Yolo 配置（兼容驼峰命名）
            if "YOLO_DEVICE" in data or "yoloDevice" in data:
                config.set_config_value(
                    "YOLO_DEVICE",
                    data.get("YOLO_DEVICE") or data.get("yoloDevice", ""),
                )
            if "YOLO_ENABLED" in data or "yoloEnabled" in data:
                config.set_config_value(
                    "YOLO_ENABLED",
                    data.get("YOLO_ENABLED") if "YOLO_ENABLED" in data else data.get("yoloEnabled", True),
                )
            if "YOLO_IMGSZ" in data or "yoloImgsz" in data:
                config.set_config_value(
                    "YOLO_IMGSZ",
                    int(data.get("YOLO_IMGSZ") or data.get("yoloImgsz", 480)),
                )
            if "YOLO_SERVICE_URL" in data or "yoloServiceUrl" in data:
                config.set_config_value(
                    "YOLO_SERVICE_URL",
                    data.get("YOLO_SERVICE_URL") or data.get("yoloServiceUrl", "http://127.0.0.1:6001"),
                )
            if "FACE_MODEL" in data or "faceModel" in data:
                config.set_config_value(
                    "FACE_MODEL",
                    data.get("FACE_MODEL") or data.get("faceModel", "buffalo_m"),
                )
            if "FACE_SIM_THRESHOLD" in data or "faceSimThreshold" in data:
                config.set_config_value(
                    "FACE_SIM_THRESHOLD",
                    float(data.get("FACE_SIM_THRESHOLD") or data.get("faceSimThreshold", 0.5)),
                )
            config._get_config().save_to_file()
            log("[GUI] 配置已保存到 gateway.ini", "SUCCESS")
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ==================== 串口 ====================

    def get_serial_ports(self):
        """扫描系统串口，返回设备名列表。"""
        detected = [p.device for p in serial.tools.list_ports.comports()]
        if detected:
            log(f"[GUI] 检测到 {len(detected)} 个串口: {', '.join(detected)}")
        else:
            log("[GUI] 未检测到可用串口", "WARN")
        return detected

    def _open_serial_internal(self, port, baudrate):
        """内部方法:打开串口并保存引用。仅在 start_gateway 内部调用。

        串口生命周期完全绑定到网关:启动网关=打开串口,停止网关=关闭串口。
        避免双端串口管理冲突(PortNotOpenError)。
        """
        if not port or port.startswith("(未检测到"):
            return {"success": False, "message": "未检测到可用串口,请连接设备后刷新列表"}

        # 防御性关闭已持有的串口(理论上 start_gateway 前应为 None)
        if self._serial_port_obj is not None:
            try:
                self._serial_port_obj.close()
            except Exception:
                pass
            self._serial_port_obj = None
            self._serial_open = False

        try:
            import serial as pyserial

            sp = pyserial.Serial(port, baudrate, timeout=1)
            self._serial_open = True
            self._serial_port_obj = sp
            log(f"[GUI] 串口 {port}@{baudrate} 已打开", "SUCCESS")
            return {"success": True}
        except Exception as e:
            detail = str(e)
            if "FileNotFoundError" in detail or "could not open" in detail:
                return {
                    "success": False,
                    "message": f"无法打开串口 {port}。\n端口不存在或已被其他程序占用。",
                }
            return {"success": False, "message": f"串口打开失败: {detail}"}

    def _close_serial_internal(self):
        """内部方法:关闭 GUI 持有的串口。仅在 stop_gateway 内部调用。"""
        if self._serial_port_obj is not None:
            try:
                self._serial_port_obj.close()
            except Exception:
                pass
            self._serial_port_obj = None
            self._serial_open = False
            log("[GUI] 串口已关闭", "INFO")

    # ==================== 网关启停（与串口同步） ====================

    def start_gateway(self):
        """启动网关核心。串口生命周期与网关绑定:启动网关=打开串口。

        前置条件:已配置 SERIAL_PORT 和 EMQX_HOST。
        执行顺序:
          1. 校验配置
          2. 打开串口(_open_serial_internal)
          3. 创建 GatewayCore 并传入已打开的串口(_owns_serial=False)
          4. 启动网关(连接 MQTT + 发布注册 + 等待审批)
        审批通过后,SerialReader 自动 start() 并开始读取数据。
        """
        host = config.EMQX_HOST
        if not host:
            return {"success": False, "message": "请输入 MQTT Broker 地址"}

        port = config.SERIAL_PORT
        baudrate = config.SERIAL_BAUDRATE
        if not port:
            return {"success": False, "message": "请先选择串口端口"}

        # 1. 打开串口
        result = self._open_serial_internal(port, baudrate)
        if not result["success"]:
            return result

        # 2. 创建并启动 GatewayCore,复用 GUI 打开的串口
        sp = self._serial_port_obj
        self._core = GatewayCore(serial_port=sp)
        self._core.start()
        self._gateway_running = True
        log("[GUI] 网关已启动(串口已同步打开)", "SUCCESS")
        return {"success": True, "uuid": self._core.gw_uuid}

    def stop_gateway(self):
        """停止网关核心。串口生命周期与网关绑定:停止网关=关闭串口。

        执行顺序:
          1. 停止 GatewayCore(stop() 会停止 reader/mqtt/heartbeat,
             _owns_serial=False 时 stop() 不关闭串口,由本方法显式关闭)
          2. 关闭串口(_close_serial_internal)
          3. 清理状态
        注意:不清除 gateway_state.approved,审批状态由后端控制,
        网关启停不应影响审批状态,重启后直接恢复业务转发。
        """
        if self._core:
            self._core.stop()
            self._core = None
        self._gateway_running = False
        # 关闭串口(与 start_gateway 对称)
        self._close_serial_internal()
        log("[GUI] 网关已停止(串口已同步关闭)", "INFO")
        return {"success": True}

    # ==================== 状态轮询 ====================

    def get_status(self):
        """返回网关当前运行状态（供 JS 定时轮询）。"""
        # EMQX 连接状态:通过 core._mqtt 的 is_connected() 判断
        emqx_connected = False
        emqx_host = ""
        emqx_port = 1883
        if self._core and hasattr(self._core, "_mqtt"):
            try:
                mqtt_inst = self._core._mqtt
                if hasattr(mqtt_inst, "is_connected"):
                    emqx_connected = mqtt_inst.is_connected()
                elif hasattr(mqtt_inst, "_client") and mqtt_inst._client is not None:
                    c = mqtt_inst._client
                    if hasattr(c, "is_connected"):
                        emqx_connected = c.is_connected()
            except Exception:
                pass
        emqx_host = config.EMQX_HOST
        emqx_port = config.EMQX_PORT

        return {
            "running": self._gateway_running,
            "gateway_running": self._gateway_running,  # Gateway.vue 兼容字段
            "approved": gateway_state.approved if self._core else False,
            "device_count": (
                self._core._mac_registry.count()
                if self._core and self._core._mac_registry
                else 0
            ),
            "uuid": self._core.gw_uuid if self._core else "",
            "serial_open": self._serial_open,
            "serial_port": config.SERIAL_PORT,
            "serial_baudrate": config.SERIAL_BAUDRATE,
            "emqx_connected": emqx_connected,
            "emqx_host": emqx_host,
            "emqx_port": emqx_port,
        }

    def poll_logs(self):
        """排空日志队列，返回日志条目列表供 JS 渲染。"""
        logs = []
        while True:
            try:
                logs.append(log_queue.get_nowait())
            except queue.Empty:
                break
        return logs

    # ==================== Gateway.vue 桥接适配方法 ====================

    def get_gateway_status(self):
        """Gateway.vue 兼容：返回网关状态（丰富字段版 get_status）。"""
        return self.get_status()

    def list_serial_ports(self):
        """Gateway.vue 兼容：返回 {ports: [...]} 格式的串口列表。"""
        ports = self.get_serial_ports()
        return {"ports": ports}

    def get_gateway_logs(self):
        """Gateway.vue 兼容：返回 {logs: [...]} 格式的日志列表。"""
        return {"logs": self.poll_logs()}

    def reset_gateway_uuid(self):
        """Gateway.vue 兼容：强制重置网关 UUID 并返回新值。
        用于解决编译后旧 UUID 导致审批异常的问题。"""
        new_uuid = reset_uuid()
        # 如果网关已启动，需要重启核心以使用新 UUID
        was_running = self._gateway_running
        if was_running:
            self.stop_gateway()
        self._core = GatewayCore()
        if was_running:
            self.start_gateway()
        return {"success": True, "uuid": new_uuid,
                "message": "UUID 已重置为 " + new_uuid[:8] + "…，网关将重新注册"}

    def save_serial_config(self, data):
        """Gateway.vue 兼容：仅保存串口配置（部分更新）。"""
        try:
            if not isinstance(data, dict):
                return {"success": False, "message": "参数格式错误"}
            port = data.get("port", "")
            baudrate = data.get("baudrate", 38400)
            if port:
                config.set_config_value("SERIAL_PORT", str(port))
            config.set_config_value("SERIAL_BAUDRATE", int(baudrate))
            config._get_config().save_to_file()
            log(f"[GUI] 串口配置已保存: {port}@{baudrate}", "SUCCESS")
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def save_emqx_config(self, data):
        """Gateway.vue 兼容：仅保存 EMQX 配置（部分更新）。"""
        try:
            if not isinstance(data, dict):
                return {"success": False, "message": "参数格式错误"}
            if "host" in data:
                config.set_config_value("EMQX_HOST", str(data.get("host", "")))
            if "port" in data:
                config.set_config_value("EMQX_PORT", int(data.get("port", 1883)))
            if "username" in data:
                config.set_config_value("EMQX_USERNAME", str(data.get("username", "")))
            if "password" in data and data.get("password", ""):
                config.set_config_value("EMQX_PASSWORD", str(data.get("password", "")))
            config._get_config().save_to_file()
            log(f"[GUI] EMQX 配置已保存: {config.EMQX_HOST}:{config.EMQX_PORT}", "SUCCESS")
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ==================== HTTP 代理（转发到云端后端） ====================

    def http_get(self, path, params=None):
        """转发 GET 请求到云端后端。path 为含 /api 前缀的完整路径。"""
        try:
            return self._get_http().get(path, params)
        except Exception as e:
            return {"status": 0, "data": {"error": str(e)}}

    def http_post(self, path, body=None):
        """转发 POST 请求到云端后端。PUT 也走此通道。"""
        try:
            return self._get_http().post(path, body)
        except Exception as e:
            return {"status": 0, "data": {"error": str(e)}}

    def http_delete(self, path, body=None):
        """转发 DELETE 请求到云端后端。"""
        try:
            return self._get_http().delete(path, body)
        except Exception as e:
            return {"status": 0, "data": {"error": str(e)}}

    def http_patch(self, path, body=None):
        """转发 PATCH 请求到云端后端（如设备命名/绑定）。"""
        try:
            return self._get_http().patch(path, body)
        except Exception as e:
            return {"status": 0, "data": {"error": str(e)}}

    def set_jwt(self, token):
        """持久化 JWT token（登录成功后调用）。"""
        try:
            self._get_http().set_token(token)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def logout(self):
        """清除 JWT token（退出登录时调用）。"""
        try:
            self._get_http().clear_token()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def test_backend_connection(self, url=None):
        """测试后端连通性，返回 {reachable, latency_ms, status_code, error}。"""
        try:
            return self._get_http().test_connection(url)
        except Exception as e:
            return {
                "reachable": False,
                "latency_ms": 0,
                "status_code": 0,
                "error": str(e),
            }

    # ==================== Yolo 视觉 ====================

    @staticmethod
    def _decode_frame(frame_b64):
        """base64 JPEG/PNG → BGR numpy 数组。

        兼容 data URI 前缀（data:image/jpeg;base64,xxxx）。
        """
        import base64
        import numpy as np
        import cv2
        if not frame_b64:
            raise ValueError("frame_b64 为空")
        # 移除 data URI 前缀
        if "," in frame_b64 and frame_b64.startswith("data:"):
            frame_b64 = frame_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(frame_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("base64 解码失败:图像格式无法识别")
        return frame

    @staticmethod
    def _parse_classes(classes_str):
        """解析类别字符串为列表。如 "0,2,5" → [0, 2, 5]。"""
        if not classes_str:
            return None
        try:
            return [int(c.strip()) for c in str(classes_str).split(",") if c.strip()]
        except ValueError:
            return None

    def _get_yolo_session(self):
        """获取/创建 Yolo HTTP Session（复用 TCP 连接，避免逐帧握手开销）。"""
        if not hasattr(self, "_yolo_http_session") or self._yolo_http_session is None:
            import requests as _req
            import urllib3 as _u3
            _u3.disable_warnings()
            self._yolo_http_session = _req.Session()
            # 适配器配置:连接池大小=4, keep-alive 复用
            from requests.adapters import HTTPAdapter
            self._yolo_http_session.mount("http://", HTTPAdapter(pool_connections=2, pool_maxsize=4))
        return self._yolo_http_session

    def yolo_http_get(self, path, params=None):
        """HTTP GET 代理到 Yolo 服务(config.YOLO_SERVICE_URL)，避免 file:// CORS 限制。"""
        import requests as _req
        base = config.YOLO_SERVICE_URL or "http://127.0.0.1:6001"
        if not path.startswith("/"):
            path = "/" + path
        url = base.rstrip("/") + path
        try:
            resp = self._get_yolo_session().get(url, params=params, timeout=15, verify=False)
            try:
                data = resp.json()
            except ValueError:
                data = resp.text
            return {"status": resp.status_code, "data": data}
        except _req.RequestException as e:
            return {"status": 0, "data": {"error": str(e)}}

    def yolo_http_post(self, path, body=None):
        """HTTP POST 代理到 Yolo 服务(config.YOLO_SERVICE_URL)，避免 file:// CORS 限制。"""
        import requests as _req
        base = config.YOLO_SERVICE_URL or "http://127.0.0.1:6001"
        if not path.startswith("/"):
            path = "/" + path
        url = base.rstrip("/") + path
        timeout = 30 if "recognize" in path or "face" in path else 15
        try:
            if not isinstance(body, dict):
                log(f"[Yolo-Proxy] POST {url} | unexpected body type={type(body).__name__}", "WARN")
                body = {}
            resp = self._get_yolo_session().post(url, json=body, timeout=timeout, verify=False)
            try:
                data = resp.json()
            except ValueError:
                data = resp.text
            if resp.status_code >= 400:
                log(f"[Yolo-Proxy] ERROR {resp.status_code}: {str(data)[:300]}", "ERROR")
            return {"status": resp.status_code, "data": data}
        except _req.RequestException as e:
            log(f"[Yolo-Proxy] RequestException: {e}", "ERROR")
            return {"status": 0, "data": {"error": str(e)}}
        except Exception as e:
            log(f"[Yolo-Proxy] Unexpected error: {e}", "ERROR")
            return {"status": 0, "data": {"error": str(e)}}

    def vision_detect(self, frame_b64, options=None):
        """目标检测。options: {conf, iou, classes}。"""
        try:
            frame = self._decode_frame(frame_b64)
            opts = options or {}
            conf = opts.get("conf")
            iou = opts.get("iou")
            classes = self._parse_classes(opts.get("classes"))
            return self._get_yolo().detect(frame, conf=conf, iou=iou, classes=classes)
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def vision_recognize(self, frame_b64, user_id):
        """人脸识别：本地比对拉取的人脸库。"""
        try:
            frame = self._decode_frame(frame_b64)
            return self._get_yolo().recognize(frame, int(user_id))
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def vision_face_embed(self, frame_b64):
        """人脸特征提取，返回 base64 编码的 float32 embedding。"""
        try:
            frame = self._decode_frame(frame_b64)
            return self._get_yolo().extract_embedding(frame)
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def vision_invalidate_faces(self, user_id=None):
        """失效人脸库缓存（用户人脸更新后调用）。"""
        try:
            return self._get_yolo().invalidate_face_cache(
                int(user_id) if user_id is not None else None
            )
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def yolo_status(self):
        """返回 Yolo 模块状态（不触发初始化）。"""
        try:
            return self._get_yolo().status()
        except Exception as e:
            return {
                "ready": False,
                "enabled": False,
                "error": str(e),
            }

    def yolo_switch_device(self, device):
        """切换 Yolo 推理设备（""=自动, "cpu", "0"=GPU0）。"""
        try:
            return self._get_yolo().switch_device(device)
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def yolo_check_gpu_available(self):
        """检查 GPU 是否可用（不加载模型）。"""
        try:
            return self._get_yolo().check_gpu_available()
        except Exception as e:
            return {
                "gpu_available": False,
                "device_count": 0,
                "devices": [],
                "error": str(e),
            }

    # ==================== 模型下载管理 ====================

    def download_model(self, model_name):
        """异步下载模型，进度通过 evaluate_js 推送到前端。

        前端需注册 window.__modelDownloadProgress(modelName, downloaded, total, percent) 回调。
        百分比约定:
          percent == -1: 下载已开始(总大小未知)
          percent == -2: 下载失败(前端应显示错误并退出"下载中"状态)
          0 <= percent <= 100: 正常进度

        返回 {"ok": True, "message": "下载已开始"} 立即给前端,
        实际下载结果通过进度回调异步推送。
        """
        import threading
        from model_manager import download_model as _download, get_models_dir

        # 提前确认模型目录可用,便于排查"路径为空"问题
        try:
            target_dir = get_models_dir()
            log(f"[GUI] 模型下载目标目录: {target_dir}", "INFO")
        except Exception as e:
            log(f"[GUI] 获取模型目录失败: {e}", "ERROR")

        # 推送一次"开始下载"事件(percent=-1),让前端立即显示下载中状态
        if self._window is not None:
            try:
                self._window.evaluate_js(
                    f"window.__modelDownloadProgress && "
                    f"window.__modelDownloadProgress({model_name!r}, 0, -1, -1)"
                )
            except Exception:
                pass

        def on_progress(downloaded, total, percent):
            if self._window is None:
                return
            try:
                js = (
                    f"window.__modelDownloadProgress && "
                    f"window.__modelDownloadProgress({model_name!r}, "
                    f"{downloaded}, {total}, {percent})"
                )
                self._window.evaluate_js(js)
            except Exception:
                pass

        def _download_thread():
            try:
                result = _download(model_name, on_progress=on_progress)
                if result.get("ok"):
                    log(f"[GUI] 模型 {model_name} 下载成功: {result.get('path')}", "SUCCESS")
                else:
                    log(f"[GUI] 模型 {model_name} 下载失败: {result.get('error')}", "ERROR")
                    # 推送错误事件(percent=-2),让前端退出"下载中"状态
                    if self._window is not None:
                        try:
                            self._window.evaluate_js(
                                f"window.__modelDownloadProgress && "
                                f"window.__modelDownloadProgress({model_name!r}, -1, -1, -2)"
                            )
                        except Exception:
                            pass
            except Exception as e:
                log(f"[GUI] 模型 {model_name} 下载异常: {e}", "ERROR")
                if self._window is not None:
                    try:
                        self._window.evaluate_js(
                            f"window.__modelDownloadProgress && "
                            f"window.__modelDownloadProgress({model_name!r}, -1, -1, -2)"
                        )
                    except Exception:
                        pass

        # 异步执行,不阻塞 pywebview UI 线程(否则页面冻结、进度回调无法触发)
        threading.Thread(target=_download_thread, daemon=True, name="model-download").start()
        return {"ok": True, "message": "下载已开始"}

    def list_models(self):
        """列出所有已知模型的安装状态。"""
        try:
            from model_manager import list_models as _list
            return _list()
        except Exception as e:
            return []

    def is_model_installed(self, model_name):
        """检查模型是否已安装。"""
        try:
            from model_manager import is_model_installed as _check
            return _check(model_name)
        except Exception:
            return False

    # ==================== Yolo 设置 / Python 依赖安装 ====================

    def get_yolo_settings(self):
        """返回 Yolo 服务设置:服务地址、GPU 状态、模型安装状态、Python 依赖状态。"""
        try:
            gpu_info = self.yolo_check_gpu_available()
        except Exception as e:
            gpu_info = {"gpu_available": False, "device_count": 0, "devices": [], "error": str(e)}

        # 检查 Python 依赖是否已安装
        # 使用 importlib.util.find_spec 代替 import,避免 torch/ultralytics
        # 等大型包加载 DLL 超时(import torch 首次需 5-15s,find_spec 近乎瞬时)
        deps = {}
        import subprocess as _sp
        import shutil as _sh

        py_exe = os.path.join(config.PYTHON_RUNTIME_DIR, "python.exe")
        if not os.path.isfile(py_exe):
            py_exe = _sh.which("python") or _sh.which("python3") or _sh.which("py")

        _pkg_list = [
            ("torch", "torch"),
            ("insightface", "insightface"),
            ("onnxruntime", "onnxruntime"),
            ("ultralytics", "ultralytics"),
            ("cv2", "cv2"),
        ]

        # 预填充默认值：无 Python 时全部视为未安装
        for pkg, _name in _pkg_list:
            deps[pkg] = False

        if py_exe:
            # 使用 find_spec 一次性批量检测,比 import 快 10-50 倍且不会超时
            check_script = (
                "import importlib.util as _u; "
                + "; ".join(
                    f"print('{pkg}:' + str(_u.find_spec('{name}') is not None))"
                    for pkg, name in _pkg_list
                )
            )
            try:
                r = _sp.run(
                    [py_exe, "-c", check_script],
                    capture_output=True, timeout=15, text=True,
                    creationflags=0x08000000,
                )
                if r.returncode == 0:
                    for line in (r.stdout or "").strip().splitlines():
                        if ":" in line:
                            key, val = line.split(":", 1)
                            if key in deps:
                                deps[key] = val.strip().lower() == "true"
            except Exception:
                pass

        # 模型安装状态
        try:
            from model_manager import list_models as _list
            models = _list()
        except Exception:
            models = []

        return {
            "yolo_service_url": config.YOLO_SERVICE_URL,
            "yolo_enabled": config.YOLO_ENABLED,
            "yolo_device": config.YOLO_DEVICE,
            "yolo_imgsz": config.YOLO_IMGSZ,
            "face_model": config.FACE_MODEL,
            "models_dir": config.MODELS_DIR,
            "data_dir": config.DATA_DIR,
            "gpu": gpu_info,
            "dependencies": deps,
            "models": models,
        }

    def save_yolo_settings(self, data):
        """保存 Yolo 服务设置(仅更新传入的字段)。"""
        try:
            if "yolo_service_url" in data or "YOLO_SERVICE_URL" in data:
                url = data.get("yolo_service_url") or data.get("YOLO_SERVICE_URL", "")
                config.set_config_value("YOLO_SERVICE_URL", url or "http://127.0.0.1:6001")
            if "yolo_device" in data or "YOLO_DEVICE" in data:
                config.set_config_value("YOLO_DEVICE", data.get("yolo_device") or data.get("YOLO_DEVICE", ""))
            if "yolo_enabled" in data or "YOLO_ENABLED" in data:
                val = data.get("yolo_enabled") if "yolo_enabled" in data else data.get("YOLO_ENABLED", True)
                config.set_config_value("YOLO_ENABLED", bool(val))
            if "yolo_imgsz" in data or "YOLO_IMGSZ" in data:
                config.set_config_value("YOLO_IMGSZ", int(data.get("yolo_imgsz") or data.get("YOLO_IMGSZ", 480)))
            config._get_config().save_to_file()
            log("[GUI] Yolo 设置已保存", "SUCCESS")
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def install_python_package(self, package, extra_index_url=None):
        """通过 pip 安装 Python 依赖包,进度通过 evaluate_js 推送到前端。

        :param package: 包名,如 "insightface" / "onnxruntime-gpu" / "torch"
        :param extra_index_url: 额外的 pip 索引 URL(如 CUDA 版 torch)
        前端需注册 window.__pipInstallProgress(line) 回调接收子进程输出。
        """
        import subprocess

        def on_line(line):
            if self._window is None:
                return
            try:
                safe = line.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
                js = f"window.__pipInstallProgress && window.__pipInstallProgress({package!r}, {safe!r})"
                self._window.evaluate_js(js)
            except Exception:
                pass

        try:
            # 优先使用内嵌 Python 的 pip
            py_exe = os.path.join(config.PYTHON_RUNTIME_DIR, "python.exe")
            if not os.path.isfile(py_exe):
                # 内嵌 Python 不存在,触发安装
                self.ensure_python_runtime()
                on_line("[ERROR] 内嵌 Python 运行时未安装,正在后台安装中,请等待完成后再试\n")
                return {"ok": False, "package": package, "message": "内嵌 Python 运行时正在安装中,请等待完成后再试"}

            def _run_pip():
                """执行 pip install,返回退出码。"""
                cmd = [py_exe, "-m", "pip", "install", "--no-input"] + package.split()
                cmd += ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
                        "--trusted-host", "pypi.tuna.tsinghua.edu.cn"]
                if extra_index_url:
                    cmd += ["--extra-index-url", extra_index_url]
                on_line(f"$ {' '.join(cmd)}\n")
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=0x08000000,
                )
                for line in proc.stdout:
                    on_line(line)
                proc.wait()
                return proc.returncode

            on_line(f"=== 安装 {package} ===\n")
            code = _run_pip()
            if code == 0:
                log(f"[GUI] 依赖安装成功: {package}", "SUCCESS")
                return {"ok": True, "package": package}

            msg = f"pip install 退出码 {code}"
            log(f"[GUI] 依赖安装失败: {package} ({msg})", "ERROR")
            return {"ok": False, "package": package, "error": msg}
        except Exception as e:
            log(f"[GUI] 依赖安装异常: {package} - {e}", "ERROR")
            return {"ok": False, "package": package, "error": str(e)}

    def install_gpu_lib(self):
        """安装 GPU 库(torch + CUDA + torchvision + torchaudio + ultralytics + opencv + numpy)。

        使用 PyTorch 官方 CUDA 12.1 索引安装 torch 全家桶,
        然后安装 ultralytics + opencv-python-headless + numpy 等 Yolo 运行时依赖。
        """
        # 1. torch + torchvision + torchaudio (CUDA 12.1)
        r1 = self.install_python_package(
            "torch torchvision torchaudio",
            extra_index_url="https://download.pytorch.org/whl/cu121",
        )
        if not r1.get("ok"):
            return r1
        # 2. ultralytics + opencv-python-headless + numpy
        r2 = self.install_python_package("ultralytics opencv-python-headless numpy")
        return r2

    def install_insightface_lib(self):
        """安装 insightface 库(onnxruntime-gpu + insightface)。
        注意: onnxruntime-gpu 锁定 1.20.1(CUDA 12), 1.21+ 需要 CUDA 13 与 torch cu121 不兼容。
        """
        r1 = self.install_python_package("onnxruntime-gpu==1.20.1")
        if not r1.get("ok"):
            return r1
        return self.install_python_package("insightface")

    def install_all_dependencies(self, device_type="gpu"):
        """一键安装全部 Yolo 视觉依赖。

        :param device_type: "gpu" 或 "cpu"
          - GPU 模式: torch+torchvision+torchaudio (CUDA 12.1) + ultralytics + insightface
                      + onnxruntime-gpu + opencv-python-headless + numpy
          - CPU 模式: torch+torchvision+torchaudio + ultralytics + insightface
                      + onnxruntime + opencv-python-headless + numpy
        """
        is_gpu = str(device_type).lower() in ("gpu", "cuda", "0")
        # 1. torch + torchvision + torchaudio
        if is_gpu:
            r1 = self.install_python_package(
                "torch torchvision torchaudio",
                extra_index_url="https://download.pytorch.org/whl/cu121",
            )
        else:
            r1 = self.install_python_package("torch torchvision torchaudio")
        if not r1.get("ok"):
            return r1
        # 2. ultralytics + opencv-python-headless + numpy
        r2 = self.install_python_package("ultralytics opencv-python-headless numpy")
        if not r2.get("ok"):
            return r2
        # 3. onnxruntime(-gpu) + insightface (锁定 1.20.1, 1.21+ 需要 CUDA 13 与 torch cu121 不兼容)
        if is_gpu:
            r3 = self.install_python_package("onnxruntime-gpu==1.20.1 insightface")
        else:
            r3 = self.install_python_package("onnxruntime==1.20.1 insightface")
        return r3

    # ==================== Yolo 服务子进程启停（Flask + waitress） ====================

    def select_models_dir(self):
        """图形化选择模型存储目录,保存到 config.MODELS_DIR 并持久化。

        使用 webview 的 FOLDER_DIALOG 弹出原生文件夹选择窗口。
        返回 {ok: bool, path: str};用户取消时 path 为空字符串。
        """
        import webview
        try:
            window = self._window
            if window is None and getattr(webview, "windows", None):
                window = webview.windows[0]
            if window is None:
                return {"ok": False, "path": "", "message": "webview 窗口未初始化"}

            result = window.create_file_dialog(webview.FOLDER_DIALOG)
            # pywebview 返回 tuple 或 list(可能为空)
            if not result:
                return {"ok": False, "path": ""}
            selected = result[0] if isinstance(result, (list, tuple)) else result
            if not selected:
                return {"ok": False, "path": ""}

            # 持久化到 gateway.ini
            config.set_config_value("MODELS_DIR", str(selected))
            config._get_config().save_to_file()
            log(f"[GUI] 模型存储目录已设置为: {selected}", "SUCCESS")
            return {"ok": True, "path": str(selected)}
        except Exception as e:
            log(f"[GUI] 选择模型目录失败: {e}", "ERROR")
            return {"ok": False, "path": "", "message": str(e)}

    # ==================== 数据目录 / 内嵌 Python 运行时 ====================

    def select_data_dir(self):
        """图形化选择数据存储根目录,保存到 config.DATA_DIR 并持久化。

        数据根目录用于存放内嵌 Python 运行时、模型文件等用户数据。
        返回 {ok: bool, path: str};用户取消时 path 为空字符串。
        """
        import webview
        try:
            window = self._window
            if window is None and getattr(webview, "windows", None):
                window = webview.windows[0]
            if window is None:
                return {"ok": False, "path": "", "message": "webview 窗口未初始化"}

            result = window.create_file_dialog(webview.FOLDER_DIALOG)
            # pywebview 返回 tuple 或 list(可能为空)
            if not result:
                return {"ok": False, "path": ""}
            selected = result[0] if isinstance(result, (list, tuple)) else result
            if not selected:
                return {"ok": False, "path": ""}

            # 持久化到 gateway.ini
            config.set_config_value("DATA_DIR", str(selected))
            config._get_config().save_to_file()
            log(f"[GUI] 数据根目录已设置为: {selected}", "SUCCESS")
            return {"ok": True, "path": config.DATA_DIR}
        except Exception as e:
            log(f"[GUI] 选择数据目录失败: {e}", "ERROR")
            return {"ok": False, "path": "", "message": str(e)}

    def get_data_dir(self):
        """返回数据目录与内嵌 Python 运行时目录路径。"""
        return {
            "data_dir": config.DATA_DIR,
            "python_runtime_dir": config.PYTHON_RUNTIME_DIR,
            "models_dir": config.MODELS_DIR,
        }

    def get_python_runtime_status(self):
        """检查内嵌 Python 运行时是否已解压到 DATA_DIR/python_runtime/。"""
        runtime_dir = config.PYTHON_RUNTIME_DIR
        py_exe = os.path.join(runtime_dir, "python.exe")
        installed = os.path.isfile(py_exe)
        version = ""
        if installed:
            try:
                import subprocess as _sp
                r = _sp.run([py_exe, "--version"], capture_output=True, text=True, timeout=5,
                            creationflags=0x08000000)
                version = (r.stdout or r.stderr or "").strip()
            except Exception:
                version = "unknown"
        return {"installed": installed, "path": py_exe if installed else "", "version": version, "runtime_dir": runtime_dir}

    def ensure_python_runtime(self):
        """从 exe 内解压内嵌 Python 运行时到 DATA_DIR/python_runtime/。

        在后台线程执行,不阻塞 UI。进度通过 _push_runtime_progress 推送到前端。
        若 python.exe 已存在则直接返回成功。
        """
        import threading

        runtime_dir = config.PYTHON_RUNTIME_DIR
        py_exe = os.path.join(runtime_dir, "python.exe")

        # 已存在则直接返回
        if os.path.isfile(py_exe):
            return {"ok": True, "message": "Python 运行时已就绪", "path": py_exe}

        # 定位源文件
        if getattr(sys, "frozen", False):
            src_dir = os.path.join(sys._MEIPASS, "python_embed", "runtime")
        else:
            src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "python_embed", "runtime")

        if not os.path.isdir(src_dir):
            return {"ok": False, "message": f"内嵌 Python 运行时源文件不存在: {src_dir}"}

        def _extract_thread():
            try:
                self._push_runtime_progress("start", "正在解压 Python 运行时...")
                os.makedirs(runtime_dir, exist_ok=True)
                # 复制所有文件
                import shutil
                for item in os.listdir(src_dir):
                    src = os.path.join(src_dir, item)
                    dst = os.path.join(runtime_dir, item)
                    if os.path.isfile(src):
                        shutil.copy2(src, dst)
                    elif os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                self._push_runtime_progress("extracted", "解压完成，正在安装 pip...")

                # 安装 pip
                get_pip = os.path.join(runtime_dir, "get-pip.py")
                if os.path.isfile(get_pip):
                    import subprocess as _sp
                    r = _sp.run(
                        [py_exe, get_pip, "--no-warn-script-location"],
                        capture_output=True, text=True, timeout=120,
                        creationflags=0x08000000,
                    )
                    if r.returncode != 0:
                        self._push_runtime_progress("error", f"pip 安装失败: {r.stderr[:500]}")
                        return
                self._push_runtime_progress("done", "Python 运行时安装完成")
                log(f"[GUI] Python 运行时已解压到: {runtime_dir}", "SUCCESS")
            except Exception as e:
                self._push_runtime_progress("error", str(e))
                log(f"[GUI] Python 运行时解压失败: {e}", "ERROR")

        threading.Thread(target=_extract_thread, daemon=True, name="python-runtime").start()
        return {"ok": True, "message": "正在安装 Python 运行时..."}

    def _push_runtime_progress(self, status, message):
        """推送 Python 运行时安装进度到前端。"""
        if self._window is None:
            return
        try:
            safe_msg = message.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
            js = f"window.__pythonRuntimeProgress && window.__pythonRuntimeProgress('{status}', '{safe_msg}')"
            self._window.evaluate_js(js)
        except Exception:
            pass

    def _get_python_exe(self):
        """返回内嵌 Python 的 python.exe 路径;若不存在返回 None。"""
        py_exe = os.path.join(config.PYTHON_RUNTIME_DIR, "python.exe")
        return py_exe if os.path.exists(py_exe) else None

    def _ensure_yolo_base_deps(self, py_exe):
        """确保内嵌 Python 中已安装 flask + waitress (Yolo 服务最小依赖)。

        若未安装则自动执行 pip install,并通过 eval_js 推送安装日志到前端。
        返回 (ok: bool, message: str), ok=True 表示依赖已就绪可启动。
        """
        import subprocess

        # 检查 flask / waitress 是否可导入
        missing = []
        for pkg in ("flask", "waitress", "flask_cors"):
            import_name = pkg.replace("-", "_")
            try:
                r = subprocess.run(
                    [py_exe, "-c", f"import {import_name}"],
                    capture_output=True, timeout=5,
                    creationflags=0x08000000,
                )
                if r.returncode != 0:
                    missing.append(pkg)
            except Exception:
                missing.append(pkg)

        if not missing:
            print("[GUI] Yolo 基础依赖(flask/waitress/flask_cors)已就绪", flush=True)
            return True, ""

        # 有缺失,自动安装
        missing_str = " ".join(missing)
        log(f"[GUI] Yolo 基础依赖缺失: {missing_str}, 正在自动安装...", "WARN")
        self._push_yolo_log(f"[依赖检测] 缺少: {missing_str}, 正在安装...\n")

        cmd = [
            py_exe, "-m", "pip", "install", "--no-input",
            "-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
            "--trusted-host", "pypi.tuna.tsinghua.edu.cn",
        ] + missing

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
                creationflags=0x08000000,
            )
            for line in proc.stdout:
                self._push_yolo_log(f"[pip] {line}")
            proc.wait()

            if proc.returncode != 0:
                msg = f"pip install {missing_str} 失败 (exit_code={proc.returncode})"
                log(f"[GUI] {msg}", "ERROR")
                self._push_yolo_log(f"[依赖安装] {msg}\n")
                return False, msg

            # 再次验证是否可导入
            for pkg in missing:
                import_name = pkg.replace("-", "_")
                r = subprocess.run(
                    [py_exe, "-c", f"import {import_name}"],
                    capture_output=True, timeout=5,
                    creationflags=0x08000000,
                )
                if r.returncode != 0:
                    msg = f"安装后仍无法导入 {pkg}"
                    log(f"[GUI] {msg}", "ERROR")
                    return False, msg

            log(f"[GUI] Yolo 基础依赖安装完成: {missing_str}", "SUCCESS")
            self._push_yolo_log(f"[依赖安装] {missing_str} 安装完成\n")
            return True, ""
        except Exception as e:
            msg = f"pip install 异常: {e}"
            log(f"[GUI] {msg}", "ERROR")
            self._push_yolo_log(f"[依赖安装] {msg}\n")
            return False, msg

    def _generate_yolo_launcher(self):
        """生成 Yolo Flask 服务启动器脚本到 config.PYTHON_RUNTIME_DIR/_yolo_launcher.py。

        启动器在内嵌 Python 环境中运行,负责:
          - 从环境变量读取 Yolo 源码目录并加入 sys.path
          - 加载 Yolo/config.py 并从环境变量注入配置
          - 设置 WEIGHTS / INSIGHTFACE_HOME
          - 注册为 sys.modules["config"] 并启动 Flask + waitress
        返回启动器脚本路径。
        """
        launcher_path = os.path.join(config.PYTHON_RUNTIME_DIR, "_yolo_launcher.py")
        LAUNCHER_CODE = '''#!/usr/bin/env python3
"""Yolo Flask 服务启动器 - 在内嵌 Python 环境中运行。"""
import sys, os, importlib.util

# 从环境变量读取 Yolo 源码目录
yolo_dir = os.environ.get("YOLO_SOURCE_DIR", "")
if not yolo_dir or not os.path.isdir(yolo_dir):
    print(f"[Yolo-Launcher] Yolo source dir not found: {yolo_dir}", flush=True)
    sys.exit(1)
print(f"[Yolo-Launcher] Yolo dir = {yolo_dir}", flush=True)

if yolo_dir not in sys.path:
    sys.path.insert(0, yolo_dir)

# 加载 Yolo/config.py
config_path = os.path.join(yolo_dir, "config.py")
spec = importlib.util.spec_from_file_location("yolo_inner_config", config_path)
yolo_config_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(yolo_config_module)
YoloConfig = yolo_config_module.Config

# 从环境变量注入配置
def _env(name, default=""):
    v = os.environ.get(name)
    return v if v not in (None, "") else default

YoloConfig.BACKEND_URL = _env("YOLO_BACKEND_URL", YoloConfig.BACKEND_URL)
YoloConfig.INTERNAL_TOKEN = _env("YOLO_INTERNAL_TOKEN", YoloConfig.INTERNAL_TOKEN)
YoloConfig.DEVICE = _env("YOLO_DEVICE", YoloConfig.DEVICE)
try:
    YoloConfig.IMGSZ = int(_env("YOLO_IMGSZ", str(YoloConfig.IMGSZ)))
except ValueError:
    pass
YoloConfig.FACE_MODEL = _env("YOLO_FACE_MODEL", YoloConfig.FACE_MODEL)
try:
    YoloConfig.FACE_SIM_THRESHOLD = float(_env("YOLO_FACE_SIM_THRESHOLD", str(YoloConfig.FACE_SIM_THRESHOLD)))
except ValueError:
    pass
# 强制覆盖 FORCE_OPENVINO(环境变量有值时优先;默认关闭避免 Intel 核显 CISA 错误)
_force_ov = os.environ.get("YOLO_FORCE_OPENVINO", "").strip()
if _force_ov in ("0", "false", "False", "no"):
    YoloConfig.FORCE_OPENVINO = False
    print(f"[Yolo-Launcher] FORCE_OPENVINO = False (override)", flush=True)

# MODELS_DIR 设置
models_dir = os.environ.get("YOLO_MODELS_DIR", "").strip()
if models_dir:
    try:
        os.makedirs(models_dir, exist_ok=True)
    except Exception:
        pass
    YoloConfig.WEIGHTS = os.path.join(models_dir, "yolo26n.pt")
    os.environ["INSIGHTFACE_HOME"] = models_dir
    print(f"[Yolo-Launcher] MODELS_DIR = {models_dir}", flush=True)
    print(f"[Yolo-Launcher] WEIGHTS    = {YoloConfig.WEIGHTS}", flush=True)

print(f"[Yolo-Launcher] BACKEND_URL = {YoloConfig.BACKEND_URL}", flush=True)
print(f"[Yolo-Launcher] DEVICE      = {YoloConfig.DEVICE or '(auto)'}", flush=True)
print(f"[Yolo-Launcher] IMGSZ       = {YoloConfig.IMGSZ}", flush=True)
print(f"[Yolo-Launcher] FACE_MODEL  = {YoloConfig.FACE_MODEL}", flush=True)

# 注册为 sys.modules["config"]
sys.modules["config"] = yolo_config_module

# 将 torch CUDA DLL 目录加入 PATH(必须在 onnxruntime import 之前)
# 解决 onnxruntime_providers_cuda.dll Error 126 依赖缺失问题
try:
    import torch as _torch_launcher
    _tl = os.path.join(os.path.dirname(_torch_launcher.__file__), 'lib')
    if os.path.isdir(_tl):
        os.environ['PATH'] = _tl + os.pathsep + os.environ.get('PATH', '')
except ImportError:
    pass

# 启动 Flask + waitress
try:
    from app import create_app
    from waitress import serve
    app = create_app()
    host = YoloConfig.HOST
    port = YoloConfig.PORT
    print(f"[Yolo-Launcher] waitress serving on http://{host}:{port}", flush=True)
    serve(app, host=host, port=port, threads=4)
except SystemExit:
    raise
except Exception as e:
    print(f"[Yolo-Launcher] 启动失败: {e}", flush=True)
    raise
'''
        try:
            os.makedirs(os.path.dirname(launcher_path), exist_ok=True)
            with open(launcher_path, "w", encoding="utf-8") as f:
                f.write(LAUNCHER_CODE)
            log(f"[GUI] Yolo 启动器已生成: {launcher_path}", "INFO")
        except Exception as e:
            log(f"[GUI] 生成 Yolo 启动器失败: {e}", "ERROR")
        return launcher_path

    def start_yolo_service(self):
        """启动 Yolo Flask 子进程(监听 6001 端口)。

        使用内嵌 Python 运行时启动 Yolo 服务(替代旧的 sys.executable --yolo-server
        自克隆方式):
          1. ensure_python_runtime() 确保内嵌 Python 已部署
          2. _generate_yolo_launcher() 生成启动器脚本(_yolo_launcher.py)
          3. 定位 Yolo 源码目录并清理/注入环境变量(YOLO_SOURCE_DIR 等)
          4. 用内嵌 python.exe 执行启动器,启动 Flask + waitress
        所有耗时操作(模型加载)在子进程中执行,不阻塞 UI。
        stdout 实时通过 evaluate_js 推送到 window.__yoloServiceLog(line)。
        """
        import subprocess
        import threading

        # 1. 检查是否已运行
        if self._yolo_proc is not None and self._yolo_proc.poll() is None:
            return {"ok": False, "message": "Yolo 服务已在运行", "pid": self._yolo_proc.pid}

        # 2. 检查内嵌 Python 运行时是否已就绪(不在此处自动安装,用户需先安装)
        py_exe = self._get_python_exe()
        if not py_exe:
            return {"ok": False, "message": "内嵌 Python 运行时未安装,请先安装 Python 运行时"}

        # 2.5 检查基础依赖(flask + waitress)是否已安装,未安装则自动安装
        dep_ok, dep_msg = self._ensure_yolo_base_deps(py_exe)
        if not dep_ok:
            return {"ok": False, "message": f"Yolo 基础依赖安装失败: {dep_msg}"}

        # 3. 生成启动器脚本
        launcher_path = self._generate_yolo_launcher()

        # 4. 定位 Yolo 源码目录
        #    exe 模式: sys._MEIPASS/Yolo/(打包时 --add-data 打入)
        #    开发模式: gateway 上级目录下的 Yolo/
        if getattr(sys, "frozen", False):
            yolo_dir = os.path.join(sys._MEIPASS, "Yolo")
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            yolo_dir = os.path.join(base, "Yolo")
        if not os.path.isdir(yolo_dir):
            msg = f"Yolo 源码目录不存在: {yolo_dir}"
            log(f"[GUI] {msg}", "ERROR")
            return {"ok": False, "message": msg}

        # 5. 清理环境变量(移除 PyInstaller 注入到 PATH 中的 _MEIPASS 路径,
        #    避免内嵌 Python 误加载 exe 内的 DLL 而非自身运行时)
        clean_env = os.environ.copy()
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            path_parts = clean_env.get("PATH", "").split(os.pathsep)
            path_parts = [p for p in path_parts if p and p != meipass]
            clean_env["PATH"] = os.pathsep.join(path_parts)

        # 6. 注入 Yolo 配置环境变量(由 _yolo_launcher.py 读取)
        clean_env["YOLO_SOURCE_DIR"] = yolo_dir
        clean_env["YOLO_BACKEND_URL"] = config.BACKEND_URL or ""
        clean_env["YOLO_INTERNAL_TOKEN"] = config.INTERNAL_TOKEN or ""
        clean_env["YOLO_DEVICE"] = config.YOLO_DEVICE or ""
        clean_env["YOLO_IMGSZ"] = str(config.YOLO_IMGSZ or 480)
        clean_env["YOLO_FACE_MODEL"] = config.FACE_MODEL or "buffalo_m"
        clean_env["YOLO_FACE_SIM_THRESHOLD"] = str(config.FACE_SIM_THRESHOLD or 0.5)
        # 强制关闭 OpenVINO(避免 Intel 核显 CISA kernel header 错误导致启动失败)
        clean_env["YOLO_FORCE_OPENVINO"] = "0"
        # MODELS_DIR 非空时传递(启动器据此设置 WEIGHTS 绝对路径 + INSIGHTFACE_HOME)
        clean_env["YOLO_MODELS_DIR"] = config.MODELS_DIR or ""

        # 7. 启动子进程: 内嵌 python.exe 执行启动器脚本
        cmd = [py_exe, launcher_path]
        try:
            log(f"[GUI] 启动 Yolo 服务: {' '.join(cmd)}", "INFO")
            self._push_yolo_log(f"$ {' '.join(cmd)}\n")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
                env=clean_env,
                creationflags=0x08000000,
            )
            self._yolo_proc = proc
        except Exception as e:
            log(f"[GUI] Yolo 服务启动失败: {e}", "ERROR")
            return {"ok": False, "message": str(e)}

        # 8. 后台线程读取 stdout,推送到前端;同时缓存到 _stdout_buffer
        #    供存活检查在子进程立即退出时拼装错误消息
        _stdout_buffer = []

        def _reader():
            try:
                for line in proc.stdout:
                    _stdout_buffer.append(line)
                    self._push_yolo_log(line)
            except Exception:
                pass
            # 进程结束时通知前端
            rc = proc.returncode
            self._push_yolo_log(f"\n[Yolo] 子进程退出,returncode={rc}\n")

        threading.Thread(target=_reader, daemon=True, name="yolo-stdout-reader").start()

        # 9. 启动后存活检查:等待 2 秒,确认子进程未立即退出
        #    若启动器因 Yolo 目录缺失/依赖未安装而 sys.exit,子进程会立即退出。
        #    此处检查可避免前端误以为服务已启动。
        import time as _time
        _time.sleep(2)
        if proc.poll() is not None:
            # 子进程已退出;给 _reader 线程一点时间把剩余缓冲读入 _stdout_buffer
            try:
                _time.sleep(0.3)
            except Exception:
                pass
            output = "".join(_stdout_buffer).strip()
            self._yolo_proc = None
            err_msg = (
                f"Yolo 服务启动后立即退出 (code={proc.returncode})\n"
                f"{output}".strip()
            )
            log(f"[GUI] Yolo 服务启动后立即退出: code={proc.returncode}", "ERROR")
            return {"ok": False, "message": err_msg}

        log(f"[GUI] Yolo 服务已启动 (pid={proc.pid})", "SUCCESS")
        return {"ok": True, "pid": proc.pid}

    def _push_yolo_log(self, line):
        """将一行 Yolo 服务日志推送到前端 window.__yoloServiceLog(line)。"""
        if self._window is None:
            return
        try:
            safe = (
                line.replace("\\", "\\\\")
                .replace("'", "\\'")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r")
            )
            js = f"window.__yoloServiceLog && window.__yoloServiceLog({safe!r})"
            self._window.evaluate_js(js)
        except Exception:
            pass

    def stop_yolo_service(self):
        """停止 Yolo Flask 子进程。terminate + wait(timeout=5)。"""
        proc = self._yolo_proc
        if proc is None or proc.poll() is not None:
            self._yolo_proc = None
            return {"ok": True, "message": "服务未运行"}

        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                # terminate 超时,强制 kill
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except Exception:
                    pass
            log(f"[GUI] Yolo 服务已停止 (pid={proc.pid})", "INFO")
        except Exception as e:
            log(f"[GUI] 停止 Yolo 服务异常: {e}", "ERROR")
        finally:
            self._yolo_proc = None
        return {"ok": True}

    def get_yolo_service_status(self):
        """返回 Yolo 子进程运行状态供前端轮询。"""
        proc = self._yolo_proc
        if proc is None:
            return {"running": False, "pid": None}
        running = proc.poll() is None
        return {"running": running, "pid": proc.pid if running else None}

    # ==================== WebSocket 桥接（备选方案） ====================

    def ws_bridge_start(self):
        """启动 WebSocket 桥接（前端直连失败时的备选方案）。"""
        try:
            return self._get_ws_bridge().start()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def ws_bridge_stop(self):
        """停止 WebSocket 桥接。"""
        try:
            self._get_ws_bridge().stop()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def ws_bridge_status(self):
        """返回 WebSocket 桥接状态。"""
        try:
            return self._get_ws_bridge().status()
        except Exception as e:
            return {
                "running": False,
                "connected": False,
                "backend_url": "",
                "error": str(e),
            }

    # ==================== 窗口控制 ====================

    def minimize_window(self):
        """最小化窗口。"""
        self._window.minimize()

    def toggle_maximize(self):
        """切换最大化/还原。"""
        if self._maximized:
            self._window.restore()
            self._maximized = False
        else:
            self._window.maximize()
            self._maximized = True
        return {"maximized": self._maximized}

    def close_window(self):
        """关闭窗口（由 JS 端确认后调用）。"""
        self._cleanup()
        self._window.destroy()

    def on_closing(self):
        """Alt+F4 等系统关闭事件：清理资源后退出。"""
        self._cleanup()

    def _cleanup(self):
        """清理所有资源:停止网关线程 + 关闭串口 + 停止 ws_bridge。

        窗口关闭时必须显式关闭串口,否则 Python 进程退出前串口句柄可能残留,
        导致下次启动 EXE 时报"串口被占用"。
        """
        if self._core:
            try:
                self._core.stop()
            except Exception:
                pass
            self._core = None
        if self._serial_port_obj is not None:
            try:
                self._serial_port_obj.close()
            except Exception:
                pass
            self._serial_port_obj = None
            self._serial_open = False
        self._gateway_running = False
        # 停止 WebSocket 桥接
        if self._ws_bridge is not None:
            try:
                self._ws_bridge.stop()
            except Exception:
                pass
            self._ws_bridge = None
        # 停止 Yolo 子进程
        if self._yolo_proc is not None and self._yolo_proc.poll() is None:
            try:
                self._yolo_proc.terminate()
                try:
                    self._yolo_proc.wait(timeout=3)
                except Exception:
                    try:
                        self._yolo_proc.kill()
                    except Exception:
                        pass
            except Exception:
                pass
        self._yolo_proc = None
        # 关闭 Yolo HTTP session
        if hasattr(self, "_yolo_http_session") and self._yolo_http_session is not None:
            try:
                self._yolo_http_session.close()
            except Exception:
                pass
            self._yolo_http_session = None


def _run_yolo_server():
    """Yolo Flask 服务子进程入口(模块级函数,非 GatewayApi 方法)。

    由 main() 在检测到 --yolo-server 参数时调用。运行在独立子进程中,
    不影响主进程(gateway)的 sys.modules["config"]。

    流程:
      1. 定位 Yolo/ 目录(PyInstaller 用 sys._MEIPASS,开发用上级 Yolo/)
      2. 将 Yolo 目录加入 sys.path
      3. 用 importlib 加载 Yolo/config.py,从环境变量注入配置
      4. 如 MODELS_DIR 非空,设置 WEIGHTS 为绝对路径 + INSIGHTFACE_HOME
      5. 将 Yolo config 模块注册为 sys.modules["config"](供 app.py 导入)
      6. from app import create_app; waitress.serve(...)
    """
    import importlib.util

    # 1. 定位 Yolo 目录
    #    优先从环境变量 YOLO_SOURCE_DIR 读取(启动器脚本设置)
    yolo_source = os.environ.get("YOLO_SOURCE_DIR", "")
    if yolo_source:
        yolo_dir = yolo_source
    elif getattr(sys, "frozen", False):
        yolo_dir = os.path.join(sys._MEIPASS, "Yolo")
    else:
        base = os.path.dirname(os.path.abspath(__file__))
        yolo_dir = os.path.join(os.path.dirname(base), "Yolo")
    if not os.path.isdir(yolo_dir):
        print(f"[Yolo-Subproc] Yolo 目录不存在: {yolo_dir}", flush=True)
        sys.exit(1)
    print(f"[Yolo-Subproc] Yolo dir = {yolo_dir}", flush=True)

    # 2. 加入 sys.path(放在最前,Yolo 内部 `from app import ...` 能命中)
    if yolo_dir not in sys.path:
        sys.path.insert(0, yolo_dir)

    # 3. 加载 Yolo/config.py(按文件路径加载,避免命名冲突)
    config_path = os.path.join(yolo_dir, "config.py")
    spec = importlib.util.spec_from_file_location("yolo_inner_config", config_path)
    yolo_config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(yolo_config_module)
    YoloConfig = yolo_config_module.Config

    # 4. 从环境变量注入配置(由 start_yolo_service() 设置)
    def _env(name, default=""):
        v = os.environ.get(name)
        return v if v not in (None, "") else default

    YoloConfig.BACKEND_URL = _env("YOLO_BACKEND_URL", YoloConfig.BACKEND_URL)
    YoloConfig.INTERNAL_TOKEN = _env("YOLO_INTERNAL_TOKEN", YoloConfig.INTERNAL_TOKEN)
    YoloConfig.DEVICE = _env("YOLO_DEVICE", YoloConfig.DEVICE)
    try:
        YoloConfig.IMGSZ = int(_env("YOLO_IMGSZ", str(YoloConfig.IMGSZ)))
    except ValueError:
        pass
    YoloConfig.FACE_MODEL = _env("YOLO_FACE_MODEL", YoloConfig.FACE_MODEL)
    try:
        YoloConfig.FACE_SIM_THRESHOLD = float(
            _env("YOLO_FACE_SIM_THRESHOLD", str(YoloConfig.FACE_SIM_THRESHOLD))
        )
    except ValueError:
        pass
    # 强制覆盖 FORCE_OPENVINO(避免 Intel 核显 CISA kernel header 错误)
    _force_ov = os.environ.get("YOLO_FORCE_OPENVINO", "").strip()
    if _force_ov in ("0", "false", "False", "no"):
        YoloConfig.FORCE_OPENVINO = False
        print(f"[Yolo-Subproc] FORCE_OPENVINO = False (override)", flush=True)

    # 5. MODELS_DIR 非空时:WEIGHTS 设为绝对路径 + 设置 INSIGHTFACE_HOME
    models_dir = os.environ.get("YOLO_MODELS_DIR", "").strip()
    if models_dir:
        try:
            os.makedirs(models_dir, exist_ok=True)
        except Exception:
            pass
        YoloConfig.WEIGHTS = os.path.join(models_dir, "yolo26n.pt")
        os.environ["INSIGHTFACE_HOME"] = models_dir
        print(f"[Yolo-Subproc] MODELS_DIR = {models_dir}", flush=True)
        print(f"[Yolo-Subproc] WEIGHTS    = {YoloConfig.WEIGHTS}", flush=True)

    print(f"[Yolo-Subproc] BACKEND_URL = {YoloConfig.BACKEND_URL}", flush=True)
    print(f"[Yolo-Subproc] DEVICE      = {YoloConfig.DEVICE or '(auto)'}", flush=True)
    print(f"[Yolo-Subproc] IMGSZ       = {YoloConfig.IMGSZ}", flush=True)
    print(f"[Yolo-Subproc] FACE_MODEL  = {YoloConfig.FACE_MODEL}", flush=True)

    # 6. 注册为 sys.modules["config"],供 app.py 中 `from config import Config` 命中
    sys.modules["config"] = yolo_config_module

    # 7. 启动 Flask + waitress
    try:
        from app import create_app
        from waitress import serve
        app = create_app()
        host = YoloConfig.HOST
        port = YoloConfig.PORT
        print(f"[Yolo-Subproc] waitress serving on http://{host}:{port}", flush=True)
        serve(app, host=host, port=port, threads=4)
    except SystemExit:
        # app.create_app() 校验失败时调用 sys.exit(1),这里向上传播退出码
        raise
    except Exception as e:
        print(f"[Yolo-Subproc] 启动失败: {e}", flush=True)
        raise


def main():
    """创建 pywebview 窗口并启动。"""
    # 子进程入口:--yolo-server 参数触发 Yolo Flask 服务运行模式
    if "--yolo-server" in sys.argv:
        _run_yolo_server()
        return

    import webview

    api = GatewayApi()

    # 优先加载前端构建产物（Vue dist），回退到旧版 gui_app.html
    frontend_dist = resource_path(os.path.join("frontend", "dist", "index.html"))
    if os.path.exists(frontend_dist):
        html_path = frontend_dist
        print(f"[GUI] 加载前端构建产物: {html_path}")
    else:
        html_path = resource_path("gui_app.html")
        print(f"[GUI] 加载旧版 HTML: {html_path}")

    window = webview.create_window(
        title="WSN-Gateway",
        url=html_path,
        js_api=api,
        width=1200,
        height=900,
        min_size=(900, 680),
        text_select=False,
        frameless=True,
        easy_drag=True,
    )
    api.set_window(window)
    window.events.closing += api.on_closing

    webview.start(debug=False)


if __name__ == "__main__":
    main()
