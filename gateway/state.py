# -*- coding: utf-8 -*-
"""网关运行状态(线程安全):记录是否已通过后端审批。
待审主题隔离机制下,审批通过前不发布任何业务数据。"""
import threading


class GatewayState:
    def __init__(self):
        self._approved = False
        self._lock = threading.Lock()

    @property
    def approved(self) -> bool:
        with self._lock:
            return self._approved

    def set_approved(self, value: bool):
        with self._lock:
            self._approved = value


# 全局单例
gateway_state = GatewayState()
