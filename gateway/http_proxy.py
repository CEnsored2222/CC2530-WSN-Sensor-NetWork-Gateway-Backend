# -*- coding: utf-8 -*-
"""HTTP 代理：转发前端请求到云端后端，附加 JWT 鉴权头。

gateway 桌面应用通过 pywebview 加载本地 HTML（file://），前端无法直接发起跨域请求，
故通过 js_api 桥接：前端调用 window.pywebview.api.http_get/http_post，Python 侧代理转发。
"""
import time

import requests

import config


class HttpProxy:
    """HTTP 代理：转发前端请求到云端后端，附加 JWT 鉴权头。"""

    def __init__(self):
        """创建 requests.Session，token 懒加载（每次请求读取最新值）。"""
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        """拼接 BACKEND_URL + path；BACKEND_URL 为空返回空字符串。"""
        base = config.BACKEND_URL
        if not base:
            return ""
        if not path.startswith("/"):
            path = "/" + path
        return base.rstrip("/") + path

    def _headers(self) -> dict:
        """返回请求头：始终含 Content-Type，JWT 非空时附加 Authorization。"""
        headers = {"Content-Type": "application/json"}
        token = config.JWT_TOKEN
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def get(self, path: str, params: dict = None) -> dict:
        """GET 请求到 _url(path)，timeout=10s。"""
        try:
            resp = self.session.get(
                self._url(path),
                headers=self._headers(),
                params=params,
                timeout=10,
            )
            try:
                data = resp.json()
            except ValueError:
                data = resp.text
            return {"status": resp.status_code, "data": data}
        except requests.RequestException as e:
            return {"status": 0, "data": {"error": str(e)}}

    def post(self, path: str, body: dict = None) -> dict:
        """POST 请求到 _url(path)；upload/face 路径 timeout=30s，其余 10s。"""
        if body is None:
            body = {}
        timeout = 30 if ("upload" in path or "face" in path) else 10
        try:
            resp = self.session.post(
                self._url(path),
                headers=self._headers(),
                json=body,
                timeout=timeout,
            )
            try:
                data = resp.json()
            except ValueError:
                data = resp.text
            return {"status": resp.status_code, "data": data}
        except requests.RequestException as e:
            return {"status": 0, "data": {"error": str(e)}}

    def set_token(self, token: str) -> None:
        """持久化 JWT 到 gateway.ini。"""
        config.set_config_value("JWT_TOKEN", token)
        config.save_to_file()

    def clear_token(self) -> None:
        """清除 JWT 并持久化。"""
        config.set_config_value("JWT_TOKEN", "")
        config.save_to_file()

    def test_connection(self, url: str = None) -> dict:
        """测试与后端连接，请求 {url}/api/health，timeout=5s。"""
        if url is None:
            url = config.BACKEND_URL
        if not url:
            return {
                "reachable": False,
                "latency_ms": 0,
                "status_code": 0,
                "error": "BACKEND_URL 为空",
            }
        target = url.rstrip("/") + "/api/health"
        start = time.time()
        try:
            resp = self.session.get(target, timeout=5)
            latency = int((time.time() - start) * 1000)
            return {
                "reachable": resp.ok,
                "latency_ms": latency,
                "status_code": resp.status_code,
                "error": None if resp.ok else f"HTTP {resp.status_code}",
            }
        except requests.RequestException as e:
            latency = int((time.time() - start) * 1000)
            return {
                "reachable": False,
                "latency_ms": latency,
                "status_code": 0,
                "error": str(e),
            }
