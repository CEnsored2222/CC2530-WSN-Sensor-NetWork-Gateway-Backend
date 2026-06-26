# -*- coding: utf-8 -*-
"""串口报文解析器。
解析串口收到的报文并分类:

上行(串口 -> 网关):
  {REG=MAC:00:12:4B:00:0D:C8:A8:CE}                              设备注册
  {Humidity=45, Temp=26, D=1, MAC=00:12:4B:00:0D:C8:A8:CE}      温湿度+LED状态
  {Light=512, D=0, MAC=00:12:4B:00:0D:3F:2A:B1}                 光照+LED状态
  {CMD=SUCCESS, LED=1, MAC=00:12:4B:00:0D:C8:A8:CE}             LED控制反馈
  {CMD=SUCCESS, STATUS=1, MAC=00:12:4B:00:0D:C8:A8:CE}         休眠控制反馈
"""


def parse_packet(line: str):
    """解析一行串口报文。
    :return: (kind, data) 元组
        kind: 'reg' | 'data' | 'feedback' | None
        data: dict,至少含 mac
    """
    line = line.strip()
    if not line or not line.startswith("{") or not line.endswith("}"):
        return None, None

    body = line[1:-1]
    fields = {}
    for part in body.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        fields[k.strip()] = v.strip()

    # 设备注册 {REG=MAC:xx:xx:...}
    if "REG" in fields:
        mac_raw = fields["REG"]
        mac = mac_raw[4:] if mac_raw.startswith("MAC:") else mac_raw
        return "reg", {"mac": mac}

    mac = fields.get("MAC")
    if mac is None:
        return None, None

    # 控制反馈 {CMD=SUCCESS, LED=1, MAC=...}
    if "CMD" in fields:
        data = {"mac": mac, "cmd_result": fields["CMD"]}
        if "LED" in fields:
            data["cmd"] = "LED"
            data["value"] = int(fields["LED"])
        elif "STATUS" in fields:
            data["cmd"] = "STATUS"
            data["value"] = int(fields["STATUS"])
        return "feedback", data

    # 数据报文 {Temp=..,Humidity=..,D=..,MAC=..} 或 {Light=..,D=..,MAC=..}
    data = {"mac": mac}
    if "Temp" in fields:
        try:
            data["temperature"] = float(fields["Temp"])
        except ValueError:
            pass
    if "Humidity" in fields:
        try:
            data["humidity"] = float(fields["Humidity"])
        except ValueError:
            pass
    if "Light" in fields:
        try:
            data["light"] = int(fields["Light"])
        except ValueError:
            pass
    if "D" in fields:
        try:
            data["led"] = int(fields["D"])
        except ValueError:
            pass

    if len(data) > 1:  # 除 mac 外至少有一个字段
        return "data", data

    return None, None
