"""
Remediation tests for CLAIM_EXTENDED consensus bypass.
"""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from plan_store import PlanStore, OpType, TaskState  # noqa: E402
import handlers.claim_extended as claim_extended  # noqa: E402
import handlers.decide as decide_handler  # noqa: E402
from consensus.epochs import epoch_manager  # noqa: E402


class _AllowAllConsensus:
    """Test double for consensus adapter that always accepts first decide call."""

    def try_decide(
        self, need_id, proposal_id, epoch, lamport, k_plan, decider_id, timestamp_ns
    ):  # pragma: no cover - simple stub
        return {
            "need_id": need_id,
            "proposal_id": proposal_id,
            "epoch": epoch,
            "lamport": lamport,
            "k_plan": k_plan,
            "decider_id": decider_id,
            "timestamp_ns": timestamp_ns,
        }


@pytest.mark.asyncio
async def test_claim_extended_routes_decision_through_decide_handler():
    db_path = Path(tempfile.mktemp())
    store = PlanStore(db_path)

    claim_extended.plan_store = store
    claim_extended._lease_registry.clear()
    claim_extended.consensus_adapter = _AllowAllConsensus()
    claim_extended.raft_adapter = None

    decide_handler.plan_store = store
    decide_handler.consensus_adapter = claim_extended.consensus_adapter
    decide_handler.raft_adapter = None

    envelope = {
        "kind": "CLAIM_EXTENDED",
        "thread_id": "thread-claim-remediation",
        "lamport": 50,
        "sender_pk_b64": "worker-public-key",
        "payload": {
            "task_id": "task-claim-1",
            "worker_id": "worker-A",
            "lease_ttl": 120,
            "heartbeat_interval": 30,
            "need_id": "need-claim-1",
            "proposal_id": "proposal-1",
            "epoch": epoch_manager.get_current_epoch(),
        },
    }

    await claim_extended.handle_claim_extended(envelope)

    ops = await store.get_ops_for_thread("thread-claim-remediation")
    op_types = [op.op_type for op in ops]

    # No direct state write in CLAIM_EXTENDED; STATE comes from DECIDE handler path.
    assert op_types.count(OpType.STATE) == 1
    assert op_types.count(OpType.ANNOTATE) >= 2

    task = await store.get_task("task-claim-1")
    assert task is not None
    assert task["state"] == TaskState.DECIDED.value

    # Ensure decide annotation was recorded.
    decide_annotations = [
        op for op in ops if op.op_type == OpType.ANNOTATE and op.payload.get("annotation_type") == "decide"
    ]
    assert len(decide_annotations) == 1


@pytest.mark.asyncio
async def test_claim_extended_rejects_conflicting_worker_for_same_task():
    db_path = Path(tempfile.mktemp())
    store = PlanStore(db_path)

    claim_extended.plan_store = store
    claim_extended._lease_registry.clear()
    claim_extended.consensus_adapter = _AllowAllConsensus()
    claim_extended.raft_adapter = None

    decide_handler.plan_store = store
    decide_handler.consensus_adapter = claim_extended.consensus_adapter
    decide_handler.raft_adapter = None

    first = {
        "kind": "CLAIM_EXTENDED",
        "thread_id": "thread-claim-lock",
        "lamport": 100,
        "sender_pk_b64": "worker-public-key-A",
        "payload": {
            "task_id": "task-lock-1",
            "worker_id": "worker-A",
            "lease_ttl": 180,
            "heartbeat_interval": 30,
            "need_id": "need-lock-1",
            "proposal_id": "proposal-lock-A",
            "epoch": epoch_manager.get_current_epoch(),
        },
    }

    second = {
        "kind": "CLAIM_EXTENDED",
        "thread_id": "thread-claim-lock",
        "lamport": 110,
        "sender_pk_b64": "worker-public-key-B",
        "payload": {
            "task_id": "task-lock-1",
            "worker_id": "worker-B",
            "lease_ttl": 180,
            "heartbeat_interval": 30,
            "need_id": "need-lock-1",
            "proposal_id": "proposal-lock-B",
            "epoch": epoch_manager.get_current_epoch(),
        },
    }

    await claim_extended.handle_claim_extended(first)
    ops_after_first = await store.get_ops_for_thread("thread-claim-lock")

    await claim_extended.handle_claim_extended(second)
    ops_after_second = await store.get_ops_for_thread("thread-claim-lock")

    # Conflicting second claim should be rejected without adding new ops.
    assert len(ops_after_second) == len(ops_after_first)
