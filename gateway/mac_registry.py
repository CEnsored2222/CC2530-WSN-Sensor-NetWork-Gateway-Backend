# -*- coding: utf-8 -*-
"""设备 MAC 列表维护。
本地网关维护一个 MAC 列表,用于判断设备状态:
- 新 MAC 加入时由调用方发布 active
- 某设备 timeout_seconds(默认 5s)内未发数据则从列表剔除并触发 on_remove 回调
  (由调用方发布 sleep)

设备状态判断两种方式(均在本地网关完成):
1. 新 MAC 出现 + timeout_seconds 内无新数据 → sleep
2. 收到控制指令成功执行的反馈 → 改变状态(由 serial_reader 处理)
"""
import threading
import time

from log_handler import log


class MacRegistry:
    def __init__(self, timeout_seconds=5, on_remove=None):
        """
        :param timeout_seconds: 设备 MAC 无数据超时秒数，超时后触发 on_remove
        :param on_remove: 超时剔除回调 callback(mac)
        """
        # mac -> last_seen 时间戳
        self._macs = {}
        self._lock = threading.Lock()
        self._timeout_seconds = timeout_seconds
        # 设备超时剔除时的回调:callback(mac)
        self._on_remove = on_remove
        self._running = False
        self._thread = None

    def register(self, mac: str) -> bool:
        """新增或刷新 MAC 的 last_seen。若为新 MAC 返回 True。"""
        with self._lock:
            is_new = mac not in self._macs
            self._macs[mac] = time.time()
            return is_new

    def refresh(self, mac: str):
        """刷新已存在 MAC 的 last_seen。"""
        with self._lock:
            if mac in self._macs:
                self._macs[mac] = time.time()

    def force_remove(self, mac: str):
        """主动移除 MAC(不触发 on_remove 回调)。
        用于设备主动休眠:避免 timeout_seconds 超时后再触发一次 sleep 发布。
        """
        with self._lock:
            self._macs.pop(mac, None)

    def contains(self, mac: str) -> bool:
        with self._lock:
            return mac in self._macs

    def count(self) -> int:
        """返回当前活跃设备数。"""
        with self._lock:
            return len(self._macs)

    def get_all_macs(self) -> list:
        """返回当前所有活跃 MAC 列表（用于关机时批量发 sleep）。"""
        with self._lock:
            return list(self._macs.keys())

    def _check_loop(self):
        """每秒扫描,超时的 MAC 剔除并触发回调。"""
        while self._running:
            now = time.time()
            expired = []
            with self._lock:
                for mac, last in list(self._macs.items()):
                    if now - last > self._timeout_seconds:
                        expired.append(mac)
                        del self._macs[mac]
            for mac in expired:
                if self._on_remove:
                    try:
                        self._on_remove(mac)
                    except Exception as e:
                        log(f"[MacRegistry] 超时回调异常: {e}", "ERROR")
            time.sleep(1)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._check_loop, daemon=True, name="mac-timeout")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
