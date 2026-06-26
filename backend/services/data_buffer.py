# -*- coding: utf-8 -*-
"""数据入库缓冲。

后端订阅的温度/湿度/光照/LED状态/设备状态实时通过 WebSocket 推送前端(不入库),
同时缓冲每台设备的最新值,每 10s 批量 flush 到 sensor_data 表。

- latest: 持久缓存每台设备最新值(供实时推送与历史查询取最新)
- dirty:  标记自上次 flush 以来有新数据的设备,flush 时仅插入这些设备
"""
import threading
import time
from datetime import datetime


class DataBuffer:
    def __init__(self, db, sensor_data_model, app, flush_interval=10):
        self._db = db
        self._model = sensor_data_model
        self._app = app
        self._flush_interval = flush_interval
        self._latest = {}            # device_id -> {field: value, ...}
        self._dirty = set()           # 有新数据待入库的 device_id
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def update(self, device_id, **fields):
        """更新设备最新值,返回该设备当前全部最新字段(副本)。"""
        with self._lock:
            rec = self._latest.setdefault(device_id, {})
            rec.update(fields)
            self._dirty.add(device_id)
            return dict(rec)

    def get_latest(self, device_id):
        with self._lock:
            return dict(self._latest.get(device_id, {}))

    def clear(self, device_id):
        """设备离线时清除其缓存。"""
        with self._lock:
            self._latest.pop(device_id, None)
            self._dirty.discard(device_id)

    def _flush_loop(self):
        while self._running:
            time.sleep(self._flush_interval)
            try:
                with self._app.app_context():
                    self.flush()
            except Exception as e:
                print(f"[DataBuffer] flush 异常: {e}")

    def flush(self):
        """将 dirty 设备的最新值批量入库。需在 app context 中调用。"""
        with self._lock:
            dirty = list(self._dirty)
            self._dirty.clear()
            snapshot = [(did, dict(self._latest.get(did, {}))) for did in dirty]

        if not snapshot:
            return 0

        records = []
        for did, rec in snapshot:
            ts = rec.get("_ts")
            recorded_at = datetime.fromtimestamp(ts) if ts else datetime.now()
            records.append(self._model(
                device_id=did,
                temperature=rec.get("temperature"),
                humidity=rec.get("humidity"),
                light=rec.get("light"),
                led_status=rec.get("led_status"),
                device_status=rec.get("device_status"),
                recorded_at=recorded_at,
            ))
        self._db.session.bulk_save_objects(records)
        self._db.session.commit()
        print(f"[DataBuffer] 入库 {len(records)} 条记录")
        return len(records)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._flush_loop, daemon=True, name="data-buffer")
        self._thread.start()
        print(f"[DataBuffer] 启动,每 {self._flush_interval}s 入库一次")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
