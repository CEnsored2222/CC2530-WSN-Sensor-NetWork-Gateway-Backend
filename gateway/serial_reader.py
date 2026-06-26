# -*- coding: utf-8 -*-
"""串口读取器:从串口(或模拟器)读取报文,解析后转发到 MQTT。

串口对象需提供阻塞式 readline() -> bytes 接口(真实 pyserial.Serial
与 SerialSimulator 均满足),便于无硬件时切换为模拟器调试。"""
import threading
import time

from serial_parser import parse_packet
from state import gateway_state


class SerialReader:
    def __init__(self, serial_port, mqtt_client, mac_registry):
        """
        :param serial_port: 提供 readline() 的串口对象
        :param mqtt_client: GatewayMqttClient
        :param mac_registry: MacRegistry
        """
        self._serial = serial_port
        self._mqtt = mqtt_client
        self._macs = mac_registry
        self._running = False
        self._thread = None

    def start(self):
        if self._serial is None:
            print("[SerialReader] 串口不可用(serial_port=None),无法启动串口监听")
            return
        if not gateway_state.approved:
            print("[SerialReader] 网关未审批通过,暂不启动串口监听")
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="serial-reader")
        self._thread.start()
        print(f"[SerialReader] 串口监听已启动")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self):
        while self._running:
            try:
                raw = self._serial.readline()
            except Exception as e:
                print(f"[SerialReader] 读取异常: {e}")
                time.sleep(1)
                continue

            if not raw:
                continue
            try:
                line = raw.decode("utf-8", errors="ignore").strip()
            except Exception:
                continue
            if not line:
                continue

            kind, data = parse_packet(line)
            if kind is None:
                continue

            # 待审隔离:审批通过前不发布业务数据
            if not gateway_state.approved:
                continue

            try:
                if kind == "reg":
                    self._handle_reg(data)
                elif kind == "data":
                    self._handle_data(data)
                elif kind == "feedback":
                    self._handle_feedback(data)
            except Exception as e:
                print(f"[SerialReader] 处理报文异常 kind={kind} err={e}")

    def _on_new_mac(self, mac: str):
        """新 MAC 出现时发布设备发现与活跃状态。"""
        self._mqtt.publish_discovery(mac)
        self._mqtt.publish_status(mac, "active")

    def _handle_reg(self, data):
        mac = data["mac"]
        is_new = self._macs.register(mac)
        if is_new:
            print(f"[SerialReader] 新设备注册 {mac}")
            self._on_new_mac(mac)

    def _handle_data(self, data):
        mac = data["mac"]
        is_new = self._macs.register(mac)
        if is_new:
            # 数据报文触发新设备发现(防止设备未先发 REG)
            print(f"[SerialReader] 数据报文发现新设备 {mac}")
            self._on_new_mac(mac)

        if "temperature" in data:
            self._mqtt.publish_temperature(mac, data["temperature"])
        if "humidity" in data:
            self._mqtt.publish_humidity(mac, data["humidity"])
        if "light" in data:
            self._mqtt.publish_light(mac, data["light"])
        if "led" in data:
            self._mqtt.publish_led(mac, data["led"])

    def _handle_feedback(self, data):
        """控制指令反馈:由本地网关解析,成功时直接更新 led/status 主题。

        反馈报文示例:
          {CMD=SUCCESS, LED=1, MAC=...}      LED 控制成功
          {CMD=SUCCESS, STATUS=1, MAC=...}   休眠控制成功(1=运行/0=休眠)

        注意:指令失败时设备不会回传失败反馈,前端通过 3s 内状态未变来判断失败。
        因此这里仅在 SUCCESS 时更新状态,FAIL/其他结果忽略。
        """
        mac = data["mac"]
        cmd = data.get("cmd", "")
        value = data.get("value")
        result = (data.get("cmd_result", "") or "").upper()
        print(f"[SerialReader] 控制反馈 dev={mac} cmd={cmd} value={value} result={result}")

        # 仅当指令成功时才更新状态(失败不反馈,但也防御性处理)
        if result != "SUCCESS":
            return

        if cmd == "LED":
            # LED 反馈:刷新 MAC 计时,发布 LED 状态
            self._macs.refresh(mac)
            self._mqtt.publish_led(mac, bool(value))
        elif cmd == "STATUS":
            # STATUS 反馈:1=运行(active),0=休眠(sleep)
            if value == 1:
                # 唤醒:刷新 MAC 计时,发布 active
                self._macs.refresh(mac)
                self._mqtt.publish_status(mac, "active")
            else:
                # 休眠:主动从 MAC 注册表移除,避免 5s 后再次发布 sleep
                self._macs.force_remove(mac)
                self._mqtt.publish_status(mac, "sleep")
