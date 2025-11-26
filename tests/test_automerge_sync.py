"""
Test Automerge Sync Protocol

Verifies:
- Full sync between two stores
- Incremental sync with changes only
- Three-way merge convergence
- Concurrent edits preservation
- Peer registration and tracking
"""

import pytest
import sys
from pathlib import Path
import time
import uuid

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from plan.automerge_store import AutomergePlanStore
from plan.sync_protocol import SyncManager, PeerState
from plan.peer_discovery import PeerDiscovery, PeerInfo
from plan_store import PlanOp, OpType, TaskState


def create_test_op(
    op_type: OpType,
    task_id: str,
    lamport: int,
    thread_id: str = "test-thread",
    actor_id: str = "test-actor",
    payload: dict = None
) -> PlanOp:
    """Helper to create test operations"""
    return PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=lamport,
        actor_id=actor_id,
        op_type=op_type,
        task_id=task_id,
        payload=payload or {},
        timestamp_ns=time.time_ns()
    )


class TestFullSync:
    """Test full synchronization between stores"""
    
    def test_full_sync_two_stores(self):
        """Two stores merge completely after full sync"""
        # Store A has task-1
        store_a = AutomergePlanStore()
        store_a.append_op(create_test_op(
            OpType.ADD_TASK, "task-1", 1,
            actor_id="peer-a",
            payload={"type": "build"}
        ))
        
        # Store B has task-2
        store_b = AutomergePlanStore()
        store_b.append_op(create_test_op(
            OpType.ADD_TASK, "task-2", 2,
            actor_id="peer-b",
            payload={"type": "test"}
        ))
        
        # Create sync managers
        sync_a = SyncManager(store_a, "peer-a")
        sync_b = SyncManager(store_b, "peer-b")
        
        # Register peers with callbacks
        sync_a.register_peer(
            "peer-b", "nats://peer-b",
            sync_callback=lambda _: store_b.get_save_data()
        )
        sync_b.register_peer(
            "peer-a", "nats://peer-a",
            sync_callback=lambda _: store_a.get_save_data()
        )
        
        # Sync A with B
        success = sync_a.sync_with_peer("peer-b")
        assert success is True
        
        # A should now have both tasks
        assert len(store_a.doc.tasks) == 2
        assert store_a.get_task("task-1") is not None
        assert store_a.get_task("task-2") is not None
    
    def test_full_sync_bidirectional(self):
        """Full sync works bidirectionally"""
        store_a = AutomergePlanStore()
        store_a.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        
        store_b = AutomergePlanStore()
        store_b.append_op(create_test_op(OpType.ADD_TASK, "task-2", 2))
        
        sync_a = SyncManager(store_a, "peer-a")
        sync_b = SyncManager(store_b, "peer-b")
        
        sync_a.register_peer("peer-b", "nats://peer-b",
                            lambda _: store_b.get_save_data())
        sync_b.register_peer("peer-a", "nats://peer-a",
                            lambda _: store_a.get_save_data())
        
        # Sync both ways
        sync_a.sync_with_peer("peer-b")
        sync_b.sync_with_peer("peer-a")
        
        # Both should have both tasks
        assert len(store_a.doc.tasks) == 2
        assert len(store_b.doc.tasks) == 2
        
        assert store_a.get_task("task-1") is not None
        assert store_a.get_task("task-2") is not None
        assert store_b.get_task("task-1") is not None
        assert store_b.get_task("task-2") is not None
    
    def test_sync_tracks_peer_state(self):
        """Sync manager tracks peer state correctly"""
        store_a = AutomergePlanStore()
        store_b = AutomergePlanStore()
        
        sync_a = SyncManager(store_a, "peer-a")
        sync_a.register_peer("peer-b", "nats://peer-b",
                            lambda _: store_b.get_save_data())
        
        # Check peer state before sync
        peer_state = sync_a.get_peer_state("peer-b")
        assert peer_state is not None
        assert peer_state.peer_id == "peer-b"
        assert peer_state.sync_state == "idle"
        assert peer_state.ops_synced == 0
        
        # Sync
        sync_a.sync_with_peer("peer-b")
        
        # Check peer state after sync
        peer_state = sync_a.get_peer_state("peer-b")
        assert peer_state.sync_state == "idle"
        assert peer_state.last_sync_ns > 0


class TestIncrementalSync:
    """Test incremental synchronization"""
    
    def test_incremental_sync_only_new_changes(self):
        """Incremental sync only sends new changes"""
        store_a = AutomergePlanStore()
        store_a.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        
        store_b = AutomergePlanStore()
        
        sync_a = SyncManager(store_a, "peer-a")
        
        # Register peer first
        sync_a.register_peer("peer-b", "nats://peer-b")
        
        # First sync - full
        peer_data = store_b.get_save_data()
        local_changes = sync_a.incremental_sync("peer-b", peer_data)
        
        assert local_changes is not None
        
        # Merge back to B
        store_b.load_from_data(local_changes)
        assert len(store_b.doc.tasks) == 1
        assert store_b.get_task("task-1") is not None


class TestThreeWayMerge:
    """Test three-way merge convergence"""
    
    def test_three_way_merge_convergence(self):
        """A, B, C all converge to same state"""
        # Create three stores with different tasks
        store_a = AutomergePlanStore()
        store_a.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        
        store_b = AutomergePlanStore()
        store_b.append_op(create_test_op(OpType.ADD_TASK, "task-2", 2))
        
        store_c = AutomergePlanStore()
        store_c.append_op(create_test_op(OpType.ADD_TASK, "task-3", 3))
        
        # Create sync managers
        sync_a = SyncManager(store_a, "peer-a")
        sync_b = SyncManager(store_b, "peer-b")
        sync_c = SyncManager(store_c, "peer-c")
        
        # Register all peers
        sync_a.register_peer("peer-b", "nats://peer-b", lambda _: store_b.get_save_data())
        sync_a.register_peer("peer-c", "nats://peer-c", lambda _: store_c.get_save_data())
        
        sync_b.register_peer("peer-a", "nats://peer-a", lambda _: store_a.get_save_data())
        sync_b.register_peer("peer-c", "nats://peer-c", lambda _: store_c.get_save_data())
        
        sync_c.register_peer("peer-a", "nats://peer-a", lambda _: store_a.get_save_data())
        sync_c.register_peer("peer-b", "nats://peer-b", lambda _: store_b.get_save_data())
        
        # Sync A with B and C
        sync_a.sync_all_peers()
        
        # Sync B with A and C
        sync_b.sync_all_peers()
        
        # Sync C with A and B
        sync_c.sync_all_peers()
        
        # All should have all 3 tasks
        assert len(store_a.doc.tasks) == 3
        assert len(store_b.doc.tasks) == 3
        assert len(store_c.doc.tasks) == 3
        
        # Verify all tasks present
        for store in [store_a, store_b, store_c]:
            assert store.get_task("task-1") is not None
            assert store.get_task("task-2") is not None
            assert store.get_task("task-3") is not None
    
    def test_three_way_state_convergence(self):
        """Three-way merge resolves to highest lamport"""
        # All start with same task
        store_a = AutomergePlanStore()
        store_a.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        
        store_b = AutomergePlanStore()
        store_b.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        
        store_c = AutomergePlanStore()
        store_c.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        
        # Each updates state with different lamport
        store_a.append_op(create_test_op(
            OpType.STATE, "task-1", 5,
            payload={"state": "DRAFT"}
        ))
        
        store_b.append_op(create_test_op(
            OpType.STATE, "task-1", 10,
            payload={"state": "DECIDED"}
        ))
        
        store_c.append_op(create_test_op(
            OpType.STATE, "task-1", 15,
            payload={"state": "VERIFIED"}
        ))
        
        # Merge all three
        store_a.merge_with_peer(store_b.get_save_data())
        store_a.merge_with_peer(store_c.get_save_data())
        
        store_b.merge_with_peer(store_a.get_save_data())
        store_c.merge_with_peer(store_a.get_save_data())
        
        # All should converge to highest lamport (VERIFIED)
        assert store_a.get_task("task-1")["state"] == "VERIFIED"
        assert store_b.get_task("task-1")["state"] == "VERIFIED"
        assert store_c.get_task("task-1")["state"] == "VERIFIED"


class TestConcurrentEdits:
    """Test concurrent edits are preserved"""
    
    def test_concurrent_edits_both_preserved(self):
        """Concurrent edits to different tasks are preserved"""
        # Both start with same tasks
        store_a = AutomergePlanStore()
        store_a.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        store_a.append_op(create_test_op(OpType.ADD_TASK, "task-2", 2))
        
        store_b = AutomergePlanStore()
        store_b.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        store_b.append_op(create_test_op(OpType.ADD_TASK, "task-2", 2))
        
        # A updates task-1
        store_a.append_op(create_test_op(
            OpType.STATE, "task-1", 10,
            payload={"state": "DECIDED"}
        ))
        
        # B updates task-2 (concurrent)
        store_b.append_op(create_test_op(
            OpType.STATE, "task-2", 11,
            payload={"state": "VERIFIED"}
        ))
        
        # Merge
        store_a.merge_with_peer(store_b.get_save_data())
        
        # Both edits should be preserved
        assert store_a.get_task("task-1")["state"] == "DECIDED"
        assert store_a.get_task("task-2")["state"] == "VERIFIED"
    
    def test_concurrent_annotations_lww(self):
        """Concurrent annotations use LWW"""
        store_a = AutomergePlanStore()
        store_a.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        
        store_b = AutomergePlanStore()
        store_b.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        
        # A annotates with lamport 5
        store_a.append_op(create_test_op(
            OpType.ANNOTATE, "task-1", 5,
            payload={"priority": "high", "owner": "alice"}
        ))
        
        # B annotates with lamport 10 (higher)
        store_b.append_op(create_test_op(
            OpType.ANNOTATE, "task-1", 10,
            payload={"priority": "critical"}
        ))
        
        # Merge
        store_a.merge_with_peer(store_b.get_save_data())
        
        # Higher lamport should win for priority
        task = store_a.get_task("task-1")
        assert task["annotations"]["priority"] == "critical"
        # Owner should still be from A (not overwritten)
        assert task["annotations"]["owner"] == "alice"


class TestPeerManagement:
    """Test peer registration and management"""
    
    def test_register_peer(self):
        """Can register peers"""
        store = AutomergePlanStore()
        sync = SyncManager(store, "peer-a")
        
        sync.register_peer("peer-b", "nats://peer-b")
        sync.register_peer("peer-c", "nats://peer-c")
        
        peers = sync.get_all_peers()
        assert len(peers) == 2
        assert "peer-b" in peers
        assert "peer-c" in peers
    
    def test_cannot_register_self(self):
        """Cannot register self as peer"""
        store = AutomergePlanStore()
        sync = SyncManager(store, "peer-a")
        
        sync.register_peer("peer-a", "nats://peer-a")
        
        # Should not be registered
        peers = sync.get_all_peers()
        assert len(peers) == 0
    
    def test_unregister_peer(self):
        """Can unregister peers"""
        store = AutomergePlanStore()
        sync = SyncManager(store, "peer-a")
        
        sync.register_peer("peer-b", "nats://peer-b")
        assert len(sync.get_all_peers()) == 1
        
        sync.unregister_peer("peer-b")
        assert len(sync.get_all_peers()) == 0
    
    def test_sync_status(self):
        """Can get sync status"""
        store = AutomergePlanStore()
        store.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        
        sync = SyncManager(store, "peer-a")
        sync.register_peer("peer-b", "nats://peer-b")
        
        status = sync.get_sync_status()
        
        assert status["local_peer_id"] == "peer-a"
        assert status["total_ops"] == 1
        assert status["total_tasks"] == 1
        assert status["total_peers"] == 1
        assert "peer-b" in status["peers"]


class TestPeerDiscovery:
    """Test peer discovery functionality"""
    
    def test_peer_discovery_initialization(self):
        """Can initialize peer discovery"""
        discovery = PeerDiscovery(
            "peer-a",
            "nats://peer-a",
            ["plan_sync", "consensus"]
        )
        
        assert discovery.local_peer_id == "peer-a"
        assert discovery.local_address == "nats://peer-a"
        assert "plan_sync" in discovery.capabilities
    
    def test_add_discovered_peer(self):
        """Can add discovered peers"""
        discovery = PeerDiscovery("peer-a", "nats://peer-a")
        
        peer_info = PeerInfo(
            peer_id="peer-b",
            address="nats://peer-b",
            capabilities=["plan_sync"]
        )
        
        discovery.add_discovered_peer(peer_info)
        
        peers = discovery.get_all_peers()
        assert len(peers) == 1
        assert peers[0].peer_id == "peer-b"
    
    def test_cannot_add_self_as_peer(self):
        """Cannot discover self as peer"""
        discovery = PeerDiscovery("peer-a", "nats://peer-a")
        
        peer_info = PeerInfo(
            peer_id="peer-a",  # Same as local
            address="nats://peer-a",
            capabilities=["plan_sync"]
        )
        
        discovery.add_discovered_peer(peer_info)
        
        # Should not be added
        peers = discovery.get_all_peers()
        assert len(peers) == 0
    
    def test_get_peers_with_capability(self):
        """Can filter peers by capability"""
        discovery = PeerDiscovery("peer-a", "nats://peer-a")
        
        discovery.add_discovered_peer(PeerInfo(
            "peer-b", "nats://peer-b", ["plan_sync"]
        ))
        discovery.add_discovered_peer(PeerInfo(
            "peer-c", "nats://peer-c", ["consensus"]
        ))
        discovery.add_discovered_peer(PeerInfo(
            "peer-d", "nats://peer-d", ["plan_sync", "consensus"]
        ))
        
        sync_peers = discovery.get_peers_with_capability("plan_sync")
        assert len(sync_peers) == 2
        
        consensus_peers = discovery.get_peers_with_capability("consensus")
        assert len(consensus_peers) == 2
    
    def test_discovery_status(self):
        """Can get discovery status"""
        discovery = PeerDiscovery("peer-a", "nats://peer-a", ["plan_sync"])
        discovery.add_discovered_peer(PeerInfo("peer-b", "nats://peer-b", ["plan_sync"]))
        
        status = discovery.get_discovery_status()
        
        assert status["local_peer_id"] == "peer-a"
        assert status["discovered_peers"] == 1
        assert "peer-b" in status["peers"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
