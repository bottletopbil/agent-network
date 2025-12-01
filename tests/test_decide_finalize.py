"""
Unit tests for DECIDE and FINALIZE handlers.

Tests:
- DECIDE atomicity via consensus
- FINALIZE state updates
"""

import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from plan_store import PlanStore, OpType, TaskState, PlanOp
from consensus import ConsensusAdapter
import handlers.decide
import handlers.finalize
import uuid
import time


class TestDecideHandler:
    """Test DECIDE handler atomicity"""

    @pytest.mark.asyncio
    async def test_decide_atomicity(self):
        """Verify DECIDE is at-most-once via consensus"""
        # Create temporary plan store and consensus adapter
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.decide.plan_store = store

        adapter = ConsensusAdapter()
        adapter.redis.flushdb()  # Clean slate
        handlers.decide.consensus_adapter = adapter

        # Create a task first
        task_id = "task-decide-test"
        add_op = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id="test-thread",
            lamport=1,
            actor_id="system",
            op_type=OpType.ADD_TASK,
            task_id=task_id,
            payload={"type": "test"},
            timestamp_ns=time.time_ns(),
        )
        store.append_op(add_op)

        # First DECIDE - should succeed
        envelope1 = {
            "kind": "DECIDE",
            "thread_id": "test-thread",
            "lamport": 100,
            "sender_pk_b64": "decider-1",
            "payload": {
                "need_id": "need-123",
                "proposal_id": "proposal-A",
                "task_id": task_id,
                "epoch": 1,
                "k_plan": 3,
            },
        }

        await handlers.decide.handle_decide(envelope1)

        # Verify DECIDE was recorded in consensus
        decide_record = adapter.get_decide("need-123")
        assert decide_record is not None
        assert decide_record.proposal_id == "proposal-A"
        assert decide_record.k_plan == 3

        # Verify task state updated to DECIDED
        task = store.get_task(task_id)
        assert task is not None
        assert task["state"] == TaskState.DECIDED.value

        # Verify DECIDE annotation recorded
        ops = store.get_ops_for_thread("test-thread")
        decide_ops = [
            op
            for op in ops
            if op.op_type == OpType.ANNOTATE and op.payload.get("annotation_type") == "decide"
        ]
        assert len(decide_ops) == 1
        assert decide_ops[0].payload["proposal_id"] == "proposal-A"

        # Second DECIDE for same need - should fail (conflict)
        envelope2 = {
            "kind": "DECIDE",
            "thread_id": "test-thread",
            "lamport": 110,
            "sender_pk_b64": "decider-2",
            "payload": {
                "need_id": "need-123",  # Same need_id
                "proposal_id": "proposal-B",  # Different proposal
                "task_id": task_id,
                "epoch": 1,
                "k_plan": 2,
            },
        }

        await handlers.decide.handle_decide(envelope2)

        # Verify original DECIDE unchanged
        decide_record = adapter.get_decide("need-123")
        assert decide_record.proposal_id == "proposal-A"  # Still A, not B

        # Verify no additional DECIDE annotation (conflict was rejected)
        ops = store.get_ops_for_thread("test-thread")
        decide_ops = [
            op
            for op in ops
            if op.op_type == OpType.ANNOTATE and op.payload.get("annotation_type") == "decide"
        ]
        assert len(decide_ops) == 1  # Still only 1

    @pytest.mark.asyncio
    async def test_decide_missing_fields(self):
        """Verify DECIDE handles missing fields gracefully"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.decide.plan_store = store

        adapter = ConsensusAdapter()
        adapter.redis.flushdb()
        handlers.decide.consensus_adapter = adapter

        # Missing proposal_id
        envelope = {
            "kind": "DECIDE",
            "thread_id": "test-thread-2",
            "lamport": 200,
            "sender_pk_b64": "decider-key",
            "payload": {
                "need_id": "need-456"
                # No proposal_id
            },
        }

        await handlers.decide.handle_decide(envelope)

        # Should not record DECIDE
        decide_record = adapter.get_decide("need-456")
        assert decide_record is None


class TestFinalizeHandler:
    """Test FINALIZE handler state updates"""

    @pytest.mark.asyncio
    async def test_finalize_state(self):
        """Verify FINALIZE updates state to FINAL"""
        # Create temporary plan store
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.finalize.plan_store = store

        # Create a task first
        task_id = "task-finalize-test"
        add_op = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id="test-thread",
            lamport=1,
            actor_id="system",
            op_type=OpType.ADD_TASK,
            task_id=task_id,
            payload={"type": "test"},
            timestamp_ns=time.time_ns(),
        )
        store.append_op(add_op)

        # Verify initial state is DRAFT
        task = store.get_task(task_id)
        assert task["state"] == TaskState.DRAFT.value

        # Send FINALIZE envelope
        envelope = {
            "kind": "FINALIZE",
            "thread_id": "test-thread",
            "lamport": 300,
            "sender_pk_b64": "finalizer-key",
            "payload": {
                "task_id": task_id,
                "metadata": {"completion_time": "2024-01-01", "result": "success"},
            },
        }

        await handlers.finalize.handle_finalize(envelope)

        # Verify state updated to FINAL
        task = store.get_task(task_id)
        assert task is not None
        assert task["state"] == TaskState.FINAL.value

        # Verify completion metadata recorded
        ops = store.get_ops_for_thread("test-thread")
        finalize_ops = [
            op
            for op in ops
            if op.op_type == OpType.ANNOTATE and op.payload.get("annotation_type") == "finalize"
        ]
        assert len(finalize_ops) == 1

        finalize_op = finalize_ops[0]
        assert finalize_op.payload["finalized_by"] == "finalizer-key"
        assert "finalized_at" in finalize_op.payload
        assert finalize_op.payload["metadata"]["result"] == "success"

    @pytest.mark.asyncio
    async def test_finalize_missing_task_id(self):
        """Verify FINALIZE handles missing task_id gracefully"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.finalize.plan_store = store

        envelope = {
            "kind": "FINALIZE",
            "thread_id": "test-thread-2",
            "lamport": 400,
            "sender_pk_b64": "finalizer-key",
            "payload": {
                "metadata": {}
                # No task_id
            },
        }

        await handlers.finalize.handle_finalize(envelope)

        # Should not create any ops
        ops = store.get_ops_for_thread("test-thread-2")
        assert len(ops) == 0

    @pytest.mark.asyncio
    async def test_finalize_multiple_times(self):
        """Verify FINALIZE can be called multiple times (idempotent)"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.finalize.plan_store = store

        # Create a task
        task_id = "task-multi-final"
        add_op = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id="test-thread-3",
            lamport=1,
            actor_id="system",
            op_type=OpType.ADD_TASK,
            task_id=task_id,
            payload={"type": "test"},
            timestamp_ns=time.time_ns(),
        )
        store.append_op(add_op)

        # First FINALIZE
        envelope1 = {
            "kind": "FINALIZE",
            "thread_id": "test-thread-3",
            "lamport": 500,
            "sender_pk_b64": "finalizer-1",
            "payload": {"task_id": task_id},
        }
        await handlers.finalize.handle_finalize(envelope1)

        # Second FINALIZE
        envelope2 = {
            "kind": "FINALIZE",
            "thread_id": "test-thread-3",
            "lamport": 510,
            "sender_pk_b64": "finalizer-2",
            "payload": {"task_id": task_id},
        }
        await handlers.finalize.handle_finalize(envelope2)

        # Task should still be FINAL
        task = store.get_task(task_id)
        assert task["state"] == TaskState.FINAL.value

        # Both finalize annotations should be recorded
        ops = store.get_ops_for_thread("test-thread-3")
        finalize_ops = [
            op
            for op in ops
            if op.op_type == OpType.ANNOTATE and op.payload.get("annotation_type") == "finalize"
        ]
        assert len(finalize_ops) == 2
