# -*- coding: utf-8 -*-
"""网关核心生命周期管理。

将原 main.py 的 5 阶段启动流程封装为 GatewayCore 类，供 CLI 和 GUI 共用。

Phase 1  初始化 ── __init__(): UUID, 串口, MQTT, MacRegistry, SerialReader
Phase 2  连接   ── start(): 后台 connect_mqtt → loop_start → publish_register
Phase 3  待审批 ── register_resp_handler 回调: approved / revoked
Phase 4  业务   ── approved 后自动启动 mac_registry + serial_reader + heartbeat
Phase 5  关机   ── stop(): 优雅停止所有线程
"""
import os
import threading
import time
import uuid as uuidlib

import serial as pyserial

import config
from log_handler import log
from mac_registry import MacRegistry
from mqtt_client import GatewayMqttClient
from serial_reader import SerialReader
from serial_writer import SerialWriter
from state import gateway_state


def get_or_create_uuid() -> str:
    """读取或生成并持久化网关 UUID。"""
    path = config.GW_UUID_FILE
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            uid = f.read().strip()
            if uid:
                log(f"[Gateway] 从文件加载已有 UUID: {uid}")
                log(f"[Gateway] UUID 文件位置: {path}")
                return uid
    uid = str(uuidlib.uuid4())
    with open(path, "w", encoding="utf-8") as f:
        f.write(uid)
    log(f"[Gateway] 生成新网关 UUID: {uid}")
    log(f"[Gateway] UUID 已保存到: {path}")
    return uid


def reset_uuid() -> str:
    """强制删除旧 UUID 文件并重新生成。用于解决编译后 UUID 不匹配问题。"""
    path = config.GW_UUID_FILE
    if os.path.exists(path):
        os.remove(path)
        log(f"[Gateway] 已删除旧 UUID 文件: {path}")
    return get_or_create_uuid()


def open_serial():
    """打开串口。失败返回 None（网关进入 MQTT-only 模式）。"""
    try:
        port = pyserial.Serial(config.SERIAL_PORT, config.SERIAL_BAUDRATE, timeout=1)
        log(f"[Gateway] 已打开串口 {config.SERIAL_PORT}@{config.SERIAL_BAUDRATE}", "SUCCESS")
        return port
    except Exception as e:
        log(f"[Gateway] 串口打开失败 {config.SERIAL_PORT}: {e}", "WARN")
        log("[Gateway] 串口不可用,仅运行 MQTT 部分(等待数据/指令)", "WARN")
        return None


class GatewayCore:
    """网关核心，封装完整生命周期。线程安全。"""

    def __init__(self, serial_port=None):
        # ===== Phase 1: 初始化 =====
        self.gw_uuid = get_or_create_uuid()
        log(f"[Gateway] 网关 UUID = {self.gw_uuid}")
        log(f"[Gateway] EMQX = {config.EMQX_HOST}:{config.EMQX_PORT}")

        # 串口（外部传入则使用，否则自动打开）
        # _owns_serial 标记所有权:GUI 传入的串口由 GUI 管理生命周期,
        # stop() 不关闭它;CLI 模式自己打开的串口由 stop() 关闭。
        if serial_port is not None:
            self._serial_port = serial_port
            self._owns_serial = False
        else:
            self._serial_port = open_serial()
            self._owns_serial = True
        self._serial_writer = SerialWriter(serial_port=self._serial_port)

        # 业务状态
        self._business_started = threading.Event()
        self._business_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._heartbeat_thread = None

        # MQTT + 回调（先占位，后填充）
        self._mqtt = None
        self._mac_registry = None
        self._serial_reader = None

        self._init_mqtt_and_friends()

    # ---------- Phase 1 内部 ----------
    def _init_mqtt_and_friends(self):
        """创建 MQTT 客户端、MacRegistry、SerialReader，绑定回调。"""

        def on_register_resp(result, user_id):
            with self._business_lock:
                if result == "approved" and not self._business_started.is_set():
                    self._start_business()
                    log(f"[Gateway] 审批通过(绑定用户 user_id={user_id}),启动业务数据转发", "SUCCESS")
                elif result == "revoked" and self._business_started.is_set():
                    self._stop_business()
                    log("[Gateway] 审批已撤销,停止业务数据转发,等待重新审批", "WARN")
                    # 重新发布注册请求
                    self._mqtt.publish_register()

        self._mqtt = GatewayMqttClient(
            self.gw_uuid,
            cmd_handler=self._serial_writer.handle_cmd,
            register_resp_handler=on_register_resp,
        )

        def on_mac_remove(mac):
            if gateway_state.approved:
                self._mqtt.publish_status(mac, "sleep")
                log(f"[Gateway] 设备 {mac} 超时({config.MAC_TIMEOUT_SECONDS}s 无数据),发布 sleep")

        self._mac_registry = MacRegistry(
            timeout_seconds=config.MAC_TIMEOUT_SECONDS,
            on_remove=on_mac_remove,
        )
        self._serial_reader = SerialReader(self._serial_port, self._mqtt, self._mac_registry)

    # ---------- Phase 2: 连接 ----------
    def start(self):
        """启动网关：后台连接 MQTT，发布注册请求。"""
        self._stop_event.clear()
        # 连接线程（Event 可中断）
        t = threading.Thread(target=self._connect_loop, daemon=True, name="mqtt-connect")
        t.start()

    def _connect_loop(self):
        """后台 MQTT 连接重试循环。"""
        while not self._stop_event.is_set():
            try:
                self._mqtt.connect()
                break
            except Exception as e:
                log(f"[Gateway] 连接 EMQX 失败({config.EMQX_HOST}:{config.EMQX_PORT}): {e},3s 后重试", "ERROR")
                if self._stop_event.wait(3):
                    return
        if self._stop_event.is_set():
            return

        self._mqtt.loop_start()
        self._mqtt.publish_register()
        # 审批状态保留:网关重启后若审批仍有效,直接恢复业务转发
        # 审批状态只由后端 revoked 消息撤销
        if gateway_state.approved and not self._business_started.is_set():
            self._start_business()
            log("[Gateway] 审批状态仍有效,直接恢复业务数据转发", "SUCCESS")
        else:
            log("[Gateway] 网关运行中,等待后端审批...")

    # ---------- Phase 3→4: 审批回调 ----------
    def _start_business(self):
        """审批通过：启动所有业务线程。"""
        self._business_started.set()
        self._mac_registry.start()
        self._serial_reader.start()

        def heartbeat_loop():
            while self._business_started.is_set():
                if gateway_state.approved:
                    try:
                        self._mqtt.publish_heartbeat()
                    except Exception as e:
                        log(f"[Gateway] 心跳发送异常: {e}", "ERROR")
                time.sleep(config.HEARTBEAT_INTERVAL)

        self._heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True, name="heartbeat")
        self._heartbeat_thread.start()

    def _stop_business(self):
        """停止所有业务线程(网关停止或审批撤销时调用)。

        注意:不清除 gateway_state.approved。审批状态只由后端 approved/revoked
        消息控制,网关启停不应影响审批状态。这样重启网关后无需后端重新审批。
        """
        self._business_started.clear()

        # 关机前对全部活跃设备发送 sleep,防止后端保留过期 active 状态
        if self._mac_registry:
            for mac in self._mac_registry.get_all_macs():
                try:
                    self._mqtt.publish_status(mac, "sleep")
                except Exception:
                    pass
            log(f"[Gateway] 已对 {self._mac_registry.count()} 台设备发布 sleep")

        try:
            self._serial_reader.stop()
        except Exception as e:
            log(f"[Gateway] 停止 serial_reader 异常: {e}", "ERROR")
        try:
            self._mac_registry.stop()
        except Exception as e:
            log(f"[Gateway] 停止 mac_registry 异常: {e}", "ERROR")
        # 停止心跳线程
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=3)

    # ---------- 串口重新打开 ----------
    def restart_serial(self):
        """GUI 重新打开串口时调用。严格顺序操作。"""
        # 1. 关闭旧串口
        if self._serial_port is not None:
            try:
                self._serial_port.close()
            except Exception:
                pass
        # 2. 打开新串口
        self._serial_port = open_serial()
        # 3. 更新 Writer
        self._serial_writer.update_serial(self._serial_port)
        # 4. 更新 Reader（update_serial 内部会判断 was_running 并自动重启）
        self._serial_reader.update_serial(self._serial_port)
        log(f"[Gateway] 串口已重新打开 {config.SERIAL_PORT}@{config.SERIAL_BAUDRATE}", "SUCCESS")

    def close_serial(self):
        """GUI 关闭串口时调用。停止 reader，清空 writer/reader 引用。"""
        if self._serial_reader._running:
            self._serial_reader.stop()
        if self._serial_port is not None:
            try:
                self._serial_port.close()
            except Exception:
                pass
        self._serial_port = None
        self._serial_writer.update_serial(None)
        self._serial_reader.update_serial(None)
        log("[Gateway] 串口已关闭", "INFO")

    # ---------- Phase 5: 关机 ----------
    def stop(self):
        """优雅停止所有线程。

        串口关闭策略:
        - CLI 模式(_owns_serial=True):stop() 关闭自己打开的串口
        - GUI 模式(_owns_serial=False):串口由 GUI 管理生命周期,stop() 不关闭,
          停止网关后串口保持打开,用户可直接重新启动网关
        """
        self._stop_event.set()
        self._stop_business()

        if self._owns_serial and self._serial_port is not None:
            try:
                self._serial_port.close()
            except Exception:
                pass
        try:
            self._mqtt.loop_stop()
            self._mqtt.disconnect()
        except Exception:
            pass
        log("[Gateway] 已停止", "INFO")

    def wait(self, timeout=None):
        """阻塞等待（CLI 模式用）。"""
        try:
            while not self._stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            log("[Gateway] 收到退出信号,正在停止...", "WARN")
            self.stop()
