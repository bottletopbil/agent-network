"""
Unit tests for Basic Negotiation Verbs (YIELD, RELEASE, UPDATE_PLAN).

Tests:
- YIELD handler: voluntary task release
- RELEASE handler: system-initiated lease expiration
- UPDATE_PLAN handler: collaborative plan updates
"""

import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from plan_store import PlanStore, OpType, TaskState
import handlers.yield_handler
import handlers.release
import handlers.update_plan


class TestYieldHandler:
    """Test YIELD handler for voluntary task release"""
    
    @pytest.mark.asyncio
    async def test_yield_release_task(self):
        """Verify YIELD releases task and updates state to DRAFT"""
        # Create temporary plan store
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        
        # Inject plan store into yield handler
        handlers.yield_handler.plan_store = store
        
        # Create YIELD envelope
        envelope = {
            "kind": "YIELD",
            "thread_id": "test-thread-yield",
            "lamport": 50,
            "sender_pk_b64": "worker-public-key",
            "payload": {
                "task_id": "task-123",
                "reason": "cannot_complete"
            }
        }
        
        # Handle YIELD
        await handlers.yield_handler.handle_yield(envelope)
        
        # Verify operations were created
        ops = store.get_ops_for_thread("test-thread-yield")
        assert len(ops) == 2  # ANNOTATE + STATE
        
        # Verify ANNOTATE op for yield
        annotate_op = ops[0]
        assert annotate_op.op_type == OpType.ANNOTATE
        assert annotate_op.thread_id == "test-thread-yield"
        assert annotate_op.lamport == 50
        assert annotate_op.actor_id == "worker-public-key"
        assert annotate_op.task_id == "task-123"
        
        # Verify yield payload
        assert annotate_op.payload["annotation_type"] == "yield"
        assert annotate_op.payload["yielder"] == "worker-public-key"
        assert annotate_op.payload["reason"] == "cannot_complete"
        assert "yielded_at" in annotate_op.payload
        assert annotate_op.payload["yielded_at"] > 0
        
        # Verify STATE op updated task to DRAFT
        state_op = ops[1]
        assert state_op.op_type == OpType.STATE
        assert state_op.task_id == "task-123"
        assert state_op.payload["state"] == TaskState.DRAFT.value
        assert state_op.lamport == 51  # lamport + 1
    
    @pytest.mark.asyncio
    async def test_yield_missing_task_id(self):
        """Verify YIELD handles missing task_id gracefully"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.yield_handler.plan_store = store
        
        envelope = {
            "kind": "YIELD",
            "thread_id": "test-thread-yield-2",
            "lamport": 10,
            "sender_pk_b64": "worker-key",
            "payload": {"reason": "test"}  # No task_id
        }
        
        # Should not crash
        await handlers.yield_handler.handle_yield(envelope)
        
        # Should not create any ops
        ops = store.get_ops_for_thread("test-thread-yield-2")
        assert len(ops) == 0
    
    @pytest.mark.asyncio
    async def test_yield_default_reason(self):
        """Verify YIELD uses default reason if not provided"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.yield_handler.plan_store = store
        
        envelope = {
            "kind": "YIELD",
            "thread_id": "test-thread-yield-3",
            "lamport": 20,
            "sender_pk_b64": "worker-key",
            "payload": {"task_id": "task-456"}  # No reason
        }
        
        await handlers.yield_handler.handle_yield(envelope)
        
        ops = store.get_ops_for_thread("test-thread-yield-3")
        assert len(ops) == 2
        assert ops[0].payload["reason"] == "voluntary_yield"


class TestReleaseHandler:
    """Test RELEASE handler for system-initiated lease expiration"""
    
    @pytest.mark.asyncio
    async def test_release_on_timeout(self):
        """Verify RELEASE expires lease and scavenges task on timeout"""
        # Create temporary plan store
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        
        # Inject plan store into release handler
        handlers.release.plan_store = store
        
        # Create RELEASE envelope with timeout reason
        envelope = {
            "kind": "RELEASE",
            "thread_id": "test-thread-release",
            "lamport": 100,
            "sender_pk_b64": "system-coordinator",
            "payload": {
                "task_id": "task-789",
                "lease_id": "lease-abc-123",
                "reason": "timeout"
            }
        }
        
        # Handle RELEASE
        await handlers.release.handle_release(envelope)
        
        # Verify operations were created
        ops = store.get_ops_for_thread("test-thread-release")
        assert len(ops) == 2  # ANNOTATE + STATE
        
        # Verify ANNOTATE op for release
        annotate_op = ops[0]
        assert annotate_op.op_type == OpType.ANNOTATE
        assert annotate_op.thread_id == "test-thread-release"
        assert annotate_op.lamport == 100
        assert annotate_op.task_id == "task-789"
        
        # Verify release payload
        assert annotate_op.payload["annotation_type"] == "release"
        assert annotate_op.payload["lease_id"] == "lease-abc-123"
        assert annotate_op.payload["reason"] == "timeout"
        assert annotate_op.payload["system_initiated"] is True
        assert "released_at" in annotate_op.payload
        assert annotate_op.payload["released_at"] > 0
        
        # Verify STATE op scavenged task to DRAFT
        state_op = ops[1]
        assert state_op.op_type == OpType.STATE
        assert state_op.task_id == "task-789"
        assert state_op.payload["state"] == TaskState.DRAFT.value
        assert state_op.lamport == 101  # lamport + 1
    
    @pytest.mark.asyncio
    async def test_release_on_heartbeat_miss(self):
        """Verify RELEASE handles heartbeat_miss reason"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.release.plan_store = store
        
        envelope = {
            "kind": "RELEASE",
            "thread_id": "test-thread-release-2",
            "lamport": 200,
            "sender_pk_b64": "system-coordinator",
            "payload": {
                "task_id": "task-456",
                "lease_id": "lease-def-456",
                "reason": "heartbeat_miss"
            }
        }
        
        await handlers.release.handle_release(envelope)
        
        ops = store.get_ops_for_thread("test-thread-release-2")
        assert len(ops) == 2
        assert ops[0].payload["reason"] == "heartbeat_miss"
    
    @pytest.mark.asyncio
    async def test_release_invalid_reason(self):
        """Verify RELEASE handles invalid reason gracefully"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.release.plan_store = store
        
        envelope = {
            "kind": "RELEASE",
            "thread_id": "test-thread-release-3",
            "lamport": 150,
            "sender_pk_b64": "system-coordinator",
            "payload": {
                "task_id": "task-xyz",
                "lease_id": "lease-xyz-789",
                "reason": "invalid_reason"
            }
        }
        
        await handlers.release.handle_release(envelope)
        
        ops = store.get_ops_for_thread("test-thread-release-3")
        assert len(ops) == 2
        # Should default to "timeout"
        assert ops[0].payload["reason"] == "timeout"
    
    @pytest.mark.asyncio
    async def test_release_missing_fields(self):
        """Verify RELEASE handles missing required fields"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.release.plan_store = store
        
        # Missing task_id
        envelope = {
            "kind": "RELEASE",
            "thread_id": "test-thread-release-4",
            "lamport": 10,
            "sender_pk_b64": "system-coordinator",
            "payload": {"lease_id": "lease-123", "reason": "timeout"}
        }
        
        await handlers.release.handle_release(envelope)
        ops = store.get_ops_for_thread("test-thread-release-4")
        assert len(ops) == 0  # Should not create ops
        
        # Missing lease_id
        envelope2 = {
            "kind": "RELEASE",
            "thread_id": "test-thread-release-5",
            "lamport": 20,
            "sender_pk_b64": "system-coordinator",
            "payload": {"task_id": "task-abc", "reason": "timeout"}
        }
        
        await handlers.release.handle_release(envelope2)
        ops = store.get_ops_for_thread("test-thread-release-5")
        assert len(ops) == 0  # Should not create ops


class TestUpdatePlanHandler:
    """Test UPDATE_PLAN handler for collaborative plan updates"""
    
    @pytest.mark.asyncio
    async def test_update_plan(self):
        """Verify UPDATE_PLAN applies operations to plan store"""
        # Create temporary plan store
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        
        # Inject plan store into update_plan handler
        handlers.update_plan.plan_store = store
        
        # Create UPDATE_PLAN envelope with multiple ops
        envelope = {
            "kind": "UPDATE_PLAN",
            "thread_id": "test-thread-update",
            "lamport": 300,
            "sender_pk_b64": "planner-public-key",
            "payload": {
                "ops": [
                    {
                        "op_type": "ADD_TASK",
                        "task_id": "task-new-1",
                        "payload": {"type": "worker", "description": "New task 1"}
                    },
                    {
                        "op_type": "ADD_TASK",
                        "task_id": "task-new-2",
                        "payload": {"type": "verifier", "description": "New task 2"}
                    },
                    {
                        "op_type": "LINK",
                        "task_id": "task-new-1",
                        "payload": {"parent": "task-new-1", "child": "task-new-2"}
                    }
                ]
            }
        }
        
        # Handle UPDATE_PLAN
        await handlers.update_plan.handle_update_plan(envelope)
        
        # Verify all ops were applied
        ops = store.get_ops_for_thread("test-thread-update")
        assert len(ops) == 3
        
        # Verify first op (ADD_TASK)
        op1 = ops[0]
        assert op1.op_type == OpType.ADD_TASK
        assert op1.task_id == "task-new-1"
        assert op1.lamport == 300
        assert op1.payload["type"] == "worker"
        assert op1.payload["description"] == "New task 1"
        
        # Verify second op (ADD_TASK)
        op2 = ops[1]
        assert op2.op_type == OpType.ADD_TASK
        assert op2.task_id == "task-new-2"
        assert op2.lamport == 301  # Incremented
        assert op2.payload["type"] == "verifier"
        
        # Verify third op (LINK)
        op3 = ops[2]
        assert op3.op_type == OpType.LINK
        assert op3.task_id == "task-new-1"
        assert op3.lamport == 302  # Incremented
        assert op3.payload["parent"] == "task-new-1"
        assert op3.payload["child"] == "task-new-2"
    
    @pytest.mark.asyncio
    async def test_update_plan_empty_ops(self):
        """Verify UPDATE_PLAN handles empty ops array"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.update_plan.plan_store = store
        
        envelope = {
            "kind": "UPDATE_PLAN",
            "thread_id": "test-thread-update-2",
            "lamport": 10,
            "sender_pk_b64": "planner-key",
            "payload": {"ops": []}
        }
        
        # Should not crash
        await handlers.update_plan.handle_update_plan(envelope)
        
        # Should not create any ops
        ops = store.get_ops_for_thread("test-thread-update-2")
        assert len(ops) == 0
    
    @pytest.mark.asyncio
    async def test_update_plan_invalid_ops(self):
        """Verify UPDATE_PLAN skips invalid operations"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.update_plan.plan_store = store
        
        envelope = {
            "kind": "UPDATE_PLAN",
            "thread_id": "test-thread-update-3",
            "lamport": 50,
            "sender_pk_b64": "planner-key",
            "payload": {
                "ops": [
                    {
                        "op_type": "ADD_TASK",
                        "task_id": "task-valid",
                        "payload": {"type": "worker"}
                    },
                    {
                        "op_type": "INVALID_TYPE",  # Invalid op_type
                        "task_id": "task-invalid",
                        "payload": {}
                    },
                    {
                        # Missing task_id
                        "op_type": "STATE",
                        "payload": {"state": "DRAFT"}
                    }
                ]
            }
        }
        
        await handlers.update_plan.handle_update_plan(envelope)
        
        # Should only create 1 valid op
        ops = store.get_ops_for_thread("test-thread-update-3")
        assert len(ops) == 1
        assert ops[0].task_id == "task-valid"
    
    @pytest.mark.asyncio
    async def test_update_plan_state_update(self):
        """Verify UPDATE_PLAN can update task states"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        handlers.update_plan.plan_store = store
        
        envelope = {
            "kind": "UPDATE_PLAN",
            "thread_id": "test-thread-update-4",
            "lamport": 100,
            "sender_pk_b64": "coordinator-key",
            "payload": {
                "ops": [
                    {
                        "op_type": "STATE",
                        "task_id": "task-123",
                        "payload": {"state": "DECIDED"}
                    }
                ]
            }
        }
        
        await handlers.update_plan.handle_update_plan(envelope)
        
        ops = store.get_ops_for_thread("test-thread-update-4")
        assert len(ops) == 1
        assert ops[0].op_type == OpType.STATE
        assert ops[0].payload["state"] == "DECIDED"
