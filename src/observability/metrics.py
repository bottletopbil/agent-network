"""Phase 20.3 - Production Monitoring with Prometheus Metrics

This module provides Prometheus metrics export for monitoring system performance,
including DECIDE latency, bus performance, and custom business metrics.
"""

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    generate_latest,
    REGISTRY,
)
import time
from functools import wraps


# ============================================================================
# CORE METRICS
# ============================================================================

# Message counters
messages_published_total = Counter(
    "agent_swarm_messages_published_total",
    "Total number of messages published to the bus",
    ["kind", "subject"],
)

messages_received_total = Counter(
    "agent_swarm_messages_received_total",
    "Total number of messages received from the bus",
    ["kind", "subject"],
)

messages_failed_total = Counter(
    "agent_swarm_messages_failed_total",
    "Total number of failed message operations",
    ["kind", "operation", "error_type"],
)

# Latency histograms
bus_publish_latency = Histogram(
    "agent_swarm_bus_publish_latency_seconds",
    "Time to publish a message to the bus",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

decide_latency = Histogram(
    "agent_swarm_decide_latency_seconds",
    "Time to process a DECIDE message",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

policy_eval_latency = Histogram(
    "agent_swarm_policy_eval_latency_seconds",
    "Time to evaluate a policy",
    buckets=[0.001, 0.005, 0.01, 0.020, 0.050, 0.1, 0.25],
)

verification_latency = Histogram(
    "agent_swarm_verification_latency_seconds",
    "Time to verify a result",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

# Task metrics
tasks_created_total = Counter(
    "agent_swarm_tasks_created_total", "Total number of tasks created", ["task_type"]
)

tasks_completed_total = Counter(
    "agent_swarm_tasks_completed_total",
    "Total number of tasks completed",
    ["task_type", "status"],
)

active_tasks = Gauge("agent_swarm_active_tasks", "Number of currently active tasks", ["task_type"])

# Agent metrics
active_agents = Gauge(
    "agent_swarm_active_agents", "Number of currently active agents", ["agent_type"]
)

agent_errors_total = Counter(
    "agent_swarm_agent_errors_total",
    "Total number of agent errors",
    ["agent_id", "error_type"],
)

# Economic metrics
staked_tokens = Gauge("agent_swarm_staked_tokens", "Total amount of tokens staked", ["pool"])

bounty_paid_total = Counter("agent_swarm_bounty_paid_total", "Total bounties paid")

slashed_tokens_total = Counter(
    "agent_swarm_slashed_tokens_total", "Total tokens slashed for bad behavior"
)

# System health
system_uptime_seconds = Gauge("agent_swarm_uptime_seconds", "System uptime in seconds")

system_info = Info("agent_swarm_system", "System information")

# Connection pool metrics (if using connection pool)
connection_pool_size = Gauge(
    "agent_swarm_connection_pool_size",
    "Number of connections in pool",
    ["status"],  # 'available' or 'in_use'
)

# Cache metrics (if using cache)
cache_operations_total = Counter(
    "agent_swarm_cache_operations_total",
    "Total cache operations",
    ["operation", "result"],  # operation: get/put, result: hit/miss
)

cache_size = Gauge("agent_swarm_cache_size", "Current cache size", ["cache_name"])


# ============================================================================
# HELPER FUNCTIONS & DECORATORS
# ============================================================================


def track_time(histogram):
    """
    Decorator to automatically track execution time.

    Args:
        histogram: Prometheus Histogram to record time

    Example:
        @track_time(bus_publish_latency)
        def publish_message(msg):
            ...
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.time() - start_time
                histogram.observe(duration)

        return wrapper

    return decorator


async def track_time_async(histogram):
    """
    Decorator to track async function execution time.

    Args:
        histogram: Prometheus Histogram to record time
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                return await func(*args, **kwargs)
            finally:
                duration = time.time() - start_time
                histogram.observe(duration)

        return wrapper

    return decorator


class MetricsContext:
    """
    Context manager for tracking metrics.

    Example:
        with MetricsContext(decide_latency) as ctx:
            process_decide()
            ctx.set_labels(thread_id="123")
    """

    def __init__(self, histogram, **labels):
        self.histogram = histogram
        self.labels = labels
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.histogram.observe(duration)
        return False

    def set_labels(self, **labels):
        """Update labels for this context."""
        self.labels.update(labels)


# ============================================================================
# METRICS COLLECTOR
# ============================================================================


class MetricsCollector:
    """
    Centralized metrics collection and export.

    Provides methods for recording various metrics and exposing them
    to Prometheus.
    """

    def __init__(self):
        self.start_time = time.time()
        self._update_system_info()

    def _update_system_info(self):
        """Update system information metric."""
        import platform

        system_info.info(
            {
                "version": "1.0.0",
                "platform": platform.system(),
                "python_version": platform.python_version(),
            }
        )

    def record_message_published(self, kind: str, subject: str):
        """Record a published message."""
        messages_published_total.labels(kind=kind, subject=subject).inc()

    def record_message_received(self, kind: str, subject: str):
        """Record a received message."""
        messages_received_total.labels(kind=kind, subject=subject).inc()

    def record_message_failed(self, kind: str, operation: str, error_type: str):
        """Record a failed message operation."""
        messages_failed_total.labels(kind=kind, operation=operation, error_type=error_type).inc()

    def record_task_created(self, task_type: str):
        """Record task creation."""
        tasks_created_total.labels(task_type=task_type).inc()
        active_tasks.labels(task_type=task_type).inc()

    def record_task_completed(self, task_type: str, status: str):
        """Record task completion."""
        tasks_completed_total.labels(task_type=task_type, status=status).inc()
        active_tasks.labels(task_type=task_type).dec()

    def set_active_agents(self, agent_type: str, count: int):
        """Set the number of active agents."""
        active_agents.labels(agent_type=agent_type).set(count)

    def record_agent_error(self, agent_id: str, error_type: str):
        """Record an agent error."""
        agent_errors_total.labels(agent_id=agent_id, error_type=error_type).inc()

    def set_staked_tokens(self, pool: str, amount: float):
        """Set staked tokens amount."""
        staked_tokens.labels(pool=pool).set(amount)

    def record_bounty_paid(self, amount: float):
        """Record a bounty payment."""
        bounty_paid_total.inc(amount)

    def record_slashing(self, amount: float):
        """Record tokens slashed."""
        slashed_tokens_total.inc(amount)

    def update_connection_pool_stats(self, available: int, in_use: int):
        """Update connection pool statistics."""
        connection_pool_size.labels(status="available").set(available)
        connection_pool_size.labels(status="in_use").set(in_use)

    def record_cache_operation(self, operation: str, result: str):
        """
        Record a cache operation.

        Args:
            operation: 'get' or 'put'
            result: 'hit' or 'miss' (for get), 'success' (for put)
        """
        cache_operations_total.labels(operation=operation, result=result).inc()

    def set_cache_size(self, cache_name: str, size: int):
        """Set current cache size."""
        cache_size.labels(cache_name=cache_name).set(size)

    def update_uptime(self):
        """Update system uptime."""
        uptime = time.time() - self.start_time
        system_uptime_seconds.set(uptime)

    def get_metrics(self) -> bytes:
        """
        Get metrics in Prometheus format.

        Returns:
            Metrics as bytes in Prometheus exposition format
        """
        self.update_uptime()
        return generate_latest(REGISTRY)


# Global metrics collector instance
metrics_collector = MetricsCollector()


# ============================================================================
# HTTP ENDPOINT (for Prometheus scraping)
# ============================================================================


def create_metrics_endpoint():
    """
    Create a simple HTTP endpoint for Prometheus to scrape.

    Returns:
        Function that handles /metrics requests
    """

    def metrics_handler():
        """Handle metrics request."""
        return metrics_collector.get_metrics()

    return metrics_handler


# Example usage for Flask/FastAPI integration
def setup_metrics_endpoint_flask(app):
    """
    Setup metrics endpoint for Flask app.

    Args:
        app: Flask application instance
    """

    @app.route("/metrics")
    def metrics():
        from flask import Response

        return Response(
            metrics_collector.get_metrics(),
            mimetype="text/plain; version=0.0.4; charset=utf-8",
        )


def setup_metrics_endpoint_fastapi(app):
    """
    Setup metrics endpoint for FastAPI app.

    Args:
        app: FastAPI application instance
    """
    from fastapi import Response

    @app.get("/metrics")
    async def metrics():
        return Response(
            content=metrics_collector.get_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )


if __name__ == "__main__":
    # Example usage
    print("Metrics Collector Example")
    print("=" * 60)

    # Record some metrics
    metrics_collector.record_message_published("PROPOSE", "thread.123.planner")
    metrics_collector.record_message_received("CLAIM", "thread.123.worker")

    with MetricsContext(decide_latency):
        time.sleep(0.5)  # Simulate DECIDE processing

    metrics_collector.record_task_created("worker")
    metrics_collector.set_active_agents("planner", 3)

    # Export metrics
    print("\nExported Metrics:")
    print("-" * 60)
    metrics_output = metrics_collector.get_metrics().decode("utf-8")
    # Print first 20 lines
    for line in metrics_output.split("\n")[:20]:
        if line and not line.startswith("#"):
            print(line)

    print("\n... (truncated)")
    print("=" * 60)
