"""
Test Automerge-style CRDT Plan Store

Verifies:
- G-Set semantics for ops and edges
- Monotonic state updates (higher lamport wins)
- LWW (Last-Write-Wins) for annotations
- Save and load functionality
- Peer merging with deterministic state
"""

import pytest
import sys
from pathlib import Path
import time
import uuid

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from plan.automerge_store import AutomergePlanStore
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


class TestAddTask:
    """Test ADD_TASK operations"""
    
    def test_add_task(self):
        """Can add a task to the store"""
        store = AutomergePlanStore()
        
        op = create_test_op(
            op_type=OpType.ADD_TASK,
            task_id="task-1",
            lamport=1,
            payload={"type": "compile"}
        )
        
        store.append_op(op)
        
        task = store.get_task("task-1")
        assert task is not None
        assert task["task_id"] == "task-1"
        assert task["task_type"] == "compile"
        assert task["state"] == "DRAFT"
    
    def test_add_task_idempotent(self):
        """Adding same task twice is idempotent (G-Set)"""
        store = AutomergePlanStore()
        
        op = create_test_op(
            op_type=OpType.ADD_TASK,
            task_id="task-1",
            lamport=1,
            payload={"type": "compile"}
        )
        
        # Add same op twice
        store.append_op(op)
        store.append_op(op)
        
        # Should only appear once
        assert len(store.doc.ops) == 1
        assert "task-1" in store.doc.tasks
    
    def test_add_multiple_tasks(self):
        """Can add multiple different tasks"""
        store = AutomergePlanStore()
        
        op1 = create_test_op(OpType.ADD_TASK, "task-1", 1, payload={"type": "compile"})
        op2 = create_test_op(OpType.ADD_TASK, "task-2", 2, payload={"type": "test"})
        op3 = create_test_op(OpType.ADD_TASK, "task-3", 3, payload={"type": "deploy"})
        
        store.append_op(op1)
        store.append_op(op2)
        store.append_op(op3)
        
        assert len(store.doc.tasks) == 3
        assert store.get_task("task-1")["task_type"] == "compile"
        assert store.get_task("task-2")["task_type"] == "test"
        assert store.get_task("task-3")["task_type"] == "deploy"


class TestMonotonicState:
    """Test monotonic state updates (higher lamport wins)"""
    
    def test_monotonic_state_higher_lamport_wins(self):
        """State updates only apply if lamport is higher"""
        store = AutomergePlanStore()
        
        # Add task
        add_op = create_test_op(OpType.ADD_TASK, "task-1", 1)
        store.append_op(add_op)
        
        # Update to DECIDED (lamport 5)
        state_op1 = create_test_op(
            OpType.STATE, "task-1", 5,
            payload={"state": "DECIDED"}
        )
        store.append_op(state_op1)
        
        assert store.get_task("task-1")["state"] == "DECIDED"
        assert store.get_task("task-1")["last_lamport"] == 5
        
        # Try to update to DRAFT with lower lamport (3) - should be ignored
        state_op2 = create_test_op(
            OpType.STATE, "task-1", 3,
            payload={"state": "DRAFT"}
        )
        store.append_op(state_op2)
        
        # State should remain DECIDED (higher lamport wins)
        assert store.get_task("task-1")["state"] == "DECIDED"
        assert store.get_task("task-1")["last_lamport"] == 5
    
    def test_monotonic_state_equal_lamport_no_change(self):
        """Equal lamport doesn't update state"""
        store = AutomergePlanStore()
        
        add_op = create_test_op(OpType.ADD_TASK, "task-1", 1)
        store.append_op(add_op)
        
        state_op1 = create_test_op(OpType.STATE, "task-1", 5, payload={"state": "DECIDED"})
        store.append_op(state_op1)
        
        # Same lamport, different state
        state_op2 = create_test_op(OpType.STATE, "task-1", 5, payload={"state": "VERIFIED"})
        store.append_op(state_op2)
        
        # Original state should remain
        assert store.get_task("task-1")["state"] == "DECIDED"
    
    def test_monotonic_state_sequence(self):
        """State advances through monotonic sequence"""
        store = AutomergePlanStore()
        
        add_op = create_test_op(OpType.ADD_TASK, "task-1", 1)
        store.append_op(add_op)
        
        # Apply state changes in order
        states = [
            (2, "DRAFT"),
            (3, "DECIDED"),
            (4, "VERIFIED"),
            (5, "FINAL")
        ]
        
        for lamport, state in states:
            op = create_test_op(OpType.STATE, "task-1", lamport, payload={"state": state})
            store.append_op(op)
            assert store.get_task("task-1")["state"] == state
            assert store.get_task("task-1")["last_lamport"] == lamport


class TestLWWAnnotations:
    """Test Last-Write-Wins semantics for annotations"""
    
    def test_lww_annotations(self):
        """Annotations use LWW - higher lamport wins"""
        store = AutomergePlanStore()
        
        # Add task
        add_op = create_test_op(OpType.ADD_TASK, "task-1", 1)
        store.append_op(add_op)
        
        # Annotate with lamport 5
        annot_op1 = create_test_op(
            OpType.ANNOTATE, "task-1", 5,
            payload={"priority": "high", "owner": "alice"}
        )
        store.append_op(annot_op1)
        
        task = store.get_task("task-1")
        assert task["annotations"]["priority"] == "high"
        assert task["annotations"]["owner"] == "alice"
        
        # Update with higher lamport (10) - should win
        annot_op2 = create_test_op(
            OpType.ANNOTATE, "task-1", 10,
            payload={"priority": "critical"}
        )
        store.append_op(annot_op2)
        
        task = store.get_task("task-1")
        assert task["annotations"]["priority"] == "critical"  # Updated
        assert task["annotations"]["owner"] == "alice"  # Unchanged
    
    def test_lww_annotations_lower_lamport_ignored(self):
        """Lower lamport annotations are ignored"""
        store = AutomergePlanStore()
        
        add_op = create_test_op(OpType.ADD_TASK, "task-1", 1)
        store.append_op(add_op)
        
        # Annotate with lamport 10
        annot_op1 = create_test_op(
            OpType.ANNOTATE, "task-1", 10,
            payload={"status": "active"}
        )
        store.append_op(annot_op1)
        
        # Try to update with lower lamport (5) - should be ignored
        annot_op2 = create_test_op(
            OpType.ANNOTATE, "task-1", 5,
            payload={"status": "inactive"}
        )
        store.append_op(annot_op2)
        
        task = store.get_task("task-1")
        assert task["annotations"]["status"] == "active"  # Original value


class TestSaveAndLoad:
    """Test save and load functionality"""
    
    def test_save_and_load(self):
        """Can save and load document"""
        store1 = AutomergePlanStore()
        
        # Add some data
        op1 = create_test_op(OpType.ADD_TASK, "task-1", 1, payload={"type": "build"})
        op2 = create_test_op(OpType.STATE, "task-1", 2, payload={"state": "DECIDED"})
        op3 = create_test_op(OpType.ANNOTATE, "task-1", 3, payload={"priority": "high"})
        
        store1.append_op(op1)
        store1.append_op(op2)
        store1.append_op(op3)
        
        # Save
        data = store1.get_save_data()
        assert isinstance(data, bytes)
        assert len(data) > 0
        
        # Load into new store
        store2 = AutomergePlanStore()
        store2.load_from_data(data)
        
        # Verify data matches
        task1 = store1.get_task("task-1")
        task2 = store2.get_task("task-1")
        
        assert task1 == task2
        assert task2["task_type"] == "build"
        assert task2["state"] == "DECIDED"
        assert task2["annotations"]["priority"] == "high"
    
    def test_save_preserves_ops(self):
        """Saved document preserves all ops"""
        store1 = AutomergePlanStore()
        
        ops = [
            create_test_op(OpType.ADD_TASK, f"task-{i}", i)
            for i in range(1, 6)
        ]
        
        for op in ops:
            store1.append_op(op)
        
        # Save and load
        data = store1.get_save_data()
        store2 = AutomergePlanStore()
        store2.load_from_data(data)
        
        # All ops should be preserved
        assert len(store2.doc.ops) == 5
        assert len(store2.doc.tasks) == 5


class TestMergePeers:
    """Test peer merging with CRDT semantics"""
    
    def test_merge_peers_both_tasks_appear(self):
        """After merge, tasks from both peers are present"""
        # Peer A adds task-1
        peer_a = AutomergePlanStore()
        op_a = create_test_op(
            OpType.ADD_TASK, "task-1", 1,
            thread_id="thread-a",
            payload={"type": "compile"}
        )
        peer_a.append_op(op_a)
        
        # Peer B adds task-2
        peer_b = AutomergePlanStore()
        op_b = create_test_op(
            OpType.ADD_TASK, "task-2", 2,
            thread_id="thread-b",
            payload={"type": "test"}
        )
        peer_b.append_op(op_b)
        
        # Merge B into A
        peer_b_data = peer_b.get_save_data()
        peer_a.merge_with_peer(peer_b_data)
        
        # Both tasks should be present
        assert len(peer_a.doc.tasks) == 2
        assert peer_a.get_task("task-1") is not None
        assert peer_a.get_task("task-2") is not None
        assert peer_a.get_task("task-1")["task_type"] == "compile"
        assert peer_a.get_task("task-2")["task_type"] == "test"
    
    def test_merge_peers_deterministic_state(self):
        """Merge produces deterministic state based on lamport clocks"""
        # Peer A: task-1 at DRAFT (lamport 5)
        peer_a = AutomergePlanStore()
        peer_a.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        peer_a.append_op(create_test_op(OpType.STATE, "task-1", 5, payload={"state": "DRAFT"}))
        
        # Peer B: task-1 at DECIDED (lamport 10)
        peer_b = AutomergePlanStore()
        peer_b.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        peer_b.append_op(create_test_op(OpType.STATE, "task-1", 10, payload={"state": "DECIDED"}))
        
        # Merge B into A
        peer_a.merge_with_peer(peer_b.get_save_data())
        
        # Higher lamport should win (DECIDED at lamport 10)
        assert peer_a.get_task("task-1")["state"] == "DECIDED"
        assert peer_a.get_task("task-1")["last_lamport"] == 10
    
    def test_merge_peers_edges_combined(self):
        """Edges from both peers are combined (G-Set union)"""
        # Peer A: task-1 -> task-2
        peer_a = AutomergePlanStore()
        peer_a.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        peer_a.append_op(create_test_op(OpType.ADD_TASK, "task-2", 2))
        peer_a.append_op(create_test_op(
            OpType.LINK, "task-1", 3,
            payload={"parent": "task-1", "child": "task-2"}
        ))
        
        # Peer B: task-1 -> task-3
        peer_b = AutomergePlanStore()
        peer_b.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        peer_b.append_op(create_test_op(OpType.ADD_TASK, "task-3", 4))
        peer_b.append_op(create_test_op(
            OpType.LINK, "task-1", 5,
            payload={"parent": "task-1", "child": "task-3"}
        ))
        
        # Merge
        peer_a.merge_with_peer(peer_b.get_save_data())
        
        # task-1 should have both children
        children = peer_a.get_edges("task-1")
        assert len(children) == 2
        assert "task-2" in children
        assert "task-3" in children
    
    def test_merge_peers_annotation_lww(self):
        """Annotations merge with LWW semantics"""
        # Peer A: priority = "high" (lamport 5)
        peer_a = AutomergePlanStore()
        peer_a.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        peer_a.append_op(create_test_op(
            OpType.ANNOTATE, "task-1", 5,
            payload={"priority": "high"}
        ))
        
        # Peer B: priority = "critical" (lamport 10)
        peer_b = AutomergePlanStore()
        peer_b.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        peer_b.append_op(create_test_op(
            OpType.ANNOTATE, "task-1", 10,
            payload={"priority": "critical"}
        ))
        
        # Merge
        peer_a.merge_with_peer(peer_b.get_save_data())
        
        # Higher lamport should win
        task = peer_a.get_task("task-1")
        assert task["annotations"]["priority"] == "critical"
    
    def test_merge_peers_idempotent(self):
        """Merging same peer multiple times is idempotent"""
        peer_a = AutomergePlanStore()
        peer_a.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        
        peer_b = AutomergePlanStore()
        peer_b.append_op(create_test_op(OpType.ADD_TASK, "task-2", 2))
        
        peer_b_data = peer_b.get_save_data()
        
        # Merge twice
        peer_a.merge_with_peer(peer_b_data)
        peer_a.merge_with_peer(peer_b_data)
        
        # Should still only have 2 tasks, 2 ops
        assert len(peer_a.doc.tasks) == 2
        assert len(peer_a.doc.ops) == 2


class TestGetOpsForThread:
    """Test retrieving ops for a specific thread"""
    
    def test_get_ops_for_thread(self):
        """Can retrieve ops for a specific thread"""
        store = AutomergePlanStore()
        
        # Add ops for different threads
        op1 = create_test_op(OpType.ADD_TASK, "task-1", 1, thread_id="thread-a")
        op2 = create_test_op(OpType.ADD_TASK, "task-2", 2, thread_id="thread-b")
        op3 = create_test_op(OpType.ADD_TASK, "task-3", 3, thread_id="thread-a")
        
        store.append_op(op1)
        store.append_op(op2)
        store.append_op(op3)
        
        # Get ops for thread-a
        thread_a_ops = store.get_ops_for_thread("thread-a")
        assert len(thread_a_ops) == 2
        assert thread_a_ops[0].task_id == "task-1"
        assert thread_a_ops[1].task_id == "task-3"
        
        # Get ops for thread-b
        thread_b_ops = store.get_ops_for_thread("thread-b")
        assert len(thread_b_ops) == 1
        assert thread_b_ops[0].task_id == "task-2"
    
    def test_get_ops_for_thread_ordered_by_lamport(self):
        """Ops are returned in lamport order"""
        store = AutomergePlanStore()
        
        # Add ops out of order
        ops = [
            create_test_op(OpType.ADD_TASK, "task-3", 30, thread_id="thread-1"),
            create_test_op(OpType.ADD_TASK, "task-1", 10, thread_id="thread-1"),
            create_test_op(OpType.ADD_TASK, "task-2", 20, thread_id="thread-1"),
        ]
        
        for op in ops:
            store.append_op(op)
        
        # Should be returned in lamport order
        thread_ops = store.get_ops_for_thread("thread-1")
        assert len(thread_ops) == 3
        assert thread_ops[0].lamport == 10
        assert thread_ops[1].lamport == 20
        assert thread_ops[2].lamport == 30


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
