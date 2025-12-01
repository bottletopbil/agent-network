"""
Unit tests for COMMIT and ATTEST handlers.

Tests:
- COMMIT CAS artifact validation
- ATTEST aggregation and DECIDE triggering
"""

import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from plan_store import PlanStore, OpType
from consensus import ConsensusAdapter
import handlers.commit
import handlers.attest
import cas


class TestCommitHandler:
    """Test COMMIT handler CAS validation"""

    @pytest.mark.asyncio
    async def test_commit_requires_cas(self):
        """Verify COMMIT validates artifact exists in CAS"""
        # Create temporary plan store
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.commit.plan_store = store

        # Store an artifact in CAS
        test_data = b"test artifact data"
        artifact_hash = cas.put_bytes(test_data)

        # Create COMMIT envelope with valid artifact
        envelope = {
            "kind": "COMMIT",
            "thread_id": "test-thread",
            "lamport": 40,
            "sender_pk_b64": "worker-public-key",
            "payload": {
                "task_id": "task-123",
                "commit_id": "commit-abc",
                "artifact_hash": artifact_hash,
            },
        }

        # Handle COMMIT - should succeed
        await handlers.commit.handle_commit(envelope)

        # Verify commit was recorded
        ops = store.get_ops_for_thread("test-thread")
        assert len(ops) == 1

        op = ops[0]
        assert op.op_type == OpType.ANNOTATE
        assert op.payload["annotation_type"] == "commit"
        assert op.payload["commit_id"] == "commit-abc"
        assert op.payload["artifact_hash"] == artifact_hash
        assert op.payload["committer"] == "worker-public-key"

    @pytest.mark.asyncio
    async def test_commit_rejects_missing_artifact(self):
        """Verify COMMIT rejects when artifact not in CAS"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.commit.plan_store = store

        # Create COMMIT envelope with INVALID artifact hash
        envelope = {
            "kind": "COMMIT",
            "thread_id": "test-thread-2",
            "lamport": 50,
            "sender_pk_b64": "worker-key",
            "payload": {
                "task_id": "task-456",
                "artifact_hash": "nonexistent_hash_12345678",
            },
        }

        # Handle COMMIT - should fail validation
        await handlers.commit.handle_commit(envelope)

        # Verify NO commit was recorded
        ops = store.get_ops_for_thread("test-thread-2")
        assert len(ops) == 0

    @pytest.mark.asyncio
    async def test_commit_missing_fields(self):
        """Verify COMMIT handles missing fields gracefully"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.commit.plan_store = store

        # Missing task_id
        envelope1 = {
            "kind": "COMMIT",
            "thread_id": "test-thread-3",
            "lamport": 60,
            "sender_pk_b64": "worker-key",
            "payload": {"artifact_hash": "somehash"},
        }
        await handlers.commit.handle_commit(envelope1)
        assert len(store.get_ops_for_thread("test-thread-3")) == 0

        # Missing artifact_hash
        envelope2 = {
            "kind": "COMMIT",
            "thread_id": "test-thread-4",
            "lamport": 70,
            "sender_pk_b64": "worker-key",
            "payload": {"task_id": "task-789"},
        }
        await handlers.commit.handle_commit(envelope2)
        assert len(store.get_ops_for_thread("test-thread-4")) == 0


class TestAttestHandler:
    """Test ATTEST handler aggregation and DECIDE triggering"""

    @pytest.mark.asyncio
    async def test_attest_aggregation(self):
        """Verify ATTEST counts attestations and triggers DECIDE at K=1"""
        # Create temporary plan store and consensus adapter
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.attest.plan_store = store

        # Create consensus adapter with test Redis
        adapter = ConsensusAdapter()
        adapter.redis.flushdb()  # Clean slate
        handlers.attest.consensus_adapter = adapter

        # Create ATTEST envelope
        envelope = {
            "kind": "ATTEST",
            "thread_id": "test-thread",
            "lamport": 100,
            "sender_pk_b64": "verifier-public-key",
            "payload": {
                "commit_id": "commit-xyz",
                "task_id": "task-123",
                "proposal_id": "proposal-abc",
                "need_id": "need-456",
                "verdict": "approved",
            },
        }

        # Handle ATTEST
        await handlers.attest.handle_attest(envelope)

        # Verify attestation was recorded
        ops = store.get_ops_for_thread("test-thread")
        assert len(ops) == 1

        op = ops[0]
        assert op.op_type == OpType.ANNOTATE
        assert op.payload["annotation_type"] == "attestation"
        assert op.payload["commit_id"] == "commit-xyz"
        assert op.payload["attester"] == "verifier-public-key"
        assert op.payload["verdict"] == "approved"

        # Verify DECIDE was triggered (K=1, so first attestation triggers)
        decide_record = adapter.get_decide("need-456")
        assert decide_record is not None
        assert decide_record.proposal_id == "proposal-abc"
        assert decide_record.k_plan == 1

    @pytest.mark.asyncio
    async def test_attest_multiple_attestations(self):
        """Verify multiple attestations are counted correctly"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.attest.plan_store = store

        adapter = ConsensusAdapter()
        adapter.redis.flushdb()
        handlers.attest.consensus_adapter = adapter

        commit_id = "commit-multi"
        thread_id = "test-thread-multi"

        # First attestation
        envelope1 = {
            "kind": "ATTEST",
            "thread_id": thread_id,
            "lamport": 200,
            "sender_pk_b64": "verifier-1",
            "payload": {
                "commit_id": commit_id,
                "task_id": "task-multi",
                "proposal_id": "prop-multi",
                "need_id": "need-multi",
                "verdict": "approved",
            },
        }
        await handlers.attest.handle_attest(envelope1)

        # Second attestation (different verifier)
        envelope2 = {
            "kind": "ATTEST",
            "thread_id": thread_id,
            "lamport": 210,
            "sender_pk_b64": "verifier-2",
            "payload": {
                "commit_id": commit_id,
                "task_id": "task-multi",
                "proposal_id": "prop-multi",
                "need_id": "need-multi",
                "verdict": "approved",
            },
        }
        await handlers.attest.handle_attest(envelope2)

        # Verify both attestations recorded
        ops = store.get_ops_for_thread(thread_id)
        attestations = [
            op
            for op in ops
            if op.payload.get("annotation_type") == "attestation"
            and op.payload.get("commit_id") == commit_id
        ]
        assert len(attestations) == 2

        # Verify DECIDE was triggered on first attestation (K=1)
        decide_record = adapter.get_decide("need-multi")
        assert decide_record is not None

    @pytest.mark.asyncio
    async def test_attest_missing_commit_id(self):
        """Verify ATTEST handles missing commit_id gracefully"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.attest.plan_store = store

        envelope = {
            "kind": "ATTEST",
            "thread_id": "test-thread-missing",
            "lamport": 300,
            "sender_pk_b64": "verifier-key",
            "payload": {
                "task_id": "task-xyz"
                # No commit_id
            },
        }

        await handlers.attest.handle_attest(envelope)

        # Should not create an op
        ops = store.get_ops_for_thread("test-thread-missing")
        assert len(ops) == 0
