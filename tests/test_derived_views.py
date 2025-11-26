"""
Test Derived Views & Query Interface

Verifies:
- Tasks by state filtering
- Ready tasks detection
- Graph traversal (parents/children/ancestors/descendants)
- Topological sorting
- Cycle detection
"""

import pytest
import sys
from pathlib import Path
import uuid
import time

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


class TestTasksByState:
    """Test filtering tasks by state"""
    
    def test_tasks_by_state(self):
        """Can filter tasks by state"""
        store = AutomergePlanStore()
        
        # Add tasks in different states
        store.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        store.append_op(create_test_op(OpType.ADD_TASK, "task-2", 2))
        store.append_op(create_test_op(OpType.ADD_TASK, "task-3", 3))
        
        store.append_op(create_test_op(OpType.STATE, "task-1", 4,
                                      payload={"state": "DECIDED"}))
        store.append_op(create_test_op(OpType.STATE, "task-2", 5,
                                      payload={"state": "DECIDED"}))
        store.append_op(create_test_op(OpType.STATE, "task-3", 6,
                                      payload={"state": "VERIFIED"}))
        
        # Query by state
        draft_tasks = store.task_view.get_tasks_by_state("DRAFT")
        decided_tasks = store.task_view.get_tasks_by_state("DECIDED")
        verified_tasks = store.task_view.get_tasks_by_state("VERIFIED")
        
        assert len(draft_tasks) == 0
        assert len(decided_tasks) == 2
        assert len(verified_tasks) == 1
        
        # Verify correct tasks
        decided_ids = {t["task_id"] for t in decided_tasks}
        assert "task-1" in decided_ids
        assert "task-2" in decided_ids
    
    def test_empty_state(self):
        """Querying non-existent state returns empty list"""
        store = AutomergePlanStore()
        store.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        
        final_tasks = store.task_view.get_tasks_by_state("FINAL")
        assert len(final_tasks) == 0


class TestReadyTasks:
    """Test ready task detection"""
    
    def test_ready_tasks_no_dependencies(self):
        """Tasks with no dependencies are ready"""
        store = AutomergePlanStore()
        
        # Add DRAFT tasks with no dependencies
        store.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        store.append_op(create_test_op(OpType.ADD_TASK, "task-2", 2))
        
        ready = store.task_view.get_ready_tasks(store.graph_view)
        
        assert len(ready) == 2
        ready_ids = {t["task_id"] for t in ready}
        assert "task-1" in ready_ids
        assert "task-2" in ready_ids
    
    def test_ready_tasks_with_finished_dependencies(self):
        """Tasks are ready when dependencies are finished"""
        store = AutomergePlanStore()
        
        # Create dependency: task-2 depends on task-1
        store.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        store.append_op(create_test_op(OpType.ADD_TASK, "task-2", 2))
        store.append_op(create_test_op(OpType.LINK, "task-1", 3,
                                      payload={"parent": "task-1", "child": "task-2"}))
        
        # task-1 is VERIFIED (finished), task-2 is DRAFT
        store.append_op(create_test_op(OpType.STATE, "task-1", 4,
                                      payload={"state": "VERIFIED"}))
        
        ready = store.task_view.get_ready_tasks(store.graph_view)
        
        # task-2 should be ready (dependency finished)
        assert len(ready) == 1
        assert ready[0]["task_id"] == "task-2"
    
    def test_not_ready_with_unfinished_dependencies(self):
        """Tasks not ready when dependencies are unfinished"""
        store = AutomergePlanStore()
        
        # Create dependency
        store.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        store.append_op(create_test_op(OpType.ADD_TASK, "task-2", 2))
        store.append_op(create_test_op(OpType.LINK, "task-1", 3,
                                      payload={"parent": "task-1", "child": "task-2"}))
        
        # task-1 is still DRAFT (unfinished)
        ready = store.task_view.get_ready_tasks(store.graph_view)
        
        # Only task-1 should be ready, not task-2
        assert len(ready) == 1
        assert ready[0]["task_id"] == "task-1"


class TestGraphTraversal:
    """Test graph traversal operations"""
    
    def test_get_children(self):
        """Can get direct children"""
        store = AutomergePlanStore()
        
        store.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        store.append_op(create_test_op(OpType.ADD_TASK, "task-2", 2))
        store.append_op(create_test_op(OpType.ADD_TASK, "task-3", 3))
        
        # task-1 has two children
        store.append_op(create_test_op(OpType.LINK, "task-1", 4,
                                      payload={"parent": "task-1", "child": "task-2"}))
        store.append_op(create_test_op(OpType.LINK, "task-1", 5,
                                      payload={"parent": "task-1", "child": "task-3"}))
        
        children = store.graph_view.get_children("task-1")
        
        assert len(children) == 2
        assert "task-2" in children
        assert "task-3" in children
    
    def test_get_parents(self):
        """Can get direct parents"""
        store = AutomergePlanStore()
        
        store.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        store.append_op(create_test_op(OpType.ADD_TASK, "task-2", 2))
        store.append_op(create_test_op(OpType.ADD_TASK, "task-3", 3))
        
        # task-3 has two parents
        store.append_op(create_test_op(OpType.LINK, "task-1", 4,
                                      payload={"parent": "task-1", "child": "task-3"}))
        store.append_op(create_test_op(OpType.LINK, "task-2", 5,
                                      payload={"parent": "task-2", "child": "task-3"}))
        
        parents = store.graph_view.get_parents("task-3")
        
        assert len(parents) == 2
        assert "task-1" in parents
        assert "task-2" in parents
    
    def test_get_ancestors(self):
        """Can get transitive ancestors"""
        store = AutomergePlanStore()
        
        # Create chain: 1 -> 2 -> 3 -> 4
        for i in range(1, 5):
            store.append_op(create_test_op(OpType.ADD_TASK, f"task-{i}", i))
        
        store.append_op(create_test_op(OpType.LINK, "task-1", 10,
                                      payload={"parent": "task-1", "child": "task-2"}))
        store.append_op(create_test_op(OpType.LINK, "task-2", 11,
                                      payload={"parent": "task-2", "child": "task-3"}))
        store.append_op(create_test_op(OpType.LINK, "task-3", 12,
                                      payload={"parent": "task-3", "child": "task-4"}))
        
        # Get all ancestors of task-4
        ancestors = store.graph_view.get_ancestors("task-4")
        
        assert len(ancestors) == 3
        assert "task-1" in ancestors
        assert "task-2" in ancestors
        assert "task-3" in ancestors
    
    def test_get_descendants(self):
        """Can get transitive descendants"""
        store = AutomergePlanStore()
        
        # Create chain: 1 -> 2 -> 3 -> 4
        for i in range(1, 5):
            store.append_op(create_test_op(OpType.ADD_TASK, f"task-{i}", i))
        
        store.append_op(create_test_op(OpType.LINK, "task-1", 10,
                                      payload={"parent": "task-1", "child": "task-2"}))
        store.append_op(create_test_op(OpType.LINK, "task-2", 11,
                                      payload={"parent": "task-2", "child": "task-3"}))
        store.append_op(create_test_op(OpType.LINK, "task-3", 12,
                                      payload={"parent": "task-3", "child": "task-4"}))
        
        # Get all descendants of task-1
        descendants = store.graph_view.get_descendants("task-1")
        
        assert len(descendants) == 3
        assert "task-2" in descendants
        assert "task-3" in descendants
        assert "task-4" in descendants


class TestTopologicalSort:
    """Test topological sorting"""
    
    def test_topological_sort_simple(self):
        """Can sort simple dependency chain"""
        store = AutomergePlanStore()
        
        # Create: 1 -> 2 -> 3
        store.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        store.append_op(create_test_op(OpType.ADD_TASK, "task-2", 2))
        store.append_op(create_test_op(OpType.ADD_TASK, "task-3", 3))
        
        store.append_op(create_test_op(OpType.LINK, "task-1", 4,
                                      payload={"parent": "task-1", "child": "task-2"}))
        store.append_op(create_test_op(OpType.LINK, "task-2", 5,
                                      payload={"parent": "task-2", "child": "task-3"}))
        
        task_ids = {"task-1", "task-2", "task-3"}
        sorted_tasks = store.graph_view.topological_sort(task_ids)
        
        # task-1 should come before task-2, task-2 before task-3
        idx1 = sorted_tasks.index("task-1")
        idx2 = sorted_tasks.index("task-2")
        idx3 = sorted_tasks.index("task-3")
        
        assert idx1 < idx2 < idx3
    
    def test_topological_sort_diamond(self):
        """Can sort diamond dependency pattern"""
        store = AutomergePlanStore()
        
        # Create diamond: 1 -> 2,3 -> 4
        for i in range(1, 5):
            store.append_op(create_test_op(OpType.ADD_TASK, f"task-{i}", i))
        
        store.append_op(create_test_op(OpType.LINK, "task-1", 10,
                                      payload={"parent": "task-1", "child": "task-2"}))
        store.append_op(create_test_op(OpType.LINK, "task-1", 11,
                                      payload={"parent": "task-1", "child": "task-3"}))
        store.append_op(create_test_op(OpType.LINK, "task-2", 12,
                                      payload={"parent": "task-2", "child": "task-4"}))
        store.append_op(create_test_op(OpType.LINK, "task-3", 13,
                                      payload={"parent": "task-3", "child": "task-4"}))
        
        task_ids = {"task-1", "task-2", "task-3", "task-4"}
        sorted_tasks = store.graph_view.topological_sort(task_ids)
        
        # task-1 should come first, task-4 should come last
        assert sorted_tasks[0] == "task-1"
        assert sorted_tasks[-1] == "task-4"
        
        # task-2 and task-3 should come before task-4
        idx2 = sorted_tasks.index("task-2")
        idx3 = sorted_tasks.index("task-3")
        idx4 = sorted_tasks.index("task-4")
        
        assert idx2 < idx4
        assert idx3 < idx4


class TestCycleDetection:
    """Test cycle detection"""
    
    def test_no_cycle(self):
        """Detects no cycles in DAG"""
        store = AutomergePlanStore()
        
        # Create simple chain (no cycle)
        store.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        store.append_op(create_test_op(OpType.ADD_TASK, "task-2", 2))
        store.append_op(create_test_op(OpType.LINK, "task-1", 3,
                                      payload={"parent": "task-1", "child": "task-2"}))
        
        cycles = store.graph_view.detect_cycles()
        
        assert len(cycles) == 0
    
    def test_simple_cycle(self):
        """Detects simple cycle"""
        store = AutomergePlanStore()
        
        # Create cycle: 1 -> 2 -> 3 -> 1
        for i in range(1, 4):
            store.append_op(create_test_op(OpType.ADD_TASK, f"task-{i}", i))
        
        store.append_op(create_test_op(OpType.LINK, "task-1", 4,
                                      payload={"parent": "task-1", "child": "task-2"}))
        store.append_op(create_test_op(OpType.LINK, "task-2", 5,
                                      payload={"parent": "task-2", "child": "task-3"}))
        store.append_op(create_test_op(OpType.LINK, "task-3", 6,
                                      payload={"parent": "task-3", "child": "task-1"}))
        
        cycles = store.graph_view.detect_cycles()
        
        assert len(cycles) > 0
        # Cycle should contain all three tasks
        cycle = cycles[0]
        assert "task-1" in cycle
        assert "task-2" in cycle
        assert "task-3" in cycle
    
    def test_topological_sort_fails_with_cycle(self):
        """Topological sort raises error on cycle"""
        store = AutomergePlanStore()
        
        # Create cycle
        store.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        store.append_op(create_test_op(OpType.ADD_TASK, "task-2", 2))
        store.append_op(create_test_op(OpType.LINK, "task-1", 3,
                                      payload={"parent": "task-1", "child": "task-2"}))
        store.append_op(create_test_op(OpType.LINK, "task-2", 4,
                                      payload={"parent": "task-2", "child": "task-1"}))
        
        task_ids = {"task-1", "task-2"}
        
        with pytest.raises(ValueError, match="cycle"):
            store.graph_view.topological_sort(task_ids)


class TestViewUpdates:
    """Test that views update correctly"""
    
    def test_views_update_after_ops(self):
        """Views reflect current state after ops"""
        store = AutomergePlanStore()
        
        # Add task
        store.append_op(create_test_op(OpType.ADD_TASK, "task-1", 1))
        
        # Should appear in DRAFT
        draft_tasks = store.task_view.get_tasks_by_state("DRAFT")
        assert len(draft_tasks) == 1
        
        # Change state
        store.append_op(create_test_op(OpType.STATE, "task-1", 2,
                                      payload={"state": "DECIDED"}))
        
        # Should now appear in DECIDED
        draft_tasks = store.task_view.get_tasks_by_state("DRAFT")
        decided_tasks = store.task_view.get_tasks_by_state("DECIDED")
        
        assert len(draft_tasks) == 0
        assert len(decided_tasks) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
