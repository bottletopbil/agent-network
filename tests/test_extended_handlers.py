"""
Unit tests for Extended Proposal & Claim Handlers.

Tests:
- PROPOSE_EXTENDED handler: ballot validation and patch validation
- CLAIM_EXTENDED handler: lease management and TTL validation
- ATTEST_PLAN handler: verifier attestation and K_plan threshold
"""

import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from plan_store import PlanStore, OpType
import handlers.propose_extended
import handlers.claim_extended
import handlers.attest_plan


class TestProposeExtended:
    """Test PROPOSE_EXTENDED handler with ballot and patch validation"""

    @pytest.mark.asyncio
    async def test_propose_with_ballot(self):
        """Verify PROPOSE_EXTENDED records proposal with ballot"""
        # Create temporary plan store
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)

        # Inject plan store
        handlers.propose_extended.plan_store = store

        # Clear ballot registry
        handlers.propose_extended._ballot_registry.clear()

        # Create PROPOSE_EXTENDED envelope
        envelope = {
            "kind": "PROPOSE_EXTENDED",
            "thread_id": "test-thread-propose-ext",
            "lamport": 100,
            "sender_pk_b64": "planner-public-key",
            "payload": {
                "need_id": "need-123",
                "proposal_id": "prop-ext-abc",
                "ballot": "ballot-unique-1",
                "patch": [
                    {
                        "op_type": "ADD_TASK",
                        "task_id": "task-new-1",
                        "payload": {"type": "worker"},
                    }
                ],
                "cost": 100,
                "eta": 3600,
            },
        }

        # Handle PROPOSE_EXTENDED
        await handlers.propose_extended.handle_propose_extended(envelope)

        # Verify proposal was stored
        ops = store.get_ops_for_thread("test-thread-propose-ext")
        assert len(ops) == 1

        op = ops[0]
        assert op.op_type == OpType.ANNOTATE
        assert op.task_id == "need-123"
        assert op.payload["annotation_type"] == "proposal_extended"
        assert op.payload["proposal_id"] == "prop-ext-abc"
        assert op.payload["ballot"] == "ballot-unique-1"
        assert op.payload["cost"] == 100
        assert op.payload["eta"] == 3600
        assert len(op.payload["patch"]) == 1
        assert op.payload["patch"][0]["op_type"] == "ADD_TASK"

    @pytest.mark.asyncio
    async def test_propose_duplicate_ballot(self):
        """Verify PROPOSE_EXTENDED rejects duplicate ballots per proposer"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.propose_extended.plan_store = store
        handlers.propose_extended._ballot_registry.clear()

        sender = "planner-key"

        # First proposal with ballot
        envelope1 = {
            "kind": "PROPOSE_EXTENDED",
            "thread_id": "test-thread-dup",
            "lamport": 10,
            "sender_pk_b64": sender,
            "payload": {
                "need_id": "need-456",
                "ballot": "ballot-dup",
                "patch": [{"op_type": "ADD_TASK", "task_id": "task-1", "payload": {}}],
                "cost": 50,
                "eta": 1800,
            },
        }

        await handlers.propose_extended.handle_propose_extended(envelope1)

        # Second proposal with same ballot from same sender (should fail)
        envelope2 = {
            "kind": "PROPOSE_EXTENDED",
            "thread_id": "test-thread-dup",
            "lamport": 20,
            "sender_pk_b64": sender,
            "payload": {
                "need_id": "need-789",
                "ballot": "ballot-dup",  # Same ballot
                "patch": [{"op_type": "ADD_TASK", "task_id": "task-2", "payload": {}}],
                "cost": 75,
                "eta": 2400,
            },
        }

        await handlers.propose_extended.handle_propose_extended(envelope2)

        # Should only have 1 op (first one)
        ops = store.get_ops_for_thread("test-thread-dup")
        assert len(ops) == 1
        assert ops[0].payload["proposal_id"] != "should_not_exist"

    @pytest.mark.asyncio
    async def test_propose_patch_validation(self):
        """Verify PROPOSE_EXTENDED validates patch operations"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.propose_extended.plan_store = store
        handlers.propose_extended._ballot_registry.clear()

        # Proposal with mixed valid/invalid patch ops
        envelope = {
            "kind": "PROPOSE_EXTENDED",
            "thread_id": "test-thread-patch",
            "lamport": 30,
            "sender_pk_b64": "planner-key",
            "payload": {
                "need_id": "need-patch",
                "ballot": "ballot-patch-1",
                "patch": [
                    {
                        "op_type": "ADD_TASK",
                        "task_id": "task-valid",
                        "payload": {"type": "worker"},
                    },
                    {
                        "op_type": "INVALID_OP",  # Invalid
                        "task_id": "task-invalid",
                        "payload": {},
                    },
                    {
                        "op_type": "STATE",
                        "task_id": "task-valid-2",
                        "payload": {"state": "DRAFT"},
                    },
                ],
                "cost": 25,
                "eta": 900,
            },
        }

        await handlers.propose_extended.handle_propose_extended(envelope)

        ops = store.get_ops_for_thread("test-thread-patch")
        assert len(ops) == 1

        # Should only have 2 valid ops in patch (invalid filtered out)
        assert len(ops[0].payload["patch"]) == 2
        assert ops[0].payload["patch"][0]["task_id"] == "task-valid"
        assert ops[0].payload["patch"][1]["task_id"] == "task-valid-2"

    @pytest.mark.asyncio
    async def test_propose_missing_fields(self):
        """Verify PROPOSE_EXTENDED handles missing required fields"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.propose_extended.plan_store = store
        handlers.propose_extended._ballot_registry.clear()

        # Missing need_id
        envelope1 = {
            "kind": "PROPOSE_EXTENDED",
            "thread_id": "test-thread-missing",
            "lamport": 10,
            "sender_pk_b64": "planner-key",
            "payload": {
                "ballot": "ballot-1",
                "patch": [{"op_type": "ADD_TASK", "task_id": "task-1", "payload": {}}],
            },
        }

        await handlers.propose_extended.handle_propose_extended(envelope1)
        assert len(store.get_ops_for_thread("test-thread-missing")) == 0

        # Missing ballot
        envelope2 = {
            "kind": "PROPOSE_EXTENDED",
            "thread_id": "test-thread-missing",
            "lamport": 20,
            "sender_pk_b64": "planner-key",
            "payload": {
                "need_id": "need-123",
                "patch": [{"op_type": "ADD_TASK", "task_id": "task-1", "payload": {}}],
            },
        }

        await handlers.propose_extended.handle_propose_extended(envelope2)
        assert len(store.get_ops_for_thread("test-thread-missing")) == 0

        # Empty patch
        envelope3 = {
            "kind": "PROPOSE_EXTENDED",
            "thread_id": "test-thread-missing",
            "lamport": 30,
            "sender_pk_b64": "planner-key",
            "payload": {"need_id": "need-123", "ballot": "ballot-2", "patch": []},
        }

        await handlers.propose_extended.handle_propose_extended(envelope3)
        assert len(store.get_ops_for_thread("test-thread-missing")) == 0


class TestClaimExtended:
    """Test CLAIM_EXTENDED handler with lease management"""

    @pytest.mark.asyncio
    async def test_claim_with_lease(self):
        """Verify CLAIM_EXTENDED creates lease record and updates state"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.claim_extended.plan_store = store
        handlers.claim_extended._lease_registry.clear()

        envelope = {
            "kind": "CLAIM_EXTENDED",
            "thread_id": "test-thread-claim-ext",
            "lamport": 200,
            "sender_pk_b64": "worker-public-key",
            "payload": {
                "task_id": "task-claim-123",
                "worker_id": "worker-id-abc",
                "lease_ttl": 300,
                "cost": 50,
                "eta": 1800,
                "heartbeat_interval": 30,
            },
        }

        await handlers.claim_extended.handle_claim_extended(envelope)

        # Verify ops created (ANNOTATE + STATE)
        ops = store.get_ops_for_thread("test-thread-claim-ext")
        assert len(ops) == 2

        # Verify ANNOTATE op
        annotate_op = ops[0]
        assert annotate_op.op_type == OpType.ANNOTATE
        assert annotate_op.payload["annotation_type"] == "claim_extended"
        assert "lease_id" in annotate_op.payload
        assert annotate_op.payload["worker_id"] == "worker-id-abc"
        assert annotate_op.payload["lease_ttl"] == 300
        assert annotate_op.payload["heartbeat_interval"] == 30
        assert annotate_op.payload["cost"] == 50
        assert annotate_op.payload["eta"] == 1800

        # Verify STATE op
        state_op = ops[1]
        assert state_op.op_type == OpType.STATE
        assert state_op.payload["state"] == "CLAIMED"
        assert state_op.task_id == "task-claim-123"

        # Verify lease record created
        lease_id = annotate_op.payload["lease_id"]
        lease = handlers.claim_extended.get_lease(lease_id)
        assert lease is not None
        assert lease["task_id"] == "task-claim-123"
        assert lease["worker_id"] == "worker-id-abc"
        assert lease["ttl"] == 300
        assert lease["heartbeat_interval"] == 30

    @pytest.mark.asyncio
    async def test_claim_ttl_validation(self):
        """Verify CLAIM_EXTENDED enforces minimum TTL"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.claim_extended.plan_store = store
        handlers.claim_extended._lease_registry.clear()

        # TTL below minimum (60s)
        envelope = {
            "kind": "CLAIM_EXTENDED",
            "thread_id": "test-thread-ttl",
            "lamport": 10,
            "sender_pk_b64": "worker-key",
            "payload": {
                "task_id": "task-123",
                "lease_ttl": 30,  # Below MIN_LEASE_TTL
                "heartbeat_interval": 10,
            },
        }

        await handlers.claim_extended.handle_claim_extended(envelope)

        # Should not create any ops
        ops = store.get_ops_for_thread("test-thread-ttl")
        assert len(ops) == 0
        assert len(handlers.claim_extended._lease_registry) == 0

    @pytest.mark.asyncio
    async def test_claim_heartbeat_interval(self):
        """Verify CLAIM_EXTENDED validates heartbeat interval"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.claim_extended.plan_store = store
        handlers.claim_extended._lease_registry.clear()

        # Heartbeat interval >= lease_ttl (invalid)
        envelope = {
            "kind": "CLAIM_EXTENDED",
            "thread_id": "test-thread-hb",
            "lamport": 20,
            "sender_pk_b64": "worker-key",
            "payload": {
                "task_id": "task-456",
                "lease_ttl": 120,
                "heartbeat_interval": 120,  # Must be < lease_ttl
            },
        }

        await handlers.claim_extended.handle_claim_extended(envelope)

        # Should not create any ops
        ops = store.get_ops_for_thread("test-thread-hb")
        assert len(ops) == 0

    @pytest.mark.asyncio
    async def test_claim_missing_fields(self):
        """Verify CLAIM_EXTENDED handles missing required fields"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.claim_extended.plan_store = store
        handlers.claim_extended._lease_registry.clear()

        # Missing task_id
        envelope1 = {
            "kind": "CLAIM_EXTENDED",
            "thread_id": "test-thread-missing-claim",
            "lamport": 10,
            "sender_pk_b64": "worker-key",
            "payload": {"lease_ttl": 120},
        }

        await handlers.claim_extended.handle_claim_extended(envelope1)
        assert len(store.get_ops_for_thread("test-thread-missing-claim")) == 0

        # Missing lease_ttl
        envelope2 = {
            "kind": "CLAIM_EXTENDED",
            "thread_id": "test-thread-missing-claim",
            "lamport": 20,
            "sender_pk_b64": "worker-key",
            "payload": {"task_id": "task-789"},
        }

        await handlers.claim_extended.handle_claim_extended(envelope2)
        assert len(store.get_ops_for_thread("test-thread-missing-claim")) == 0


class TestAttestPlan:
    """Test ATTEST_PLAN handler with verifier validation"""

    @pytest.mark.asyncio
    async def test_attest_plan(self):
        """Verify ATTEST_PLAN records attestation"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.attest_plan.plan_store = store
        handlers.attest_plan._attestations.clear()

        # Set verifier_pool to None for this test (graceful degradation)
        handlers.attest_plan.verifier_pool = None

        envelope = {
            "kind": "ATTEST_PLAN",
            "thread_id": "test-thread-attest",
            "lamport": 300,
            "sender_pk_b64": "verifier-public-key",
            "payload": {
                "need_id": "need-123",
                "proposal_id": "prop-abc",
                "verdict": "approve",
            },
        }

        await handlers.attest_plan.handle_attest_plan(envelope)

        # Verify attestation recorded
        ops = store.get_ops_for_thread("test-thread-attest")
        assert len(ops) == 1

        op = ops[0]
        assert op.op_type == OpType.ANNOTATE
        assert op.payload["annotation_type"] == "attest_plan"
        assert op.payload["proposal_id"] == "prop-abc"
        assert op.payload["verifier"] == "verifier-public-key"
        assert op.payload["verdict"] == "approve"

        # Verify attestation tracked
        attestations = handlers.attest_plan.get_attestations("prop-abc")
        assert "verifier-public-key" in attestations
        assert attestations["verifier-public-key"] == "approve"

    @pytest.mark.asyncio
    async def test_attest_verdict_validation(self):
        """Verify ATTEST_PLAN validates verdict values"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.attest_plan.plan_store = store
        handlers.attest_plan._attestations.clear()
        handlers.attest_plan.verifier_pool = None

        # Invalid verdict
        envelope = {
            "kind": "ATTEST_PLAN",
            "thread_id": "test-thread-verdict",
            "lamport": 10,
            "sender_pk_b64": "verifier-key",
            "payload": {
                "need_id": "need-456",
                "proposal_id": "prop-def",
                "verdict": "invalid_verdict",
            },
        }

        await handlers.attest_plan.handle_attest_plan(envelope)

        # Should not create ops
        ops = store.get_ops_for_thread("test-thread-verdict")
        assert len(ops) == 0

    @pytest.mark.asyncio
    async def test_attest_k_plan_threshold(self):
        """Verify ATTEST_PLAN checks K_plan threshold"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.attest_plan.plan_store = store
        handlers.attest_plan._attestations.clear()
        handlers.attest_plan.verifier_pool = None

        proposal_id = "prop-threshold-test"

        # Submit K_PLAN approvals
        for i in range(handlers.attest_plan.K_PLAN):
            envelope = {
                "kind": "ATTEST_PLAN",
                "thread_id": "test-thread-k-plan",
                "lamport": 100 + i,
                "sender_pk_b64": f"verifier-{i}",
                "payload": {
                    "need_id": "need-threshold",
                    "proposal_id": proposal_id,
                    "verdict": "approve",
                },
            }

            await handlers.attest_plan.handle_attest_plan(envelope)

        # Verify K_PLAN ops created
        ops = store.get_ops_for_thread("test-thread-k-plan")
        assert len(ops) == handlers.attest_plan.K_PLAN

        # Verify approval count
        approval_count = handlers.attest_plan.get_approval_count(proposal_id)
        assert approval_count == handlers.attest_plan.K_PLAN

    @pytest.mark.asyncio
    async def test_attest_unique_verifiers(self):
        """Verify ATTEST_PLAN prevents duplicate votes"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.attest_plan.plan_store = store
        handlers.attest_plan._attestations.clear()
        handlers.attest_plan.verifier_pool = None

        verifier = "verifier-duplicate"
        proposal_id = "prop-dup-vote"

        # First attestation
        envelope1 = {
            "kind": "ATTEST_PLAN",
            "thread_id": "test-thread-dup-vote",
            "lamport": 10,
            "sender_pk_b64": verifier,
            "payload": {
                "need_id": "need-dup",
                "proposal_id": proposal_id,
                "verdict": "approve",
            },
        }

        await handlers.attest_plan.handle_attest_plan(envelope1)

        # Duplicate attestation from same verifier
        envelope2 = {
            "kind": "ATTEST_PLAN",
            "thread_id": "test-thread-dup-vote",
            "lamport": 20,
            "sender_pk_b64": verifier,
            "payload": {
                "need_id": "need-dup",
                "proposal_id": proposal_id,
                "verdict": "reject",  # Different verdict
            },
        }

        await handlers.attest_plan.handle_attest_plan(envelope2)

        # Should only have 1 op
        ops = store.get_ops_for_thread("test-thread-dup-vote")
        assert len(ops) == 1

        # Attestation should still be the first one
        attestations = handlers.attest_plan.get_attestations(proposal_id)
        assert attestations[verifier] == "approve"
