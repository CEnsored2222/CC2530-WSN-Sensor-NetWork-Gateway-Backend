# -*- coding: utf-8 -*-
"""SensorRingBuffer 单元测试(纯逻辑,不依赖 db/app)。"""
import threading

from services.sensor_ring_buffer import SensorRingBuffer


class TestPushAndGetSince:
    """push / get_since 基本行为。"""

    def test_push_then_get_since(self):
        rb = SensorRingBuffer(capacity=10)
        rb.push(1, {"temperature": 25.0, "humidity": 60.0, "light": 300}, ts=100)
        rb.push(1, {"temperature": 26.0, "humidity": 61.0, "light": 310}, ts=200)

        rows = rb.get_since(1, since_ts=100)
        assert len(rows) == 1
        assert rows[0][0] == 200
        assert rows[0][1]["temperature"] == 26.0

    def test_get_since_returns_empty_for_unknown_device(self):
        rb = SensorRingBuffer()
        assert rb.get_since(999, since_ts=0) == []

    def test_get_since_inclusive_excludes_boundary(self):
        """since_ts 是排他边界(>since_ts,不含等于)。"""
        rb = SensorRingBuffer(capacity=10)
        rb.push(1, {"temperature": 25.0}, ts=100)
        rb.push(1, {"temperature": 26.0}, ts=200)
        # since=100 → 只返回 ts>100 的
        rows = rb.get_since(1, since_ts=100)
        assert len(rows) == 1
        assert rows[0][0] == 200


class TestFieldFiltering:
    """push 时只保留 _DATA_FIELDS(temperature/humidity/light)。"""

    def test_filters_non_data_fields(self):
        rb = SensorRingBuffer()
        rb.push(1, {
            "temperature": 25.0, "humidity": 60.0, "light": 300,
            "led_status": "on", "device_status": "online", "extra": "noise",
        }, ts=100)
        rows = rb.get_since(1, since_ts=0)
        assert rows[0][1] == {"temperature": 25.0, "humidity": 60.0, "light": 300}

    def test_missing_fields_preserved_as_none(self):
        """缺失字段不入字典(只有 push 时提供的字段才保留)。"""
        rb = SensorRingBuffer()
        rb.push(1, {"temperature": 25.0}, ts=100)
        rows = rb.get_since(1, since_ts=0)
        assert "temperature" in rows[0][1]
        assert "humidity" not in rows[0][1]


class TestCapacityWraparound:
    """capacity 满后,旧数据被覆盖(deque maxlen 行为)。"""

    def test_wraparound_drops_oldest(self):
        rb = SensorRingBuffer(capacity=3)
        for ts in [100, 200, 300, 400, 500]:
            rb.push(1, {"temperature": float(ts)}, ts=ts)
        # 只剩最后 3 条(300, 400, 500)
        rows = rb.get_since(1, since_ts=0)
        assert len(rows) == 3
        assert [r[0] for r in rows] == [300, 400, 500]

    def test_wraparound_get_since_only_returns_surviving(self):
        rb = SensorRingBuffer(capacity=3)
        for ts in [100, 200, 300, 400, 500]:
            rb.push(1, {"temperature": float(ts)}, ts=ts)
        # since=150 应只返回存活的且 >150 的(300,400,500),不含已淘汰的 100/200
        rows = rb.get_since(1, since_ts=150)
        assert [r[0] for r in rows] == [300, 400, 500]


class TestAggregated:
    """get_aggregated_since 多设备聚合。"""

    def test_aggregate_multiple_devices_sorted_by_ts(self):
        rb = SensorRingBuffer(capacity=10)
        # 设备1: ts 100, 300
        rb.push(1, {"temperature": 25.0}, ts=100)
        rb.push(1, {"temperature": 27.0}, ts=300)
        # 设备2: ts 200, 400
        rb.push(2, {"light": 300}, ts=200)
        rb.push(2, {"light": 400}, ts=400)

        merged = rb.get_aggregated_since([1, 2], since_ts=0)
        assert len(merged) == 4
        # 按时间正序
        assert [m[0] for m in merged] == [100, 200, 300, 400]
        # 每条带 device_id
        assert merged[0][1] == 1
        assert merged[1][1] == 2

    def test_aggregate_skips_unknown_device(self):
        rb = SensorRingBuffer()
        rb.push(1, {"temperature": 25.0}, ts=100)
        merged = rb.get_aggregated_since([1, 999], since_ts=0)
        assert len(merged) == 1


class TestGetLastTs:
    """get_last_ts 获取多设备最新时间戳。"""

    def test_returns_max_ts_across_devices(self):
        rb = SensorRingBuffer()
        rb.push(1, {"temperature": 25.0}, ts=100)
        rb.push(2, {"light": 300}, ts=200)
        rb.push(1, {"temperature": 26.0}, ts=150)
        assert rb.get_last_ts([1, 2]) == 200

    def test_returns_zero_for_empty(self):
        rb = SensorRingBuffer()
        assert rb.get_last_ts([1, 2]) == 0


class TestThreadSafety:
    """多线程并发 push 不丢数据不崩溃。"""

    def test_concurrent_push_no_crash(self):
        rb = SensorRingBuffer(capacity=10000)
        errors = []

        def worker(device_id, count):
            try:
                for i in range(count):
                    rb.push(device_id, {"temperature": float(i)}, ts=i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(d, 200)) for d in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        # 每设备 200 条,capacity 足够大,应全部保留
        for d in range(5):
            assert len(rb.get_since(d, since_ts=-1)) == 200
