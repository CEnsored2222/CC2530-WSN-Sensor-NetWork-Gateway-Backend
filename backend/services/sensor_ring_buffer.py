# -*- coding: utf-8 -*-
"""传感器数据环形缓冲区(供 MLP 微调/评估使用)。

DataBuffer 每 60s 才 flush 一行到 sensor_data 表,30min 仅 30 行,
不足以支撑微调(需数百样本)。本缓冲区直接从 MQTT 消息流累积每条快照,
3s/条 → 30min 约 600 条,几分钟即可累积足够训练样本。

每条记录为完整合并状态(temperature/humidity/light),缺失字段为 None。
capacity=800 覆盖约 40min 数据(@3s/条),保证一个微调周期(30min)内数据完整。

线程安全:所有读写均加锁。被 DataBuffer.update()(MQTT 线程)和
FineTuneScheduler(微调子线程)并发访问。
"""
import collections
import threading

# 仅采集字段参与环形缓冲(led_status/device_status 不入训练数据)
_DATA_FIELDS = ("temperature", "humidity", "light")


class SensorRingBuffer:
    def __init__(self, capacity=800):
        self._buffers = {}           # device_id -> deque([(ts, {temp,hum,light}), ...])
        self._capacity = capacity    # 每设备最多保留 800 条(≈40min @3s/条)
        self._lock = threading.Lock()

    def push(self, device_id, fields, ts):
        """每次 MQTT 消息更新时追加一条完整快照。

        Args:
            device_id: 设备 id
            fields: 该设备当前全部最新字段(含 temperature/humidity/light 等)
            ts: 消息时间戳(秒)
        """
        with self._lock:
            if device_id not in self._buffers:
                self._buffers[device_id] = collections.deque(maxlen=self._capacity)
            data = {k: v for k, v in fields.items() if k in _DATA_FIELDS}
            self._buffers[device_id].append((ts, data))

    def get_since(self, device_id, since_ts):
        """获取某设备自 since_ts 以来的所有快照,按时间正序。

        Returns:
            list of (ts, {temp,hum,light})
        """
        with self._lock:
            buf = self._buffers.get(device_id)
            if not buf:
                return []
            return [(ts, d) for ts, d in buf if ts > since_ts]

    def get_aggregated_since(self, device_ids, since_ts):
        """多设备聚合:合并多个同类型设备的数据,按时间排序。

        全局模型不区分设备,将所有同类型设备数据混合训练。

        Args:
            device_ids: 同类型设备 id 列表(如所有 type 含 temperature 的设备)
            since_ts: 起始时间戳(秒)
        Returns:
            list of (ts, device_id, {temp,hum,light}),按 ts 正序
        """
        with self._lock:
            merged = []
            for did in device_ids:
                buf = self._buffers.get(did)
                if not buf:
                    continue
                for ts, d in buf:
                    if ts > since_ts:
                        merged.append((ts, did, dict(d)))
            merged.sort(key=lambda x: x[0])
            return merged

    def get_last_ts(self, device_ids):
        """获取多个设备中最新的时间戳(用于微调时记录 last_sample_ts)。

        Returns:
            int: 最新时间戳;无数据时返回 0
        """
        with self._lock:
            max_ts = 0
            for did in device_ids:
                buf = self._buffers.get(did)
                if buf:
                    max_ts = max(max_ts, buf[-1][0])
            return max_ts
