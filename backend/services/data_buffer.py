# -*- coding: utf-8 -*-
"""数据入库缓冲。

后端订阅的温度/湿度/光照 实时通过 WebSocket 推送前端,同时缓冲每台设备的最新值,
每 600s 批量 flush 到 sensor_data 表(去空 + 去重)。

led_status / device_status 不入库,仅在 _latest 内存缓冲中保留(供实时查询与 WS 直推)。

- latest: 持久缓存每台设备最新值(含采集数据 + led/device 状态)
- dirty:  标记自上次 flush 以来有新采集数据的设备,flush 时仅处理这些设备
- last_flushed: 记录每台设备上一条入库的采集值,用于去重(完全相同则跳过)
"""
import threading
import time
from datetime import datetime


# 仅这些字段参与入库去空/去重判断(led_status / device_status 不入库)
_DATA_FIELDS = ("temperature", "humidity", "light")


class DataBuffer:
    def __init__(self, db, sensor_data_model, app, flush_interval=60):
        self._db = db
        self._model = sensor_data_model
        self._app = app
        self._flush_interval = flush_interval
        self._latest = {}            # device_id -> {field: value, ...}
        self._dirty = set()           # 有新采集数据待入库的 device_id
        self._last_flushed = {}       # device_id -> (temp, hum, light) 上一条入库值(去重用)
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        # MLP 环形缓冲区(torch 未装时为 None,延迟初始化)
        self._ring_buffer = None

    @property
    def ring_buffer(self):
        """延迟初始化环形缓冲区(torch 未装时返回 None)。"""
        if self._ring_buffer is None:
            try:
                from config import Config
                from services.sensor_ring_buffer import SensorRingBuffer
                self._ring_buffer = SensorRingBuffer(
                    capacity=Config.MLP_RING_BUFFER_CAPACITY)
            except ImportError:
                pass  # torch/onnxruntime 未装,环形缓冲区不可用
        return self._ring_buffer

    def update(self, device_id, **fields):
        """更新设备最新值,返回该设备当前全部最新字段(副本)。"""
        with self._lock:
            rec = self._latest.setdefault(device_id, {})
            rec.update(fields)
            # 仅当更新的是采集字段时才标记 dirty(led/status 不入库)
            if any(f in _DATA_FIELDS for f in fields):
                self._dirty.add(device_id)
                # 推送完整快照到环形缓冲区(供 MLP 微调/评估用)
                rb = self.ring_buffer
                if rb is not None:
                    import time as _time
                    rb.push(device_id, dict(rec), rec.get("_ts") or _time.time())
            return dict(rec)

    def get_latest(self, device_id):
        with self._lock:
            return dict(self._latest.get(device_id, {}))

    def clear(self, device_id):
        """设备离线时清除其缓存。"""
        with self._lock:
            self._latest.pop(device_id, None)
            self._dirty.discard(device_id)
            self._last_flushed.pop(device_id, None)

    def _flush_loop(self):
        while self._running:
            time.sleep(self._flush_interval)
            try:
                with self._app.app_context():
                    self.flush()
            except Exception as e:
                print(f"[DataBuffer] flush 异常: {e}")

    def flush(self):
        """将 dirty 设备的最新采集值批量入库(去空 + 去重)。需在 app context 中调用。

        - 去空:温度/湿度/光照 全为 None 时跳过(不存空数据)
        - 去重:与该设备上一条入库记录完全相同(三者都相等)时跳过(不存相同数据)
        - led_status / device_status 不入库
        """
        with self._lock:
            dirty = list(self._dirty)
            self._dirty.clear()
            snapshot = [(did, dict(self._latest.get(did, {}))) for did in dirty]

        if not snapshot:
            return 0

        records = []
        skipped = 0
        for did, rec in snapshot:
            temp = rec.get("temperature")
            hum = rec.get("humidity")
            light = rec.get("light")

            # 去空:三个采集字段全为 None → 不入库
            if temp is None and hum is None and light is None:
                skipped += 1
                continue

            # 去重:与上一条入库记录完全相同 → 不入库
            prev = self._last_flushed.get(did)
            curr = (temp, hum, light)
            if prev is not None and prev == curr:
                skipped += 1
                continue

            ts = rec.get("_ts")
            recorded_at = datetime.fromtimestamp(ts) if ts else datetime.now()
            records.append(self._model(
                device_id=did,
                temperature=temp,
                humidity=hum,
                light=light,
                recorded_at=recorded_at,
            ))
            self._last_flushed[did] = curr

        if records:
            self._db.session.bulk_save_objects(records)
            self._db.session.commit()
            print(f"[DataBuffer] 入库 {len(records)} 条记录,跳过 {skipped} 条(空/重复)")
        return len(records)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._flush_loop, daemon=True, name="data-buffer")
        self._thread.start()
        print(f"[DataBuffer] 启动,每 {self._flush_interval}s 入库一次(去空+去重)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
