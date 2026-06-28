# -*- coding: utf-8 -*-
"""串口写入器:将下行控制指令转为串口报文下发。

下行(网关 -> 串口):
  {LED=1, MAC=00:12:4B:00:0D:C8:A8:CE}     控制 LED(1开/0关)
  {STATUS=1, MAC=00:12:4B:00:0D:C8:A8:CE}  控制休眠(1开/0关)
"""
import threading

from log_handler import log


class SerialWriter:
    def __init__(self, serial_port=None):
        """
        :param serial_port: 已打开的串口对象(需提供 write());为 None 时仅打印不下发
        """
        self._serial = serial_port
        self._lock = threading.Lock()

    def update_serial(self, new_port):
        """运行时更新串口引用（GUI 重新打开串口时调用）。"""
        self._serial = new_port

    def _write(self, text: str):
        data = (text + "\n").encode("utf-8")
        if self._serial is None:
            log(f"[SerialWriter] 串口未就绪,丢弃: {text}", "WARN")
            return
        with self._lock:
            self._serial.write(data)
            if hasattr(self._serial, "flush"):
                try:
                    self._serial.flush()
                except Exception:
                    pass
        log(f"[SerialWriter] 下发: {text}")

    def write_led(self, mac: str, value):
        self._write(f"{{LED={int(value)}, MAC={mac}}}")

    def write_status(self, mac: str, value):
        self._write(f"{{STATUS={int(value)}, MAC={mac}}}")

    def handle_cmd(self, dev_mac: str, cmd: str, value):
        """MQTT cmd 主题的统一处理回调。"""
        if cmd == "LED":
            self.write_led(dev_mac, value)
        elif cmd == "STATUS":
            self.write_status(dev_mac, value)
        else:
            log(f"[SerialWriter] 未知指令 cmd={cmd}", "WARN")
