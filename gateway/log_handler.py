# -*- coding: utf-8 -*-
"""日志重定向器。

功能:
  - log(msg, level) 同时输出到 print(控制台) 和 queue.Queue(GUI消费)
  - 支持四级日志: INFO / WARN / ERROR / SUCCESS
  - 自动添加时间戳前缀

用法:
  from log_handler import log
  log("[MQTT] 已连接 EMQX", "SUCCESS")
  log("[SerialReader] 串口不可用", "WARN")
"""
import datetime
import queue
import threading

# 全局日志队列，供 GUI 消费（线程安全）
log_queue: queue.Queue = queue.Queue()

# 日志级别映射
LEVELS = {"INFO", "WARN", "ERROR", "SUCCESS"}

# 级别前缀标签
LEVEL_LABEL = {
    "INFO": "",
    "WARN": "[WARN] ",
    "ERROR": "[ERROR] ",
    "SUCCESS": "[OK] ",
}


def log(msg: str, level: str = "INFO"):
    """输出日志到 print 和队列。

    :param msg: 日志内容
    :param level: INFO / WARN / ERROR / SUCCESS
    """
    if level not in LEVELS:
        level = "INFO"

    label = LEVEL_LABEL.get(level, "")
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    full_msg = f"[{ts}] {label}{msg}"

    # 输出到控制台（调试用）
    print(full_msg)

    # 推入队列（GUI 消费），附带级别信息
    log_queue.put({"text": full_msg, "level": level, "ts": ts})
