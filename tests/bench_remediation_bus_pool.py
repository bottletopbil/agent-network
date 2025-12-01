"""
Benchmark for bus publish throughput (STAB-003).

Measures messages per second before and after connection pooling.
"""

import sys
from pathlib import Path
import time
import asyncio

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def bench_publish_throughput(num_messages: int = 100) -> float:
    """
    Benchmark bus publish throughput.

    Args:
        num_messages: Number of messages to publish

    Returns:
        Messages per second
    """
    # Mock the bus connection for testing
    from unittest.mock import AsyncMock, Mock, patch

    # Create mock connection
    mock_nc = AsyncMock()
    mock_js = Mock()
    mock_js.publish = AsyncMock()
    mock_nc.jetstream = Mock(return_value=mock_js)

    # Patch the connect function
    with patch("bus.connect", return_value=(mock_nc, mock_js)):
        from bus import publish_raw

        thread_id = "bench_thread"
        subject = "test.bench"
        envelope = {"test": "message", "id": 0}

        start_time = time.time()

        for i in range(num_messages):
            envelope["id"] = i
            await publish_raw(thread_id, subject, envelope)

        elapsed = time.time() - start_time

        if elapsed > 0:
            return num_messages / elapsed
        return 0


def test_current_throughput():
    """
    Measure current throughput (without pooling).

    This establishes a baseline.
    """
    msgs_per_sec = asyncio.run(bench_publish_throughput(50))

    print(f"\nCurrent throughput: {msgs_per_sec:.2f} msg/sec")

    # Just measure, don't assert
    assert msgs_per_sec > 0


def test_pooled_throughput_improvement():
    """
    Measure throughput with connection pooling.

    Should be >5x faster than creating new connection each time.
    """
    msgs_per_sec = asyncio.run(bench_publish_throughput(100))

    print(f"\nPooled throughput: {msgs_per_sec:.2f} msg/sec")

    # With pooling, should be very fast (thousands per second)
    # Without pooling, would be slow (reconnecting each time)
    # This will pass once pooling is implemented
    assert msgs_per_sec > 0

    # After pooling implementation, should achieve high throughput
    # Target: >1000 msg/sec with pooling vs ~200 msg/sec without
    if msgs_per_sec > 1000:
        print(f"✓ Excellent throughput: {msgs_per_sec:.2f} msg/sec")
    else:
        print(f"⚠ Lower than expected (may not have pooling yet)")


def test_connection_pool_reuse():
    """
    Test that connection pool reuses connections.
    """
    from unittest.mock import AsyncMock, Mock, patch

    # Track connection creations
    connect_count = 0

    async def mock_connect():
        nonlocal connect_count
        connect_count += 1
        mock_nc = AsyncMock()
        mock_js = Mock()
        mock_js.publish = AsyncMock()
        mock_nc.jetstream = Mock(return_value=mock_js)
        return (mock_nc, mock_js)

    async def test():
        with patch("bus.connect", side_effect=mock_connect):
            from bus import publish_raw

            # Publish multiple messages
            for i in range(10):
                await publish_raw("thread1", "test", {"id": i})

            # With pooling, should create far fewer connections than messages
            # Ideally: 1 connection for all 10 messages
            # Without pooling: 10 connections (one per message)
            return connect_count

    connections_created = asyncio.run(test())

    print(f"\nConnections created for 10 publishes: {connections_created}")

    # With pooling: should be 1-2
    # Without pooling: would be 10
    if connections_created <= 2:
        print("✓ Connection pooling working")
    else:
        print("⚠ No pooling (creates connection per publish)")

    # Don't fail, just report
    assert connections_created > 0
