# -*- coding: utf-8 -*-
"""串口读取器:从串口读取报文,解析后转发到 MQTT。

串口对象需提供 read_until(terminator) -> bytes 接口(pyserial.Serial 满足)。
CC2530 报文以 } 结尾且无 \\n,使用 read_until(b'}') + buffer 累积跨包报文。"""
import threading
import time

from log_handler import log
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
            log("[SerialReader] 串口不可用(serial_port=None),无法启动串口监听", "WARN")
            return
        if not gateway_state.approved:
            log("[SerialReader] 网关未审批通过,暂不启动串口监听", "INFO")
            return
        if self._running:
            log("[SerialReader] 串口监听已在运行", "INFO")
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="serial-reader")
        self._thread.start()
        log("[SerialReader] 串口监听已启动", "SUCCESS")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def update_serial(self, new_port):
        """运行时更新串口引用，用于 GUI 重新打开串口。

        先停止监听（若在运行），替换引用后自动恢复。
        """
        was_running = self._running
        if was_running:
            self.stop()
        self._serial = new_port
        if was_running:
            self.start()

    def _loop(self):
        # CC2530 报文格式为 {key=val, ..., MAC=...},无 \n 终止符。
        # 使用 read_until(b'}') 读取到 } 为止,并用 buffer 累积跨包报文。
        buffer = ""
        while self._running:
            # 串口被外部关闭(close_serial / update_serial)则静默退出,
            # 避免抛出 PortNotOpenError("Attempting to use a port that is not open")
            if self._serial is None:
                break
            if hasattr(self._serial, "is_open") and not self._serial.is_open:
                break
            try:
                raw = self._serial.read_until(b'}')
            except Exception as e:
                msg = str(e).lower()
                # 串口被关闭时 pyserial 抛出 PortNotOpenError,属于正常切换流程
                if "not open" in msg or "closed" in msg:
                    log("[SerialReader] 串口已关闭,停止读取线程", "INFO")
                    break
                log(f"[SerialReader] 读取异常: {e}", "ERROR")
                time.sleep(1)
                continue

            if not raw:
                continue
            try:
                chunk = raw.decode("utf-8", errors="ignore")
            except Exception:
                continue
            if not chunk:
                continue

            buffer += chunk
            # 防止异常设备导致 buffer 无限增长
            if len(buffer) > 1024:
                log(f"[SerialReader] buffer 溢出({len(buffer)}B),清空: {buffer[:80]!r}", "WARN")
                buffer = ""
                continue

            # 循环提取所有完整的 {...} 报文
            while True:
                start = buffer.find('{')
                if start < 0:
                    buffer = ""
                    break
                end = buffer.find('}', start)
                if end < 0:
                    # 还没读到 },保留 { 之后的内容等下次拼接
                    buffer = buffer[start:]
                    break
                line = buffer[start:end + 1].strip()
                buffer = buffer[end + 1:]
                if not line:
                    continue

                log(f"[SerialReader] 收到报文: {line}")
                kind, data = parse_packet(line)
                if kind is None:
                    log(f"[SerialReader] 报文解析失败(忽略): {line}", "WARN")
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
                    log(f"[SerialReader] 处理报文异常 kind={kind} err={e}", "ERROR")

    def _on_new_mac(self, mac: str):
        """新 MAC 出现时发布设备发现与活跃状态。"""
        self._mqtt.publish_discovery(mac)
        self._mqtt.publish_status(mac, "active")

    def _handle_reg(self, data):
        mac = data["mac"]
        is_new = self._macs.register(mac)
        if is_new:
            log(f"[SerialReader] 新设备注册 {mac}", "SUCCESS")
            self._on_new_mac(mac)

    def _handle_data(self, data):
        mac = data["mac"]
        is_new = self._macs.register(mac)
        if is_new:
            # 数据报文触发新设备发现(防止设备未先发 REG)
            log(f"[SerialReader] 数据报文发现新设备 {mac}", "SUCCESS")
            self._on_new_mac(mac)

        if "temperature" in data:
            self._mqtt.publish_temperature(mac, data["temperature"])
        if "humidity" in data:
            self._mqtt.publish_humidity(mac, data["humidity"])
        if "light" in data:
            self._mqtt.publish_light(mac, data["light"])
        if "led" in data:
            self._mqtt.publish_led(mac, data["led"])

        # 已有设备持续上报数据，刷新 active 状态（防止首次 active 消息丢失）
        if not is_new:
            self._mqtt.publish_status(mac, "active")

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
        log(f"[SerialReader] 控制反馈 dev={mac} cmd={cmd} value={value} result={result}")

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
