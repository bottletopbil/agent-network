"""
Unit tests for PROPOSE and CLAIM handlers.

Tests:
- PROPOSE handler proposal storage
- CLAIM handler claim recording
"""

import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from plan_store import PlanStore, OpType
import handlers.propose
import handlers.claim


class TestProposeHandler:
    """Test PROPOSE handler proposal storage"""
    
    @pytest.mark.asyncio
    async def test_propose_handler(self):
        """Verify PROPOSE creates ANNOTATE op in plan store"""
        # Create temporary plan store
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        
        # Inject plan store into propose handler
        handlers.propose.plan_store = store
        
        # Create PROPOSE envelope
        envelope = {
            "kind": "PROPOSE",
            "thread_id": "test-thread",
            "lamport": 20,
            "sender_pk_b64": "planner-public-key",
            "payload": {
                "proposal_id": "prop-123",
                "need_id": "need-456",
                "plan": [
                    {"task_id": "task-1", "type": "worker"},
                    {"task_id": "task-2", "type": "verifier"}
                ],
                "metadata": {"version": "1.0"}
            }
        }
        
        # Handle PROPOSE
        await handlers.propose.handle_propose(envelope)
        
        # Verify proposal was stored
        ops = store.get_ops_for_thread("test-thread")
        assert len(ops) == 1
        
        op = ops[0]
        assert op.op_type == OpType.ANNOTATE
        assert op.thread_id == "test-thread"
        assert op.lamport == 20
        assert op.actor_id == "planner-public-key"
        assert op.task_id == "need-456"
        
        # Verify payload
        assert op.payload["annotation_type"] == "proposal"
        assert op.payload["proposal_id"] == "prop-123"
        assert op.payload["proposer"] == "planner-public-key"
        assert len(op.payload["plan"]) == 2
        assert op.payload["plan"][0]["task_id"] == "task-1"
        assert op.payload["metadata"]["version"] == "1.0"
    
    @pytest.mark.asyncio
    async def test_propose_generates_id(self):
        """Verify PROPOSE generates proposal_id if not provided"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.propose.plan_store = store
        
        envelope = {
            "kind": "PROPOSE",
            "thread_id": "test-thread-2",
            "lamport": 5,
            "sender_pk_b64": "proposer-key",
            "payload": {
                "plan": []  # No proposal_id
            }
        }
        
        await handlers.propose.handle_propose(envelope)
        
        ops = store.get_ops_for_thread("test-thread-2")
        assert len(ops) == 1
        assert "proposal_id" in ops[0].payload
        assert ops[0].payload["proposal_id"]  # Should be auto-generated


class TestClaimHandler:
    """Test CLAIM handler claim recording"""
    
    @pytest.mark.asyncio
    async def test_claim_handler(self):
        """Verify CLAIM records claim with metadata"""
        # Create temporary plan store
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        
        # Inject plan store into claim handler
        handlers.claim.plan_store = store
        
        # Create CLAIM envelope
        envelope = {
            "kind": "CLAIM",
            "thread_id": "test-thread",
            "lamport": 30,
            "sender_pk_b64": "worker-public-key",
            "payload": {
                "task_id": "task-789",
                "claim_id": "claim-abc",
                "lease_ttl": 600  # 10 minutes
            }
        }
        
        # Handle CLAIM
        await handlers.claim.handle_claim(envelope)
        
        # Verify claim was recorded
        ops = store.get_ops_for_thread("test-thread")
        assert len(ops) == 1
        
        op = ops[0]
        assert op.op_type == OpType.ANNOTATE
        assert op.thread_id == "test-thread"
        assert op.lamport == 30
        assert op.actor_id == "worker-public-key"
        assert op.task_id == "task-789"
        
        # Verify claim payload
        assert op.payload["annotation_type"] == "claim"
        assert op.payload["claim_id"] == "claim-abc"
        assert op.payload["claimer"] == "worker-public-key"
        assert op.payload["lease_ttl"] == 600
        assert "claimed_at" in op.payload
        assert op.payload["claimed_at"] > 0
    
    @pytest.mark.asyncio
    async def test_claim_default_ttl(self):
        """Verify CLAIM uses default TTL if not provided"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.claim.plan_store = store
        
        envelope = {
            "kind": "CLAIM",
            "thread_id": "test-thread-3",
            "lamport": 10,
            "sender_pk_b64": "claimer-key",
            "payload": {
                "task_id": "task-123"
                # No lease_ttl
            }
        }
        
        await handlers.claim.handle_claim(envelope)
        
        ops = store.get_ops_for_thread("test-thread-3")
        assert len(ops) == 1
        assert ops[0].payload["lease_ttl"] == 300  # Default 5 minutes
    
    @pytest.mark.asyncio
    async def test_claim_missing_task_id(self):
        """Verify CLAIM handles missing task_id gracefully"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.claim.plan_store = store
        
        envelope = {
            "kind": "CLAIM",
            "thread_id": "test-thread-4",
            "lamport": 15,
            "sender_pk_b64": "claimer-key",
            "payload": {}  # No task_id
        }
        
        # Should not crash
        await handlers.claim.handle_claim(envelope)
        
        # Should not create an op
        ops = store.get_ops_for_thread("test-thread-4")
        assert len(ops) == 0
