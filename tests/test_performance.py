"""Tests for Phase 20.2 - Performance Optimization"""

import pytest
import time
import asyncio
from tools.benchmark import (
    PerformanceMonitor,
    Benchmark,
    ConnectionPool,
    MessageBatcher,
    SimpleCache,
    LatencyMetrics,
    generate_performance_report,
)


class TestLatencyMetrics:
    """Test LatencyMetrics functionality."""

    def test_add_sample(self):
        """Test adding latency samples."""
        metrics = LatencyMetrics("test_op")
        metrics.add_sample(10.0)
        metrics.add_sample(20.0)
        metrics.add_sample(15.0)

        assert len(metrics.samples) == 3

    def test_get_stats(self):
        """Test calculating statistics."""
        metrics = LatencyMetrics("test_op")
        for i in range(100):
            metrics.add_sample(float(i))

        stats = metrics.get_stats()

        assert stats["operation"] == "test_op"
        assert stats["count"] == 100
        assert stats["mean"] == 49.5
        assert stats["min"] == 0.0
        assert stats["max"] == 99.0
        assert stats["p95"] > stats["p50"]
        assert stats["p99"] > stats["p95"]

    def test_get_stats_empty(self):
        """Test statistics with no samples."""
        metrics = LatencyMetrics("empty")
        stats = metrics.get_stats()

        assert stats["count"] == 0
        assert stats["mean"] == 0


class TestPerformanceMonitor:
    """Test PerformanceMonitor functionality."""

    def test_record_latency(self):
        """Test recording latency measurements."""
        monitor = PerformanceMonitor()

        monitor.record_latency("op1", 10.0)
        monitor.record_latency("op1", 15.0)
        monitor.record_latency("op2", 20.0)

        assert "op1" in monitor.metrics
        assert "op2" in monitor.metrics
        assert len(monitor.metrics["op1"].samples) == 2

    def test_get_metrics_single(self):
        """Test getting metrics for single operation."""
        monitor = PerformanceMonitor()

        monitor.record_latency("test", 10.0)
        monitor.record_latency("test", 20.0)

        stats = monitor.get_metrics("test")
        assert stats["count"] == 2
        assert stats["mean"] == 15.0

    def test_get_metrics_all(self):
        """Test getting all metrics."""
        monitor = PerformanceMonitor()

        monitor.record_latency("op1", 10.0)
        monitor.record_latency("op2", 20.0)

        all_metrics = monitor.get_metrics()
        assert "op1" in all_metrics
        assert "op2" in all_metrics

    def test_check_targets(self):
        """Test checking performance targets."""
        monitor = PerformanceMonitor()

        # Bus latency target: p99 <25ms (PASS)
        for i in range(100):
            monitor.record_latency("bus_publish", 10.0)

        # DECIDE latency target: p95 <2000ms (PASS)
        for i in range(100):
            monitor.record_latency("decide_processing", 1000.0)

        # Policy eval target: p95 <20ms (PASS)
        for i in range(100):
            monitor.record_latency("policy_eval", 5.0)

        targets = monitor.check_targets()

        assert targets["bus_latency_p99_under_25ms"] is True
        assert targets["decide_latency_p95_under_2s"] is True
        assert targets["policy_eval_p95_under_20ms"] is True

    def test_check_targets_failure(self):
        """Test detecting target failures."""
        monitor = PerformanceMonitor()

        # Bus latency target: p99 <25ms (FAIL - too slow)
        for i in range(100):
            monitor.record_latency("bus_publish", 50.0)

        targets = monitor.check_targets()
        assert targets["bus_latency_p99_under_25ms"] is False

    def test_reset(self):
        """Test resetting metrics."""
        monitor = PerformanceMonitor()
        monitor.record_latency("test", 10.0)

        assert len(monitor.metrics) == 1

        monitor.reset()
        assert len(monitor.metrics) == 0


class TestBenchmark:
    """Test Benchmark functionality."""

    @pytest.mark.asyncio
    async def test_load_test(self):
        """Test load testing an async operation."""
        bench = Benchmark()

        async def test_op():
            await asyncio.sleep(0.001)  # 1ms

        results = await bench.load_test(test_op, num_tasks=50, concurrency=10)

        assert results["total_operations"] == 50
        assert results["total_time_seconds"] > 0
        assert results["throughput_ops_per_sec"] > 0
        assert results["latency_mean_ms"] >= 1.0

    def test_measure_sync(self):
        """Test measuring synchronous operation."""
        bench = Benchmark()

        def test_op():
            time.sleep(0.001)  # 1ms

        results = bench.measure_sync(test_op, iterations=20)

        assert results["iterations"] == 20
        assert results["mean_ms"] >= 1.0
        assert results["p95_ms"] >= results["p50_ms"]

    @pytest.mark.asyncio
    async def test_measure_async(self):
        """Test measuring async operation."""
        bench = Benchmark()

        async def test_op():
            await asyncio.sleep(0.001)  # 1ms

        results = await bench.measure_async(test_op, iterations=20)

        assert results["iterations"] == 20
        assert results["mean_ms"] >= 1.0
        assert results["p95_ms"] >= results["p50_ms"]

    def test_measure_latencies(self):
        """Test getting latency measurements."""
        bench = Benchmark()

        # Add some data
        bench.monitor.record_latency("test", 10.0)
        bench.monitor.record_latency("test", 15.0)

        latencies = bench.measure_latencies()

        assert "metrics" in latencies
        assert "targets_met" in latencies
        assert "all_targets_passed" in latencies


class TestConnectionPool:
    """Test ConnectionPool optimization."""

    def test_acquire_release(self):
        """Test basic acquire and release."""
        pool = ConnectionPool(factory=lambda: {"id": "conn"}, max_size=5)

        conn = pool.acquire()
        assert conn is not None
        assert pool.size() == (0, 1)  # 0 available, 1 in use

        pool.release(conn)
        assert pool.size() == (1, 0)  # 1 available, 0 in use

    def test_connection_reuse(self):
        """Test that connections are reused."""
        pool = ConnectionPool(factory=lambda: {"id": id}, max_size=5)

        conn1 = pool.acquire()
        pool.release(conn1)

        conn2 = pool.acquire()
        assert conn1 is conn2  # Should be same connection

    def test_max_size_limit(self):
        """Test that pool respects max size."""
        pool = ConnectionPool(factory=lambda: {"id": "conn"}, max_size=2)

        conns = [pool.acquire() for _ in range(5)]

        # Release all
        for conn in conns:
            pool.release(conn)

        # Only 2 should be pooled
        assert pool.size()[0] <= 2

    def test_multiple_concurrent(self):
        """Test multiple concurrent acquisitions."""
        pool = ConnectionPool(factory=lambda: {"id": "conn"}, max_size=10)

        conns = [pool.acquire() for _ in range(5)]
        assert pool.size() == (0, 5)

        # Release half
        pool.release(conns[0])
        pool.release(conns[1])
        assert pool.size() == (2, 3)


class TestMessageBatcher:
    """Test MessageBatcher optimization."""

    def test_add_messages(self):
        """Test adding messages to batch."""
        batcher = MessageBatcher(max_batch_size=5)

        result = batcher.add("msg1")
        assert result is None  # Not flushed yet
        assert batcher.pending_count() == 1

    def test_flush_on_max_size(self):
        """Test flushing when max size reached."""
        batcher = MessageBatcher(max_batch_size=3)

        batcher.add("msg1")
        batcher.add("msg2")
        batch = batcher.add("msg3")  # Should trigger flush

        assert batch is not None
        assert len(batch) == 3
        assert batcher.pending_count() == 0

    def test_flush_on_timeout(self):
        """Test flushing based on timeout."""
        batcher = MessageBatcher(max_batch_size=100, max_wait_ms=10.0)

        batcher.add("msg1")
        time.sleep(0.015)  # Wait >10ms

        batch = batcher.add("msg2")  # Should flush due to timeout
        assert batch is not None
        assert len(batch) == 2

    def test_manual_flush(self):
        """Test manual flush."""
        batcher = MessageBatcher(max_batch_size=100)

        batcher.add("msg1")
        batcher.add("msg2")

        batch = batcher.flush()
        assert len(batch) == 2
        assert batcher.pending_count() == 0


class TestSimpleCache:
    """Test SimpleCache optimization."""

    def test_get_put(self):
        """Test basic get/put operations."""
        cache = SimpleCache(max_size=10)

        cache.put("key1", "value1")
        value = cache.get("key1")

        assert value == "value1"
        assert cache.hits == 1
        assert cache.misses == 0

    def test_cache_miss(self):
        """Test cache miss."""
        cache = SimpleCache(max_size=10)

        value = cache.get("nonexistent")

        assert value is None
        assert cache.misses == 1

    def test_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = SimpleCache(max_size=3)

        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.put("key3", "value3")

        # Access key1 to make it recently used
        cache.get("key1")

        # Add key4, should evict key2 (least recently used)
        cache.put("key4", "value4")

        assert cache.get("key1") == "value1"  # Should still exist
        assert cache.get("key2") is None  # Should be evicted
        assert cache.get("key4") == "value4"  # Should exist

    def test_update_existing(self):
        """Test updating existing key."""
        cache = SimpleCache(max_size=10)

        cache.put("key1", "value1")
        cache.put("key1", "value2")  # Update

        assert cache.get("key1") == "value2"
        assert len(cache.cache) == 1

    def test_invalidate(self):
        """Test invalidating a key."""
        cache = SimpleCache(max_size=10)

        cache.put("key1", "value1")
        cache.invalidate("key1")

        assert cache.get("key1") is None

    def test_clear(self):
        """Test clearing cache."""
        cache = SimpleCache(max_size=10)

        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.get("key1")  # Hit

        cache.clear()

        assert len(cache.cache) == 0
        assert cache.hits == 0
        assert cache.misses == 0

    def test_stats(self):
        """Test cache statistics."""
        cache = SimpleCache(max_size=10)

        cache.put("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key2")  # Miss

        stats = cache.stats()

        assert stats["size"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate_percent"] == 50.0


class TestIntegration:
    """Integration tests for performance optimizations."""

    @pytest.mark.asyncio
    async def test_load_test_with_batching(self):
        """Test load testing with message batching."""
        bench = Benchmark()
        batcher = MessageBatcher(max_batch_size=10)

        async def batched_op():
            result = batcher.add("message")
            if result:
                # Batch ready, simulate send
                await asyncio.sleep(0.001)

        results = await bench.load_test(batched_op, num_tasks=50, concurrency=5)

        assert results["total_operations"] == 50
        assert results["throughput_ops_per_sec"] > 0

    def test_cache_with_pool(self):
        """Test cache with connection pool."""
        cache = SimpleCache(max_size=100)
        pool = ConnectionPool(factory=lambda: {"conn": "db"}, max_size=5)

        # Cache connection lookup
        cache_key = "conn_1"

        # First access - cache miss, acquire from pool
        if cache.get(cache_key) is None:
            conn = pool.acquire()
            cache.put(cache_key, conn)

        # Second access - cache hit
        cached_conn = cache.get(cache_key)
        assert cached_conn is not None

        stats = cache.stats()
        assert stats["hits"] == 1


class TestPerformanceReport:
    """Test performance report generation."""

    def test_generate_report(self):
        """Test generating performance report."""
        monitor = PerformanceMonitor()

        # Add some data
        for i in range(100):
            monitor.record_latency("bus_publish", 10.0)
            monitor.record_latency("policy_eval", 5.0)

        metrics = {
            "metrics": monitor.get_metrics(),
            "targets_met": monitor.check_targets(),
            "all_targets_passed": True,
        }

        report = generate_performance_report(metrics)

        assert "PERFORMANCE REPORT" in report
        assert "bus_publish" in report
        assert "policy_eval" in report
        assert "TARGET COMPLIANCE" in report


class TestPerformanceTargets:
    """Test that performance targets can be met."""

    def test_bus_latency_target(self):
        """Test bus latency target: p99 <25ms."""
        monitor = PerformanceMonitor()

        # Simulate fast bus operations
        for _ in range(100):
            monitor.record_latency("bus_publish", 5.0)  # 5ms avg

        stats = monitor.get_metrics("bus_publish")
        assert stats["p99"] < 25.0

        targets = monitor.check_targets()
        assert targets["bus_latency_p99_under_25ms"] is True

    def test_decide_latency_target(self):
        """Test DECIDE latency target: p95 <2s."""
        monitor = PerformanceMonitor()

        # Simulate DECIDE processing
        for _ in range(100):
            monitor.record_latency("decide_processing", 500.0)  # 500ms avg

        stats = monitor.get_metrics("decide_processing")
        assert stats["p95"] < 2000.0

        targets = monitor.check_targets()
        assert targets["decide_latency_p95_under_2s"] is True

    def test_policy_eval_target(self):
        """Test policy eval target: p95 <20ms."""
        monitor = PerformanceMonitor()

        # Simulate policy evaluation
        for _ in range(100):
            monitor.record_latency("policy_eval", 8.0)  # 8ms avg

        stats = monitor.get_metrics("policy_eval")
        assert stats["p95"] < 20.0

        targets = monitor.check_targets()
        assert targets["policy_eval_p95_under_20ms"] is True
