# -*- coding: utf-8 -*-
"""WebSocket 桥接：Python 侧连接云端 SocketIO，转发事件到前端。

备选方案：仅在前端 SocketIO 直连失败时启用。
Python 连接云端 SocketIO，收到事件后通过 window.evaluate_js() 推送给前端。
"""
import json
import threading
from urllib.parse import urlparse

import config


class WsBridge:
    """WebSocket 桥接：Python 侧连接云端 SocketIO，转发事件到前端。

    备选方案：仅在前端 SocketIO 直连失败时启用。
    """

    def __init__(self, window=None):
        self._window = window
        self._sio = None
        self._running = False
        self._thread = None

    def set_window(self, window) -> None:
        self._window = window

    def _push_to_frontend(self, event: str, data) -> None:
        if self._window is None:
            print(f"[ws_bridge] window 未设置,丢弃事件 {event}: {data}")
            return
        try:
            js = f"window.__wsBridgePush({json.dumps(event)}, {json.dumps(data, ensure_ascii=False)})"
            self._window.evaluate_js(js)
        except Exception as e:
            print(f"[ws_bridge] 推送前端失败 event={event} err={e}")

    def start(self) -> dict:
        backend_url = config.BACKEND_URL
        if not backend_url:
            print("[ws_bridge] BACKEND_URL 为空,无法启动")
            return {"ok": False, "error": "BACKEND_URL 未配置"}

        try:
            import socketio
        except ImportError as e:
            print(f"[ws_bridge] socketio 库未安装: {e}")
            return {"ok": False, "error": f"socketio 未安装: {e}"}

        try:
            parsed = urlparse(backend_url)
            host = f"{parsed.scheme}://{parsed.netloc}"
            namespace = parsed.path or "/"
            print(f"[ws_bridge] 连接云端 host={host} namespace={namespace}")

            sio = socketio.Client()
            self._sio = sio

            def on_sensor_data(data):
                self._push_to_frontend("sensor_data", data)

            def on_device_status(data):
                self._push_to_frontend("device_status", data)

            def on_alert(data):
                self._push_to_frontend("alert", data)

            sio.on("sensor_data", on_sensor_data, namespace="/")
            sio.on("device_status", on_device_status, namespace="/")
            sio.on("alert", on_alert, namespace="/")

            sio.connect(backend_url, namespaces=["/"])
            self._running = True

            def _run():
                try:
                    sio.wait()
                except Exception as e:
                    print(f"[ws_bridge] sio.wait 异常: {e}")
                finally:
                    self._running = False

            self._thread = threading.Thread(target=_run, daemon=True, name="ws-bridge")
            self._thread.start()

            print("[ws_bridge] 已启动,转发事件到前端")
            return {"ok": True, "error": None}
        except Exception as e:
            print(f"[ws_bridge] 启动失败: {e}")
            self._running = False
            self._sio = None
            return {"ok": False, "error": str(e)}

    def stop(self) -> None:
        self._running = False
        if self._sio is not None:
            try:
                self._sio.disconnect()
                print("[ws_bridge] 已断开连接")
            except Exception as e:
                print(f"[ws_bridge] 断开异常: {e}")
        self._sio = None

    def status(self) -> dict:
        connected = False
        if self._sio is not None:
            try:
                connected = bool(getattr(self._sio, "connected", False))
            except Exception:
                connected = False
        return {
            "running": self._running,
            "connected": connected,
            "backend_url": config.BACKEND_URL,
        }
