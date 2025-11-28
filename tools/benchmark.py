"""Phase 20.2 - Performance Benchmarking and Load Testing

This module provides tools for measuring and optimizing system performance,
including bus latency, DECIDE latency, and policy evaluation performance.
"""

import time
import asyncio
import statistics
from typing import Dict, List, Tuple, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import json


@dataclass
class LatencyMetrics:
    """Performance metrics for a component."""
    operation: str
    samples: List[float] = field(default_factory=list)
    
    def add_sample(self, latency_ms: float):
        """Add a latency sample in milliseconds."""
        self.samples.append(latency_ms)
    
    def get_stats(self) -> Dict:
        """Calculate statistics from samples."""
        if not self.samples:
            return {
                "operation": self.operation,
                "count": 0,
                "mean": 0,
                "median": 0,
                "p50": 0,
                "p95": 0,
                "p99": 0,
                "min": 0,
                "max": 0
            }
        
        sorted_samples = sorted(self.samples)
        n = len(sorted_samples)
        
        return {
            "operation": self.operation,
            "count": n,
            "mean": statistics.mean(sorted_samples),
            "median": statistics.median(sorted_samples),
            "p50": sorted_samples[int(n * 0.50)],
            "p95": sorted_samples[int(n * 0.95)] if n > 1 else sorted_samples[0],
            "p99": sorted_samples[int(n * 0.99)] if n > 1 else sorted_samples[0],
            "min": min(sorted_samples),
            "max": max(sorted_samples)
        }


class PerformanceMonitor:
    """Monitor and track performance metrics across operations."""
    
    def __init__(self):
        self.metrics: Dict[str, LatencyMetrics] = {}
    
    def record_latency(self, operation: str, latency_ms: float):
        """Record a latency measurement."""
        if operation not in self.metrics:
            self.metrics[operation] = LatencyMetrics(operation)
        self.metrics[operation].add_sample(latency_ms)
    
    def get_metrics(self, operation: Optional[str] = None) -> Dict:
        """Get metrics for specific operation or all operations."""
        if operation:
            if operation in self.metrics:
                return self.metrics[operation].get_stats()
            return {}
        
        return {
            op: metrics.get_stats()
            for op, metrics in self.metrics.items()
        }
    
    def check_targets(self) -> Dict[str, bool]:
        """
        Check if performance targets are met.
        
        Returns:
            Dictionary of target name to pass/fail bool
        """
        results = {}
        
        # Bus latency: p99 <25ms
        if "bus_publish" in self.metrics:
            stats = self.metrics["bus_publish"].get_stats()
            results["bus_latency_p99_under_25ms"] = stats["p99"] < 25.0
        
        # DECIDE latency: p95 <2s (2000ms)
        if "decide_processing" in self.metrics:
            stats = self.metrics["decide_processing"].get_stats()
            results["decide_latency_p95_under_2s"] = stats["p95"] < 2000.0
        
        # Policy eval: p95 <20ms
        if "policy_eval" in self.metrics:
            stats = self.metrics["policy_eval"].get_stats()
            results["policy_eval_p95_under_20ms"] = stats["p95"] < 20.0
        
        return results
    
    def reset(self):
        """Clear all metrics."""
        self.metrics.clear()


class Benchmark:
    """Benchmarking utilities for load testing."""
    
    def __init__(self):
        self.monitor = PerformanceMonitor()
    
    async def load_test(
        self,
        operation: Callable,
        num_tasks: int,
        concurrency: int = 10
    ) -> Dict:
        """
        Run a load test on an async operation.
        
        Args:
            operation: Async function to test
            num_tasks: Total number of operations to perform
            concurrency: Number of concurrent operations
        
        Returns:
            Performance metrics and statistics
        """
        start_time = time.time()
        
        # Track individual operation times
        operation_times = []
        
        async def run_single():
            """Run a single operation and track time."""
            op_start = time.time()
            try:
                await operation()
                op_time = (time.time() - op_start) * 1000  # Convert to ms
                operation_times.append(op_time)
            except Exception as e:
                # Still record even if failed (will be slow)
                op_time = (time.time() - op_start) * 1000
                operation_times.append(op_time)
        
        # Run tasks with controlled concurrency
        tasks_remaining = num_tasks
        tasks = []
        
        while tasks_remaining > 0:
            batch_size = min(concurrency, tasks_remaining)
            batch = [run_single() for _ in range(batch_size)]
            await asyncio.gather(*batch, return_exceptions=True)
            tasks_remaining -= batch_size
        
        total_time = time.time() - start_time
        
        # Calculate statistics
        if operation_times:
            sorted_times = sorted(operation_times)
            n = len(sorted_times)
            
            return {
                "total_operations": num_tasks,
                "total_time_seconds": total_time,
                "throughput_ops_per_sec": num_tasks / total_time if total_time > 0 else 0,
                "latency_mean_ms": statistics.mean(sorted_times),
                "latency_median_ms": statistics.median(sorted_times),
                "latency_p50_ms": sorted_times[int(n * 0.50)],
                "latency_p95_ms": sorted_times[int(n * 0.95)] if n > 1 else sorted_times[0],
                "latency_p99_ms": sorted_times[int(n * 0.99)] if n > 1 else sorted_times[0],
                "latency_min_ms": min(sorted_times),
                "latency_max_ms": max(sorted_times)
            }
        else:
            return {
                "total_operations": 0,
                "total_time_seconds": total_time,
                "throughput_ops_per_sec": 0,
                "error": "No successful operations"
            }
    
    def measure_sync(self, operation: Callable, iterations: int = 100) -> Dict:
        """
        Measure performance of a synchronous operation.
        
        Args:
            operation: Function to measure
            iterations: Number of times to run
        
        Returns:
            Performance statistics
        """
        times = []
        
        for _ in range(iterations):
            start = time.perf_counter()
            operation()
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)
        
        sorted_times = sorted(times)
        n = len(sorted_times)
        
        return {
            "iterations": iterations,
            "mean_ms": statistics.mean(sorted_times),
            "median_ms": statistics.median(sorted_times),
            "p50_ms": sorted_times[int(n * 0.50)],
            "p95_ms": sorted_times[int(n * 0.95)] if n > 1 else sorted_times[0],
            "p99_ms": sorted_times[int(n * 0.99)] if n > 1 else sorted_times[0],
            "min_ms": min(sorted_times),
            "max_ms": max(sorted_times)
        }
    
    async def measure_async(self, operation: Callable, iterations: int = 100) -> Dict:
        """
        Measure performance of an async operation.
        
        Args:
            operation: Async function to measure
            iterations: Number of times to run
        
        Returns:
            Performance statistics
        """
        times = []
        
        for _ in range(iterations):
            start = time.perf_counter()
            await operation()
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)
        
        sorted_times = sorted(times)
        n = len(sorted_times)
        
        return {
            "iterations": iterations,
            "mean_ms": statistics.mean(sorted_times),
            "median_ms": statistics.median(sorted_times),
            "p50_ms": sorted_times[int(n * 0.50)],
            "p95_ms": sorted_times[int(n * 0.95)] if n > 1 else sorted_times[0],
            "p99_ms": sorted_times[int(n * 0.99)] if n > 1 else sorted_times[0],
            "min_ms": min(sorted_times),
            "max_ms": max(sorted_times)
        }
    
    def measure_latencies(self) -> Dict:
        """
        Get current latency measurements from the monitor.
        
        Returns:
            All tracked metrics and target check results
        """
        metrics = self.monitor.get_metrics()
        targets = self.monitor.check_targets()
        
        return {
            "metrics": metrics,
            "targets_met": targets,
            "all_targets_passed": all(targets.values()) if targets else False
        }


# Optimization utilities

class ConnectionPool:
    """
    Simple connection pool for reusing expensive connections.
    
    Reduces overhead of creating new connections for each operation.
    """
    
    def __init__(self, factory: Callable, max_size: int = 10):
        """
        Initialize connection pool.
        
        Args:
            factory: Function that creates a new connection
            max_size: Maximum number of connections to pool
        """
        self.factory = factory
        self.max_size = max_size
        self.pool: List = []
        self.in_use: set = set()
    
    def acquire(self):
        """Get a connection from the pool."""
        if self.pool:
            conn = self.pool.pop()
        else:
            conn = self.factory()
        
        self.in_use.add(id(conn))
        return conn
    
    def release(self, conn):
        """Return a connection to the pool."""
        conn_id = id(conn)
        if conn_id in self.in_use:
            self.in_use.remove(conn_id)
            
            if len(self.pool) < self.max_size:
                self.pool.append(conn)
    
    def size(self) -> Tuple[int, int]:
        """Get pool statistics (available, in_use)."""
        return len(self.pool), len(self.in_use)


class MessageBatcher:
    """
    Batches messages before sending to reduce overhead.
    
    Collects messages and sends them in groups to amortize
    network/serialization costs.
    """
    
    def __init__(self, max_batch_size: int = 100, max_wait_ms: float = 10.0):
        """
        Initialize message batcher.
        
        Args:
            max_batch_size: Maximum messages per batch
            max_wait_ms: Maximum time to wait before flushing
        """
        self.max_batch_size = max_batch_size
        self.max_wait_ms = max_wait_ms
        self.buffer: List = []
        self.last_flush = time.time()
    
    def add(self, message) -> Optional[List]:
        """
        Add a message to the batch.
        
        Returns:
            Batch if ready to flush, None otherwise
        """
        self.buffer.append(message)
        
        # Check if should flush
        if self._should_flush():
            return self.flush()
        
        return None
    
    def _should_flush(self) -> bool:
        """Check if batch should be flushed."""
        if len(self.buffer) >= self.max_batch_size:
            return True
        
        elapsed_ms = (time.time() - self.last_flush) * 1000
        if elapsed_ms >= self.max_wait_ms:
            return True
        
        return False
    
    def flush(self) -> List:
        """Flush the current batch and return messages."""
        batch = self.buffer.copy()
        self.buffer.clear()
        self.last_flush = time.time()
        return batch
    
    def pending_count(self) -> int:
        """Get number of pending messages."""
        return len(self.buffer)


class SimpleCache:
    """
    Simple LRU cache for frequently accessed data.
    
    Reduces latency by caching expensive lookups.
    """
    
    def __init__(self, max_size: int = 1000):
        """
        Initialize cache.
        
        Args:
            max_size: Maximum number of items to cache
        """
        self.max_size = max_size
        self.cache: Dict = {}
        self.access_order: List = []  # Track access order for LRU
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[any]:
        """Get value from cache."""
        if key in self.cache:
            # Move to end (most recently used)
            self.access_order.remove(key)
            self.access_order.append(key)
            self.hits += 1
            return self.cache[key]
        
        self.misses += 1
        return None
    
    def put(self, key: str, value: any):
        """Put value in cache."""
        if key in self.cache:
            # Update existing
            self.access_order.remove(key)
        elif len(self.cache) >= self.max_size:
            # Evict least recently used
            lru_key = self.access_order.pop(0)
            del self.cache[lru_key]
        
        self.cache[key] = value
        self.access_order.append(key)
    
    def invalidate(self, key: str):
        """Remove a key from cache."""
        if key in self.cache:
            del self.cache[key]
            self.access_order.remove(key)
    
    def clear(self):
        """Clear all cached data."""
        self.cache.clear()
        self.access_order.clear()
        self.hits = 0
        self.misses = 0
    
    def stats(self) -> Dict:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percent": hit_rate
        }


# Report generation

def generate_performance_report(metrics: Dict) -> str:
    """
    Generate a human-readable performance report.
    
    Args:
        metrics: Metrics from measure_latencies()
    
    Returns:
        Formatted report string
    """
    lines = []
    lines.append("=" * 60)
    lines.append("PERFORMANCE REPORT")
    lines.append("=" * 60)
    lines.append("")
    
    # Metrics
    if "metrics" in metrics:
        lines.append("LATENCY METRICS:")
        lines.append("-" * 60)
        for op, stats in metrics["metrics"].items():
            lines.append(f"\n{op}:")
            lines.append(f"  Count:   {stats['count']}")
            lines.append(f"  Mean:    {stats['mean']:.2f}ms")
            lines.append(f"  Median:  {stats['median']:.2f}ms")
            lines.append(f"  P95:     {stats['p95']:.2f}ms")
            lines.append(f"  P99:     {stats['p99']:.2f}ms")
            lines.append(f"  Min/Max: {stats['min']:.2f}ms / {stats['max']:.2f}ms")
    
    lines.append("")
    
    # Targets
    if "targets_met" in metrics:
        lines.append("TARGET COMPLIANCE:")
        lines.append("-" * 60)
        for target, passed in metrics["targets_met"].items():
            status = "✓ PASS" if passed else "✗ FAIL"
            lines.append(f"  {target}: {status}")
        
        lines.append("")
        overall = "✓ ALL TARGETS MET" if metrics.get("all_targets_passed") else "✗ SOME TARGETS MISSED"
        lines.append(overall)
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Example usage
    print("Performance Benchmark Tool")
    print("=" * 60)
    
    # Create benchmark
    bench = Benchmark()
    
    # Example: Measure a simple operation
    def simple_op():
        time.sleep(0.001)  # 1ms operation
    
    print("\nMeasuring simple operation (target: ~1ms)...")
    results = bench.measure_sync(simple_op, iterations=100)
    print(f"  Mean: {results['mean_ms']:.2f}ms")
    print(f"  P95:  {results['p95_ms']:.2f}ms")
    print(f"  P99:  {results['p99_ms']:.2f}ms")
    
    # Example: Test connection pool
    print("\nTesting connection pool...")
    pool = ConnectionPool(factory=lambda: {"conn": "mock"}, max_size=5)
    conn1 = pool.acquire()
    conn2 = pool.acquire()
    print(f"  Pool size after acquire x2: {pool.size()}")  # (0, 2)
    pool.release(conn1)
    print(f"  Pool size after release x1: {pool.size()}")  # (1, 1)
    
    # Example: Test message batcher
    print("\nTesting message batcher...")
    batcher = MessageBatcher(max_batch_size=5)
    for i in range(4):
        result = batcher.add(f"msg{i}")
        print(f"  Added msg{i}, pending: {batcher.pending_count()}, flushed: {result is not None}")
    
    # Example: Test cache
    print("\nTesting cache...")
    cache = SimpleCache(max_size=3)
    cache.put("key1", "value1")
    cache.put("key2", "value2")
    _ = cache.get("key1")  # Hit
    _ = cache.get("key3")  # Miss
    stats = cache.stats()
    print(f"  Cache stats: {stats}")
    
    print("\n" + "=" * 60)
