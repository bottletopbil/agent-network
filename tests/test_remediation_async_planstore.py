"""
Test for async/threading mismatch fix (RACE-001).

This test verifies that PlanStore can handle concurrent async operations
without deadlocks using asyncio.Lock instead of threading.Lock.
"""

import sys
from pathlib import Path
import pytest
import asyncio
import tempfile
import time
import uuid

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from plan_store import PlanStore, PlanOp, OpType, TaskState


@pytest.mark.asyncio
async def test_concurrent_async_operations():
    """
    Test that 100 concurrent async append_op calls complete without deadlock.

    This will FAIL/deadlock with threading.Lock but work with asyncio.Lock.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_plan.db"
        plan_store = PlanStore(db_path)

        async def append_operation(i: int):
            """Helper to append a single operation."""
            op = PlanOp(
                op_id=f"op_{i}_{uuid.uuid4()}",
                thread_id="thread_123",
                lamport=i,
                actor_id=f"actor_{i % 5}",  # 5 different actors
                op_type=OpType.ADD_TASK,
                task_id=f"task_{i}",
                payload={"type": "test_task", "index": i},
                timestamp_ns=time.time_ns(),
            )
            await plan_store.append_op(op)
            return i

        # Run 100 concurrent operations
        start_time = time.time()
        tasks = [append_operation(i) for i in range(100)]
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start_time

        # All operations should complete
        assert len(results) == 100
        assert all(isinstance(r, int) for r in results)

        # Should be reasonably fast (not deadlocked)
        # With proper async it should be under 5 seconds
        assert elapsed < 5.0, f"Operations took {elapsed}s - possible deadlock or blocking"

        # Verify all ops were actually stored
        ops = await plan_store.get_ops_for_thread("thread_123")
        assert len(ops) == 100


@pytest.mark.asyncio
async def test_concurrent_state_updates():
    """
    Test concurrent STATE operations on the same task.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_plan.db"
        plan_store = PlanStore(db_path)

        task_id = "shared_task"

        async def update_state(lamport: int, state: TaskState):
            """Update task state."""
            op = PlanOp(
                op_id=str(uuid.uuid4()),
                thread_id="thread_456",
                lamport=lamport,
                actor_id="actor_test",
                op_type=OpType.STATE,
                task_id=task_id,
                payload={"state": state.value},
                timestamp_ns=time.time_ns(),
            )
            await plan_store.append_op(op)

        # Concurrent state updates with different lamport clocks
        tasks = [
            update_state(1, TaskState.DRAFT),
            update_state(5, TaskState.DECIDED),
            update_state(3, TaskState.VERIFIED),
            update_state(7, TaskState.FINAL),
            update_state(2, TaskState.DRAFT),
        ]

        await asyncio.gather(*tasks)

        # Highest lamport should win (monotonic)
        task = await plan_store.get_task(task_id)
        assert task is not None
        assert task["state"] == TaskState.FINAL.value  # Lamport 7 wins


@pytest.mark.asyncio
async def test_no_deadlock_under_high_concurrency():
    """
    Stress test with very high concurrency to ensure no deadlocks.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_plan.db"
        plan_store = PlanStore(db_path)

        async def rapid_append(batch_id: int):
            """Rapidly append multiple operations."""
            for i in range(10):
                op = PlanOp(
                    op_id=str(uuid.uuid4()),
                    thread_id=f"thread_{batch_id % 5}",
                    lamport=batch_id * 10 + i,
                    actor_id="stress_test",
                    op_type=OpType.ADD_TASK,
                    task_id=f"task_{batch_id}_{i}",
                    payload={"batch": batch_id},
                    timestamp_ns=time.time_ns(),
                )
                await plan_store.append_op(op)

        # 50 batches * 10 ops = 500 total operations
        start_time = time.time()
        tasks = [rapid_append(i) for i in range(50)]
        await asyncio.gather(*tasks)
        elapsed = time.time() - start_time

        # Should complete quickly
        assert elapsed < 10.0, f"High concurrency test took {elapsed}s"

        print(f"✓ 500 operations completed in {elapsed:.2f}s")


@pytest.mark.asyncio
async def test_annotate_task_async():
    """
    Test that annotate_task works in async context.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_plan.db"
        plan_store = PlanStore(db_path)

        # Create a task first
        task_id = "annotated_task"
        op = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id="thread_789",
            lamport=1,
            actor_id="creator",
            op_type=OpType.ADD_TASK,
            task_id=task_id,
            payload={"type": "test"},
            timestamp_ns=time.time_ns(),
        )
        await plan_store.append_op(op)

        # Annotate it
        await plan_store.annotate_task(task_id, {"invalidated": True, "reason": "test annotation"})

        # Verify annotation was stored
        ops = await plan_store.get_ops_for_thread("thread_789")
        annotate_ops = [o for o in ops if o.op_type == OpType.ANNOTATE]
        assert len(annotate_ops) == 1
        assert annotate_ops[0].payload["invalidated"] is True
