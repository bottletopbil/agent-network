"""
Unit tests for Lease Core Management.

Tests:
- LeaseManager: lease creation, renewal, expiry, queries
- HeartbeatProtocol: heartbeat tracking and miss detection
- HEARTBEAT handler: message processing and validation
"""

import sys
import os
import tempfile
from pathlib import Path
import time

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from leases.manager import LeaseManager, LeaseRecord
from leases.heartbeat import HeartbeatProtocol
from plan_store import PlanStore, OpType
import handlers.heartbeat


class TestLeaseManager:
    """Test LeaseManager functionality"""
    
    def test_lease_creation(self):
        """Verify lease creation with all fields"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        
        # Create lease
        lease_id = manager.create_lease(
            task_id="task-123",
            worker_id="worker-abc",
            ttl=300,
            heartbeat_interval=30
        )
        
        # Verify lease exists
        assert lease_id is not None
        lease = manager.get_lease(lease_id)
        assert lease is not None
        assert lease.task_id == "task-123"
        assert lease.worker_id == "worker-abc"
        assert lease.ttl == 300
        assert lease.heartbeat_interval == 30
        assert lease.created_at > 0
        assert lease.last_heartbeat == lease.created_at
    
    def test_lease_renewal(self):
        """Verify lease renewal updates created_at"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        
        # Create lease
        lease_id = manager.create_lease("task-456", "worker-xyz", 300, 30)
        original_lease = manager.get_lease(lease_id)
        
        # Wait a tiny bit
        time.sleep(0.01)
        
        # Renew lease
        success = manager.renew_lease(lease_id)
        assert success is True
        
        # Verify created_at and last_heartbeat updated
        renewed_lease = manager.get_lease(lease_id)
        assert renewed_lease.created_at > original_lease.created_at
        assert renewed_lease.last_heartbeat > original_lease.last_heartbeat
    
    def test_lease_renewal_nonexistent(self):
        """Verify renewal fails for nonexistent lease"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        
        success = manager.renew_lease("nonexistent-lease-id")
        assert success is False
    
    def test_heartbeat_updates(self):
        """Verify heartbeat updates last_heartbeat timestamp"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        
        # Create lease
        lease_id = manager.create_lease("task-789", "worker-123", 300, 30)
        original_lease = manager.get_lease(lease_id)
        
        # Wait a tiny bit
        time.sleep(0.01)
        
        # Send heartbeat
        success = manager.heartbeat(lease_id)
        assert success is True
        
        # Verify last_heartbeat updated
        updated_lease = manager.get_lease(lease_id)
        assert updated_lease.last_heartbeat > original_lease.last_heartbeat
        assert updated_lease.created_at == original_lease.created_at  # Should not change
    
    def test_heartbeat_nonexistent(self):
        """Verify heartbeat fails for nonexistent lease"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        
        success = manager.heartbeat("nonexistent-lease-id")
        assert success is False
    
    def test_lease_expiry_check(self):
        """Verify expiry detection for expired leases"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        
        # Create lease with very short TTL (1 nanosecond for testing)
        lease_id = manager.create_lease("task-exp", "worker-exp", ttl=0, heartbeat_interval=1)
        
        # Wait to ensure expiry
        time.sleep(0.01)
        
        # Check expiry
        expired = manager.check_expiry()
        assert lease_id in expired
    
    def test_lease_not_expired(self):
        """Verify non-expired leases not detected"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        
        # Create lease with long TTL
        lease_id = manager.create_lease("task-active", "worker-active", ttl=3600, heartbeat_interval=30)
        
        # Check expiry immediately
        expired = manager.check_expiry()
        assert lease_id not in expired
    
    def test_get_leases_for_worker(self):
        """Verify querying leases by worker_id"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        
        worker_id = "worker-multi"
        
        # Create multiple leases for same worker
        lease_id1 = manager.create_lease("task-1", worker_id, 300, 30)
        lease_id2 = manager.create_lease("task-2", worker_id, 300, 30)
        lease_id3 = manager.create_lease("task-3", "other-worker", 300, 30)
        
        # Query leases for worker
        leases = manager.get_leases_for_worker(worker_id)
        
        assert len(leases) == 2
        lease_ids = {lease.lease_id for lease in leases}
        assert lease_id1 in lease_ids
        assert lease_id2 in lease_ids
        assert lease_id3 not in lease_ids
    
    def test_get_nonexistent_lease(self):
        """Verify get_lease returns None for nonexistent lease"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        
        lease = manager.get_lease("nonexistent-id")
        assert lease is None
    
    def test_delete_lease(self):
        """Verify lease deletion"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        
        lease_id = manager.create_lease("task-del", "worker-del", 300, 30)
        
        # Verify exists
        assert manager.get_lease(lease_id) is not None
        
        # Delete
        success = manager.delete_lease(lease_id)
        assert success is True
        
        # Verify deleted
        assert manager.get_lease(lease_id) is None


class TestHeartbeatProtocol:
    """Test HeartbeatProtocol functionality"""
    
    def test_expect_heartbeat(self):
        """Verify heartbeat expectation setting"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        protocol = HeartbeatProtocol(manager)
        
        lease_id = manager.create_lease("task-hb", "worker-hb", 300, 30)
        
        # Set expectation
        protocol.expect_heartbeat(lease_id, 30)
        
        # Verify expectation set
        next_expected = protocol.get_next_expected_heartbeat(lease_id)
        assert next_expected is not None
        assert next_expected > time.time_ns()
    
    def test_receive_heartbeat(self):
        """Verify heartbeat reception updates expectation"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        protocol = HeartbeatProtocol(manager)
        
        lease_id = manager.create_lease("task-recv", "worker-recv", 300, 30)
        
        # Set initial expectation
        protocol.expect_heartbeat(lease_id, 30)
        first_expected = protocol.get_next_expected_heartbeat(lease_id)
        
        # Wait a bit
        time.sleep(0.01)
        
        # Receive heartbeat
        protocol.receive_heartbeat(lease_id)
        
        # Verify expectation updated
        second_expected = protocol.get_next_expected_heartbeat(lease_id)
        assert second_expected > first_expected
    
    def test_check_missed_heartbeats(self):
        """Verify missed heartbeat detection"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        protocol = HeartbeatProtocol(manager)
        
        lease_id = manager.create_lease("task-miss", "worker-miss", 300, 1)
        
        # Set expectation with very short interval
        protocol.expect_heartbeat(lease_id, 0)  # 0 seconds = immediate expiry
        
        # Wait to ensure miss
        time.sleep(0.01)
        
        # Check missed heartbeats
        missed = protocol.check_missed_heartbeats()
        assert lease_id in missed
    
    def test_no_missed_heartbeats(self):
        """Verify no missed heartbeats for active leases"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        protocol = HeartbeatProtocol(manager)
        
        lease_id = manager.create_lease("task-active-hb", "worker-active-hb", 300, 3600)
        
        # Set expectation with very long interval
        protocol.expect_heartbeat(lease_id, 3600)
        
        # Check missed heartbeats immediately
        missed = protocol.check_missed_heartbeats()
        assert lease_id not in missed
    
    def test_remove_expectation(self):
        """Verify expectation removal"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        protocol = HeartbeatProtocol(manager)
        
        lease_id = manager.create_lease("task-remove", "worker-remove", 300, 30)
        
        # Set expectation
        protocol.expect_heartbeat(lease_id, 30)
        assert protocol.get_next_expected_heartbeat(lease_id) is not None
        
        # Remove expectation
        protocol.remove_expectation(lease_id)
        assert protocol.get_next_expected_heartbeat(lease_id) is None


class TestHeartbeatHandler:
    """Test HEARTBEAT handler"""
    
    @pytest.mark.asyncio
    async def test_heartbeat_handler(self):
        """Verify HEARTBEAT handler processes messages"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        manager = LeaseManager(db_path)
        protocol = HeartbeatProtocol(manager)
        
        # Inject dependencies
        handlers.heartbeat.plan_store = store
        handlers.heartbeat.lease_manager = manager
        handlers.heartbeat.heartbeat_protocol = protocol
        
        # Create lease
        lease_id = manager.create_lease("task-hb-handler", "worker-hb-handler", 300, 30)
        
        # Set expectation
        protocol.expect_heartbeat(lease_id, 30)
        
        # Create HEARTBEAT envelope
        envelope = {
            "kind": "HEARTBEAT",
            "thread_id": "test-thread-hb",
            "lamport": 400,
            "sender_pk_b64": "worker-hb-handler",
            "payload": {
                "lease_id": lease_id,
                "worker_id": "worker-hb-handler",
                "progress": 50
            }
        }
        
        # Handle heartbeat
        await handlers.heartbeat.handle_heartbeat(envelope)
        
        # Verify op created
        ops = store.get_ops_for_thread("test-thread-hb")
        assert len(ops) == 1
        
        op = ops[0]
        assert op.op_type == OpType.ANNOTATE
        assert op.payload["annotation_type"] == "heartbeat"
        assert op.payload["lease_id"] == lease_id
        assert op.payload["worker_id"] == "worker-hb-handler"
        assert op.payload["progress"] == 50
        
        # Verify lease updated
        lease = manager.get_lease(lease_id)
        assert lease.last_heartbeat > lease.created_at
    
    @pytest.mark.asyncio
    async def test_heartbeat_invalid_lease(self):
        """Verify HEARTBEAT handler rejects invalid lease"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        manager = LeaseManager(db_path)
        
        handlers.heartbeat.plan_store = store
        handlers.heartbeat.lease_manager = manager
        handlers.heartbeat.heartbeat_protocol = None
        
        envelope = {
            "kind": "HEARTBEAT",
            "thread_id": "test-thread-invalid",
            "lamport": 10,
            "sender_pk_b64": "worker-key",
            "payload": {
                "lease_id": "nonexistent-lease",
                "worker_id": "worker-key"
            }
        }
        
        await handlers.heartbeat.handle_heartbeat(envelope)
        
        # Should not create ops
        ops = store.get_ops_for_thread("test-thread-invalid")
        assert len(ops) == 0
    
    @pytest.mark.asyncio
    async def test_heartbeat_worker_mismatch(self):
        """Verify HEARTBEAT handler rejects worker mismatch"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        manager = LeaseManager(db_path)
        
        handlers.heartbeat.plan_store = store
        handlers.heartbeat.lease_manager = manager
        handlers.heartbeat.heartbeat_protocol = None
        
        # Create lease for one worker
        lease_id = manager.create_lease("task-mismatch", "worker-correct", 300, 30)
        
        # Try heartbeat from different worker
        envelope = {
            "kind": "HEARTBEAT",
            "thread_id": "test-thread-mismatch",
            "lamport": 20,
            "sender_pk_b64": "worker-wrong",
            "payload": {
                "lease_id": lease_id,
                "worker_id": "worker-wrong"
            }
        }
        
        await handlers.heartbeat.handle_heartbeat(envelope)
        
        # Should not create ops
        ops = store.get_ops_for_thread("test-thread-mismatch")
        assert len(ops) == 0
    
    @pytest.mark.asyncio
    async def test_heartbeat_missing_fields(self):
        """Verify HEARTBEAT handler handles missing fields"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)
        
        handlers.heartbeat.plan_store = store
        handlers.heartbeat.lease_manager = None
        handlers.heartbeat.heartbeat_protocol = None
        
        # Missing lease_id
        envelope1 = {
            "kind": "HEARTBEAT",
            "thread_id": "test-thread-missing",
            "lamport": 10,
            "sender_pk_b64": "worker-key",
            "payload": {
                "worker_id": "worker-key"
            }
        }
        
        await handlers.heartbeat.handle_heartbeat(envelope1)
        assert len(store.get_ops_for_thread("test-thread-missing")) == 0
        
        # Missing worker_id
        envelope2 = {
            "kind": "HEARTBEAT",
            "thread_id": "test-thread-missing",
            "lamport": 20,
            "sender_pk_b64": "worker-key",
            "payload": {
                "lease_id": "some-lease"
            }
        }
        
        await handlers.heartbeat.handle_heartbeat(envelope2)
        assert len(store.get_ops_for_thread("test-thread-missing")) == 0
