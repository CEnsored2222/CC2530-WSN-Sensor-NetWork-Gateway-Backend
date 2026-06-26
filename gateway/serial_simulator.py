# -*- coding: utf-8 -*-
"""串口模拟器(仅调试用,无硬件时替代真实串口)。

提供与 pyserial 一致的 readline()/write() 接口:
- 周期性生成 REG 注册包与温湿度/光照数据包(供 SerialReader 读取)
- write() 接收下行指令并自动回产生成的反馈包(可验证控制闭环)

开启方式:设置环境变量 SIMULATE_SERIAL=true
"""
import queue
import random
import threading
import time


# 模拟的两个终端节点
MAC_TH = "00:12:4B:00:0D:C8:A8:CE"   # 温湿度节点
MAC_LIGHT = "00:12:4B:00:0D:3F:2A:B1"  # 光照节点


class SerialSimulator:
    def __init__(self):
        self._queue: "queue.Queue[bytes]" = queue.Queue()
        self._running = False
        self._thread = None
        self._led_states = {MAC_TH: 0, MAC_LIGHT: 0}

    # ---------- 串口接口 ----------
    def readline(self) -> bytes:
        try:
            return self._queue.get(timeout=1)
        except queue.Empty:
            return b""

    def write(self, data: bytes):
        text = data.decode("utf-8", errors="ignore").strip()
        if not text:
            return
        print(f"[Simulator] <- 收到下发: {text}")
        self._handle_downlink(text)

    def close(self):
        self._running = False

    # ---------- 下行指令 -> 反馈 ----------
    def _handle_downlink(self, text: str):
        # 解析 {LED=1, MAC=xx} / {STATUS=1, MAC=xx}
        if not (text.startswith("{") and text.endswith("}")):
            return
        body = text[1:-1]
        fields = {}
        for part in body.split(","):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                fields[k.strip()] = v.strip()

        mac = fields.get("MAC")
        if mac is None:
            return

        if "LED" in fields:
            led = int(fields["LED"])
            self._led_states[mac] = led
            # 延迟 0.3s 回产反馈包
            threading.Timer(0.3, self._put,
                            kwargs={"s": f"{{CMD=SUCCESS, LED={led}, MAC={mac}}}"}).start()
        elif "STATUS" in fields:
            status = int(fields["STATUS"])
            threading.Timer(0.3, self._put,
                            kwargs={"s": f"{{CMD=SUCCESS, STATUS={status}, MAC={mac}}}"}).start()

    # ---------- 数据生成 ----------
    def _put(self, s: str):
        self._queue.put((s + "\n").encode("utf-8"))

    def _generate_loop(self):
        # 初始注册
        self._put(f"{{REG=MAC:{MAC_TH}}}")
        time.sleep(0.3)
        self._put(f"{{REG=MAC:{MAC_LIGHT}}}")
        time.sleep(0.5)

        temp, hum = 25.0, 50.0
        while self._running:
            # 温湿度节点:温湿度小幅波动 + LED 状态
            temp = round(temp + random.uniform(-0.3, 0.3), 1)
            hum = round(hum + random.uniform(-1.0, 1.0), 1)
            self._put(f"{{Humidity={hum}, Temp={temp}, D={self._led_states[MAC_TH]}, MAC={MAC_TH}}}")
            time.sleep(2)

            # 光照节点:光照值 + LED 状态
            light = random.randint(300, 800)
            self._put(f"{{Light={light}, D={self._led_states[MAC_LIGHT]}, MAC={MAC_LIGHT}}}")
            time.sleep(2)

    # ---------- 生命周期 ----------
    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._generate_loop, daemon=True, name="serial-sim")
        self._thread.start()
        print("[Simulator] 串口模拟器已启动(生成温湿度+光照数据)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
