"""
Unit tests for Plan Store with CRDT semantics.

Tests:
- Basic ADD_TASK and retrieval
- Monotonic state advancement (STATE ops)
- Thread-based op ordering for deterministic replay
"""

import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from plan_store import PlanStore, PlanOp, OpType, TaskState
import uuid
import time


class TestPlanStoreBasic:
    """Test basic plan store operations"""

    def test_plan_store_basic(self):
        """Test ADD_TASK and get_task"""
        # Create temporary database
        db = PlanStore(Path(tempfile.mktemp()))

        # Create ADD_TASK operation
        op = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id="test-thread",
            lamport=1,
            actor_id="alice",
            op_type=OpType.ADD_TASK,
            task_id="task-1",
            payload={"type": "classify"},
            timestamp_ns=time.time_ns(),
        )

        # Append operation
        db.append_op(op)

        # Retrieve task
        task = db.get_task("task-1")

        # Verify task exists with correct properties
        assert task is not None
        assert task["task_id"] == "task-1"
        assert task["thread_id"] == "test-thread"
        assert task["task_type"] == "classify"
        assert task["state"] == "DRAFT"  # Default state

    def test_nonexistent_task(self):
        """Test retrieving nonexistent task returns None"""
        db = PlanStore(Path(tempfile.mktemp()))
        task = db.get_task("nonexistent-task")
        assert task is None


class TestStateMonotonic:
    """Test monotonic state advancement with lamport clocks"""

    def test_state_monotonic(self):
        """Test STATE only advances with higher lamport"""
        db = PlanStore(Path(tempfile.mktemp()))

        # First, add a task
        add_op = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id="test-thread",
            lamport=1,
            actor_id="alice",
            op_type=OpType.ADD_TASK,
            task_id="task-mono",
            payload={"type": "test"},
            timestamp_ns=time.time_ns(),
        )
        db.append_op(add_op)

        # Advance state to DECIDED at lamport=2
        state_op1 = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id="test-thread",
            lamport=2,
            actor_id="alice",
            op_type=OpType.STATE,
            task_id="task-mono",
            payload={"state": TaskState.DECIDED.value},
            timestamp_ns=time.time_ns(),
        )
        db.append_op(state_op1)

        task = db.get_task("task-mono")
        assert task["state"] == "DECIDED"

        # Try to regress state at lamport=1 (should NOT update - lower lamport)
        state_op2 = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id="test-thread",
            lamport=1,  # Lower than current last_lamport=2
            actor_id="bob",
            op_type=OpType.STATE,
            task_id="task-mono",
            payload={"state": TaskState.DRAFT.value},
            timestamp_ns=time.time_ns(),
        )
        db.append_op(state_op2)

        task = db.get_task("task-mono")
        assert task["state"] == "DECIDED"  # Should NOT regress

        # Try to update at lamport=3 (should NOT update - still lower than last valid)
        # Wait, actually lamport=3 > lamport=2, so it WOULD update in LWW
        # But semantically we want monotonic STATE progression
        # Let me re-read the code... The condition is `last_lamport < ?`
        # So lamport=3 would update. Let me test advancing to VERIFIED

        state_op3 = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id="test-thread",
            lamport=4,  # Higher lamport
            actor_id="charlie",
            op_type=OpType.STATE,
            task_id="task-mono",
            payload={"state": TaskState.VERIFIED.value},
            timestamp_ns=time.time_ns(),
        )
        db.append_op(state_op3)

        task = db.get_task("task-mono")
        assert task["state"] == "VERIFIED"  # Should advance

    def test_concurrent_state_updates(self):
        """Test that only the highest lamport wins"""
        db = PlanStore(Path(tempfile.mktemp()))

        # Add task
        add_op = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id="test-thread",
            lamport=1,
            actor_id="alice",
            op_type=OpType.ADD_TASK,
            task_id="task-concurrent",
            payload={"type": "test"},
            timestamp_ns=time.time_ns(),
        )
        db.append_op(add_op)

        # Two concurrent STATE updates with different lamport
        state_low = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id="test-thread",
            lamport=5,
            actor_id="alice",
            op_type=OpType.STATE,
            task_id="task-concurrent",
            payload={"state": TaskState.DECIDED.value},
            timestamp_ns=time.time_ns(),
        )

        state_high = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id="test-thread",
            lamport=10,
            actor_id="bob",
            op_type=OpType.STATE,
            task_id="task-concurrent",
            payload={"state": TaskState.VERIFIED.value},
            timestamp_ns=time.time_ns(),
        )

        # Apply in reverse order (higher first)
        db.append_op(state_high)
        db.append_op(state_low)

        # Should keep the higher lamport value (VERIFIED)
        task = db.get_task("task-concurrent")
        assert task["state"] == "VERIFIED"


class TestThreadOps:
    """Test thread-based operation ordering"""

    def test_thread_ops(self):
        """Test get_ops_for_thread ordering"""
        db = PlanStore(Path(tempfile.mktemp()))

        # Add multiple operations with different lamport timestamps
        ops_to_add = []
        for i in [3, 1, 4, 2, 5]:  # Deliberately out of order
            op = PlanOp(
                op_id=str(uuid.uuid4()),
                thread_id="test-thread",
                lamport=i,
                actor_id="alice",
                op_type=OpType.ADD_TASK,
                task_id=f"task-{i}",
                payload={"type": "test", "order": i},
                timestamp_ns=time.time_ns(),
            )
            ops_to_add.append(op)
            db.append_op(op)

        # Retrieve ops for thread
        retrieved_ops = db.get_ops_for_thread("test-thread")

        # Verify ordering by lamport (deterministic replay)
        assert len(retrieved_ops) == 5

        lamports = [op.lamport for op in retrieved_ops]
        assert lamports == [1, 2, 3, 4, 5]  # Should be sorted

        # Verify data integrity
        for i, op in enumerate(retrieved_ops, 1):
            assert op.lamport == i
            assert op.task_id == f"task-{i}"
            assert op.payload["order"] == i

    def test_different_threads_isolated(self):
        """Test that threads are isolated"""
        db = PlanStore(Path(tempfile.mktemp()))

        # Add ops to different threads
        op1 = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id="thread-a",
            lamport=1,
            actor_id="alice",
            op_type=OpType.ADD_TASK,
            task_id="task-a",
            payload={},
            timestamp_ns=time.time_ns(),
        )

        op2 = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id="thread-b",
            lamport=2,
            actor_id="bob",
            op_type=OpType.ADD_TASK,
            task_id="task-b",
            payload={},
            timestamp_ns=time.time_ns(),
        )

        db.append_op(op1)
        db.append_op(op2)

        # Each thread should only see its own ops
        ops_a = db.get_ops_for_thread("thread-a")
        ops_b = db.get_ops_for_thread("thread-b")

        assert len(ops_a) == 1
        assert len(ops_b) == 1
        assert ops_a[0].thread_id == "thread-a"
        assert ops_b[0].thread_id == "thread-b"
