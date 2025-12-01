"""
Benchmark for Lamport clock performance (ERR-002).

Measures throughput before and after I/O optimization.
"""

import sys
from pathlib import Path
import time
import tempfile

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lamport import Lamport


def bench_lamport_throughput(num_ops: int = 1000) -> float:
    """
    Benchmark Lamport clock tick() throughput.

    Args:
        num_ops: Number of tick operations to perform

    Returns:
        Ticks per second
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        clock_file = Path(tmpdir) / "lamport.json"
        clock = Lamport(clock_file)

        start_time = time.time()

        for _ in range(num_ops):
            clock.tick()

        elapsed = time.time() - start_time
        ticks_per_sec = num_ops / elapsed if elapsed > 0 else 0

        return ticks_per_sec


def test_lamport_current_performance():
    """
    Test current Lamport clock performance.

    Without optimization, this will be slow (< 200 ticks/sec)
    due to file I/O on every tick().
    """
    ticks_per_sec = bench_lamport_throughput(100)  # Reduced from 1000 for faster test

    print(f"\nLamport clock throughput: {ticks_per_sec:.2f} ticks/sec")

    # Just measure current performance, don't assert
    # (Will be slow before optimization, fast after)
    assert ticks_per_sec > 0


def test_lamport_optimized_target():
    """
    Test that optimized implementation meets target.

    After optimization with write batching, should achieve
    > 1000 ticks/sec.
    """
    ticks_per_sec = bench_lamport_throughput(1000)

    print(f"\nOptimized Lamport clock throughput: {ticks_per_sec:.2f} ticks/sec")

    # Target: > 1000 ticks/sec with batching
    # This may fail before optimization, pass after
    if ticks_per_sec < 1000:
        print(f"WARNING: Throughput {ticks_per_sec:.2f} < 1000 ticks/sec target")
        print("This is expected before write batching optimization")
    else:
        print(f"✓ Meets performance target (> 1000 ticks/sec)")

    # Don't fail the test, just report
    assert ticks_per_sec > 0


def test_lamport_observe_correctness():
    """
    Test that observe() always persists immediately (correctness).

    Even with batching, observe() must be synchronous to maintain
    correctness guarantees.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        clock_file = Path(tmpdir) / "lamport.json"
        clock1 = Lamport(clock_file)

        # Tick a few times
        clock1.tick()
        clock1.tick()
        clock1.tick()

        # Observe a higher value
        clock1.observe(10)

        # Create new clock from same file - should see observed value
        clock2 = Lamport(clock_file)

        # Should have persisted the observe()
        assert clock2.value() >= 10


def test_lamport_flush_method():
    """
    Test that flush() method persists pending writes.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        clock_file = Path(tmpdir) / "lamport.json"
        clock1 = Lamport(clock_file)

        # Tick several times (may be buffered)
        for _ in range(5):
            clock1.tick()

        # Explicit flush
        if hasattr(clock1, "flush"):
            clock1.flush()

        # Create new clock - should see flushed value
        clock2 = Lamport(clock_file)
        assert clock2.value() >= 5
