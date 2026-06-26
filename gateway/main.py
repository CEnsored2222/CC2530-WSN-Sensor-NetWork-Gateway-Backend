# -*- coding: utf-8 -*-
"""本地网关入口。

启动流程(待审主题隔离):
1. 读取/生成网关 UUID
2. 打开串口(或启动模拟器)
3. 连接 EMQX,订阅本网关下行主题,发布注册请求
4. 等待后端审批 -> 收到 approved 后启动串口监听/MAC超时/心跳/数据转发
5. Ctrl+C 优雅退出

运行:
  pip install -r requirements.txt
  python main.py
  # 无硬件调试:
  set SIMULATE_SERIAL=true && python main.py   (Windows)
"""
import os
import threading
import time
import uuid as uuidlib

import config
from state import gateway_state
from mac_registry import MacRegistry
from mqtt_client import GatewayMqttClient
from serial_reader import SerialReader
from serial_writer import SerialWriter
from serial_simulator import SerialSimulator


def get_or_create_uuid() -> str:
    """读取或生成并持久化网关 UUID。"""
    if os.path.exists(config.GW_UUID_FILE):
        with open(config.GW_UUID_FILE, "r", encoding="utf-8") as f:
            uid = f.read().strip()
            if uid:
                return uid
    uid = str(uuidlib.uuid4())
    with open(config.GW_UUID_FILE, "w", encoding="utf-8") as f:
        f.write(uid)
    print(f"[Gateway] 生成新网关 UUID: {uid}")
    return uid


def open_serial():
    """打开串口或创建模拟器。
    :return: (serial_port, simulator)  simulator 为 None 表示真实串口
    """
    if config.SIMULATE_SERIAL:
        sim = SerialSimulator()
        print("[Gateway] 使用串口模拟器(无硬件调试模式)")
        return sim, sim

    try:
        import serial as pyserial
        port = pyserial.Serial(config.SERIAL_PORT, config.SERIAL_BAUDRATE, timeout=1)
        print(f"[Gateway] 已打开串口 {config.SERIAL_PORT}@{config.SERIAL_BAUDRATE}")
        return port, None
    except Exception as e:
        print(f"[Gateway] 串口打开失败 {config.SERIAL_PORT}: {e}")
        print("[Gateway] 串口不可用,仅运行 MQTT 部分(等待数据/指令)")
        return None, None


def connect_mqtt(mqtt: GatewayMqttClient):
    """连接 EMQX,失败则重试。"""
    while True:
        try:
            mqtt.connect()
            return
        except Exception as e:
            print(f"[Gateway] 连接 EMQX 失败({config.EMQX_HOST}:{config.EMQX_PORT}): {e},3s 后重试")
            time.sleep(3)


def heartbeat_loop(mqtt: GatewayMqttClient, running):
    while running[0]:
        if gateway_state.approved:
            try:
                mqtt.publish_heartbeat()
            except Exception as e:
                print(f"[Gateway] 心跳发送异常: {e}")
        time.sleep(config.HEARTBEAT_INTERVAL)


def main():
    gw_uuid = get_or_create_uuid()
    print(f"[Gateway] 网关 UUID = {gw_uuid}")
    print(f"[Gateway] EMQX = {config.EMQX_HOST}:{config.EMQX_PORT}")
    print(f"[Gateway] 模拟串口 = {config.SIMULATE_SERIAL}")

    serial_port, sim = open_serial()

    # 串口写入器(下行指令由 MQTT cmd 主题触发)
    serial_writer = SerialWriter(serial_port=serial_port, simulate=(serial_port is None))

    # 业务启动状态(防止重复启动)
    business_started = [False]
    running = [True]

    # MAC 列表超时回调(需要 mqtt,先占位后绑定)
    state_holder = {}

    def on_register_resp(result, user_id):
        if result == "approved" and not business_started[0]:
            business_started[0] = True
            print(f"[Gateway] 审批通过(绑定用户 user_id={user_id}),启动业务数据转发")
            if sim:
                sim.start()
            state_holder["mac_registry"].start()
            state_holder["serial_reader"].start()
            hb = threading.Thread(target=heartbeat_loop, args=(state_holder["mqtt"], running),
                                  daemon=True, name="heartbeat")
            hb.start()
        elif result == "revoked" and business_started[0]:
            print("[Gateway] 审批已撤销,停止业务数据转发,等待重新审批")
            business_started[0] = False
            try:
                state_holder["serial_reader"].stop()
            except Exception as e:
                print(f"[Gateway] 停止 serial_reader 异常: {e}")
            try:
                state_holder["mac_registry"].stop()
            except Exception as e:
                print(f"[Gateway] 停止 mac_registry 异常: {e}")
            if sim:
                try:
                    sim.stop()
                except Exception:
                    pass
            # 重新发布注册请求,回到待审列表等待用户再次审批
            state_holder["mqtt"].publish_register()

    mqtt = GatewayMqttClient(
        gw_uuid,
        cmd_handler=serial_writer.handle_cmd,
        register_resp_handler=on_register_resp,
    )

    def on_mac_remove(mac):
        if gateway_state.approved:
            mqtt.publish_status(mac, "sleep")
            print(f"[Gateway] 设备 {mac} 超时({config.MAC_TIMEOUT_SECONDS}s 无数据),发布 sleep")

    mac_registry = MacRegistry(on_remove=on_mac_remove)
    serial_reader = SerialReader(serial_port, mqtt, mac_registry)

    state_holder["mqtt"] = mqtt
    state_holder["mac_registry"] = mac_registry
    state_holder["serial_reader"] = serial_reader

    # 连接 EMQX
    connect_mqtt(mqtt)
    mqtt.loop_start()
    # 发布注册请求(待审主题隔离:此后等待 register/resp)
    mqtt.publish_register()

    print("[Gateway] 网关运行中,等待后端审批... (Ctrl+C 退出)")
    try:
        while running[0]:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Gateway] 收到退出信号,正在停止...")
        running[0] = False
    finally:
        _shutdown(serial_reader, mac_registry, sim, serial_port, mqtt)
        print("[Gateway] 已停止")


def _shutdown(serial_reader, mac_registry, sim, serial_port, mqtt):
    try:
        serial_reader.stop()
    except Exception as e:
        print(f"[Gateway] 停止 serial_reader 异常: {e}")
    try:
        mac_registry.stop()
    except Exception as e:
        print(f"[Gateway] 停止 mac_registry 异常: {e}")
    if sim:
        try:
            sim.stop()
        except Exception:
            pass
    if serial_port is not None and sim is None:
        try:
            serial_port.close()
        except Exception:
            pass
    try:
        mqtt.loop_stop()
        mqtt.disconnect()
    except Exception:
        pass


if __name__ == "__main__":
    main()
