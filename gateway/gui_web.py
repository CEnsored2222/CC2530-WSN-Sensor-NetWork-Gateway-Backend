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
from gateway_core import GatewayCore
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
            "FACE_MODEL": config.FACE_MODEL,
            "FACE_SIM_THRESHOLD": str(config.FACE_SIM_THRESHOLD),
        }

    def save_config(self, data):
        """从 JS 接收配置字典并保存到 gateway.ini。"""
        try:
            config.set_config_value("SERIAL_PORT", data.get("SERIAL_PORT", ""))
            config.set_config_value("SERIAL_BAUDRATE", int(data.get("SERIAL_BAUDRATE", 38400)))
            config.set_config_value("EMQX_HOST", data.get("EMQX_HOST", ""))
            config.set_config_value("EMQX_PORT", int(data.get("EMQX_PORT", 1883)))
            config.set_config_value("EMQX_USERNAME", data.get("EMQX_USERNAME", ""))
            config.set_config_value("EMQX_PASSWORD", data.get("EMQX_PASSWORD", ""))
            # 新增字段（兼容前端 SetupCard 的驼峰命名）
            if "BACKEND_URL" in data or "backendUrl" in data:
                config.set_config_value(
                    "BACKEND_URL",
                    data.get("BACKEND_URL") or data.get("backendUrl", ""),
                )
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
            if "FACE_MODEL" in data or "faceModel" in data:
                config.set_config_value(
                    "FACE_MODEL",
                    data.get("FACE_MODEL") or data.get("faceModel", "buffalo_l"),
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
        return {
            "running": self._gateway_running,
            "approved": gateway_state.approved if self._core else False,
            "device_count": (
                self._core._mac_registry.count()
                if self._core and self._core._mac_registry
                else 0
            ),
            "uuid": self._core.gw_uuid if self._core else "",
            "serial_open": self._serial_open,
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

    # ==================== HTTP 代理（转发到云端后端） ====================

    def http_get(self, path, params=None):
        """转发 GET 请求到云端后端。path 为含 /api 前缀的完整路径。"""
        try:
            return self._get_http().get(path, params)
        except Exception as e:
            return {"status": 0, "data": {"error": str(e)}}

    def http_post(self, path, body=None):
        """转发 POST 请求到云端后端。PUT/DELETE 也走此通道。"""
        try:
            return self._get_http().post(path, body)
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
        """下载模型，进度通过 evaluate_js 推送到前端。

        前端需注册 window.__modelDownloadProgress(modelName, downloaded, total, percent) 回调。
        """
        from model_manager import download_model as _download

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

        try:
            return _download(model_name, on_progress=on_progress)
        except Exception as e:
            return {"ok": False, "path": "", "error": str(e)}

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


def main():
    """创建 pywebview 窗口并启动。"""
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
