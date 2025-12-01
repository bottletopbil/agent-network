"""Tests for cross-shard dependencies and rollback."""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sharding.dependencies import (
    DependencyDAG,
    RollbackHandler,
)


class TestDependencyDAG:
    """Test dependency DAG operations."""

    def test_add_dependency(self):
        """Test adding dependencies."""
        dag = DependencyDAG()

        dag.add_dependency(from_shard=1, to_shard=0, need_id="need-123")

        assert len(dag.edges) == 1
        assert dag.graph[1] == {0}
        assert dag.reverse_graph[0] == {1}
        assert dag.in_degree[1] == 1
        assert dag.in_degree[0] == 0

    def test_get_ready_shards(self):
        """Test identifying ready shards."""
        dag = DependencyDAG()

        # Shard 0 has no dependencies - ready
        # Shard 1 depends on 0 - not ready
        # Shard 2 depends on 0 - not ready
        dag.add_dependency(1, 0, "need-1")
        dag.add_dependency(2, 0, "need-2")

        ready = dag.get_ready_shards()
        assert 0 in ready
        assert 1 not in ready
        assert 2 not in ready

    def test_mark_shard_complete(self):
        """Test marking shard complete and cascading."""
        dag = DependencyDAG()

        # Build dependency chain: 2 -> 1 -> 0
        dag.add_dependency(1, 0, "need-1")
        dag.add_dependency(2, 1, "need-2")

        # Initially only shard 0 is ready
        ready = dag.get_ready_shards()
        assert ready == [0]

        # Mark shard 0 complete
        newly_ready = dag.mark_shard_complete(0)
        assert 1 in newly_ready
        assert 2 not in newly_ready

        # Now shard 1 should be ready
        ready = dag.get_ready_shards()
        assert 1 in ready
        assert 2 not in ready

        # Mark shard 1 complete
        newly_ready = dag.mark_shard_complete(1)
        assert 2 in newly_ready

        # Now shard 2 should be ready
        ready = dag.get_ready_shards()
        assert 2 in ready

    def test_topo_sort_simple(self):
        """Test topological sort on simple DAG."""
        dag = DependencyDAG()

        # Build: 2 -> 1 -> 0
        dag.add_dependency(1, 0, "need-1")
        dag.add_dependency(2, 1, "need-2")

        sorted_shards = dag.topo_sort_shards()
        assert sorted_shards is not None

        # Verify ordering: 0 should come before 1, 1 before 2
        assert sorted_shards.index(0) < sorted_shards.index(1)
        assert sorted_shards.index(1) < sorted_shards.index(2)

    def test_topo_sort_complex(self):
        """Test topological sort on complex DAG."""
        dag = DependencyDAG()

        # Build diamond:
        #     0
        #    / \
        #   1   2
        #    \ /
        #     3
        dag.add_dependency(1, 0, "need-1")
        dag.add_dependency(2, 0, "need-2")
        dag.add_dependency(3, 1, "need-3a")
        dag.add_dependency(3, 2, "need-3b")

        sorted_shards = dag.topo_sort_shards()
        assert sorted_shards is not None

        # 0 must come first
        assert sorted_shards[0] == 0
        # 3 must come last
        assert sorted_shards[-1] == 3
        # 1 and 2 in middle (order doesn't matter)
        assert set(sorted_shards[1:3]) == {1, 2}

    def test_detect_deadlock_no_cycle(self):
        """Test deadlock detection with valid DAG."""
        dag = DependencyDAG()

        dag.add_dependency(1, 0, "need-1")
        dag.add_dependency(2, 1, "need-2")

        assert dag.detect_deadlock() is False

    def test_detect_deadlock_with_cycle(self):
        """Test deadlock detection with cycle."""
        dag = DependencyDAG()

        # Create cycle: 0 -> 1 -> 2 -> 0
        dag.add_dependency(1, 0, "need-1")
        dag.add_dependency(2, 1, "need-2")
        dag.add_dependency(0, 2, "need-3")

        assert dag.detect_deadlock() is True

    def test_find_cycles(self):
        """Test finding cycles in graph."""
        dag = DependencyDAG()

        # Create cycle: 0 -> 1 -> 0
        dag.add_dependency(1, 0, "need-1")
        dag.add_dependency(0, 1, "need-2")

        cycles = dag.find_cycles()
        assert len(cycles) > 0
        # Should find cycle containing 0 and 1
        assert any(set(cycle) == {0, 1} for cycle in cycles)

    def test_get_dependencies(self):
        """Test getting shard dependencies."""
        dag = DependencyDAG()

        dag.add_dependency(2, 0, "need-1")
        dag.add_dependency(2, 1, "need-2")

        deps = dag.get_dependencies(2)
        assert deps == {0, 1}

    def test_get_dependents(self):
        """Test getting dependent shards."""
        dag = DependencyDAG()

        dag.add_dependency(1, 0, "need-1")
        dag.add_dependency(2, 0, "need-2")

        dependents = dag.get_dependents(0)
        assert dependents == {1, 2}

    def test_get_blocking_shards(self):
        """Test identifying blocking shards."""
        dag = DependencyDAG()

        dag.add_dependency(2, 0, "need-1")
        dag.add_dependency(2, 1, "need-2")

        # Nothing completed yet, both block
        blocking = dag.get_blocking_shards(2)
        assert blocking == {0, 1}

        # Complete shard 0
        dag.mark_shard_complete(0)

        # Only shard 1 blocks now
        blocking = dag.get_blocking_shards(2)
        assert blocking == {1}

        # Complete shard 1
        dag.mark_shard_complete(1)

        # Nothing blocks
        blocking = dag.get_blocking_shards(2)
        assert blocking == set()

    def test_multiple_needs_same_dependency(self):
        """Test multiple NEEDs with same dependency structure."""
        dag = DependencyDAG()

        # Two different needs, same dependency structure
        dag.add_dependency(1, 0, "need-A")
        dag.add_dependency(1, 0, "need-B")

        # Should still be represented correctly
        assert dag.graph[1] == {0}
        assert dag.in_degree[1] == 2  # Both dependencies count


class TestRollbackHandler:
    """Test rollback handler."""

    def test_rollback_shard(self):
        """Test rolling back a shard."""
        handler = RollbackHandler()

        record = handler.rollback_shard(
            shard_id=1, reason="Timeout", artifact_refs=["hash-1", "hash-2"]
        )

        assert record.shard_id == 1
        assert record.reason == "Timeout"
        assert len(record.artifact_refs) == 2
        assert record.salvaged is False

        assert len(handler.rollback_history) == 1

    def test_rollback_history(self):
        """Test rollback history tracking."""
        handler = RollbackHandler()

        handler.rollback_shard(1, "Error A")
        handler.rollback_shard(2, "Error B")
        handler.rollback_shard(1, "Error C")

        # Get all history
        all_history = handler.get_rollback_history()
        assert len(all_history) == 3

        # Get history for shard 1
        shard_1_history = handler.get_rollback_history(shard_id=1)
        assert len(shard_1_history) == 2
        assert all(r.shard_id == 1 for r in shard_1_history)

    def test_salvage_partial_work(self):
        """Test salvaging partial work."""
        handler = RollbackHandler()

        # Rollback shard first
        handler.rollback_shard(
            shard_id=1,
            reason="Partial failure",
            artifact_refs=["hash-1", "hash-2", "hash-3"],
        )

        # Salvage some artifacts
        salvaged = handler.salvage_partial_work(shard_id=1, artifact_refs=["hash-1", "hash-2"])

        assert len(salvaged) == 2
        assert "hash-1" in salvaged
        assert "hash-2" in salvaged

        # Check salvaged artifacts stored
        stored = handler.get_salvaged_artifacts(1)
        assert stored == salvaged

        # Check rollback record marked as salvaged
        history = handler.get_rollback_history(shard_id=1)
        assert history[-1].salvaged is True

    def test_clear_history(self):
        """Test clearing rollback history."""
        handler = RollbackHandler()

        handler.rollback_shard(1, "Error")
        handler.salvage_partial_work(1, ["hash-1"])

        assert len(handler.rollback_history) > 0
        assert len(handler.salvaged_artifacts) > 0

        handler.clear_history()

        assert len(handler.rollback_history) == 0
        assert len(handler.salvaged_artifacts) == 0


class TestIntegration:
    """Integration tests for cross-shard coordination."""

    def test_complete_workflow_no_deadlock(self):
        """Test complete workflow without deadlocks."""
        dag = DependencyDAG()

        # Build workflow: shard 3 depends on 1 and 2, both depend on 0
        #     0
        #    / \
        #   1   2
        #    \ /
        #     3
        dag.add_dependency(1, 0, "need-main")
        dag.add_dependency(2, 0, "need-main")
        dag.add_dependency(3, 1, "need-main")
        dag.add_dependency(3, 2, "need-main")

        # Verify no deadlock
        assert dag.detect_deadlock() is False

        # Execute in order
        ready = dag.get_ready_shards()
        assert ready == [0]

        dag.mark_shard_complete(0)
        ready = dag.get_ready_shards()
        assert set(ready) == {1, 2}

        dag.mark_shard_complete(1)
        dag.mark_shard_complete(2)
        ready = dag.get_ready_shards()
        assert ready == [3]

    def test_rollback_with_salvage(self):
        """Test rollback workflow with salvage."""
        dag = DependencyDAG()
        handler = RollbackHandler()

        # Build simple workflow
        dag.add_dependency(1, 0, "need-main")
        dag.add_dependency(2, 1, "need-main")

        # Shard 0 completes
        dag.mark_shard_complete(0)

        # Shard 1 starts but fails
        handler.rollback_shard(
            shard_id=1, reason="Execution timeout", artifact_refs=["partial-result-1"]
        )

        # Try to salvage
        salvaged = handler.salvage_partial_work(1, ["partial-result-1"])
        assert len(salvaged) == 1

        # Shard 2 should still be blocked (shard 1 not completed)
        blocking = dag.get_blocking_shards(2)
        assert 1 in blocking

    def test_deadlock_detection_and_rollback(self):
        """Test detecting deadlock and rolling back."""
        dag = DependencyDAG()
        handler = RollbackHandler()

        # Accidentally create cycle
        dag.add_dependency(1, 0, "need-A")
        dag.add_dependency(2, 1, "need-B")
        dag.add_dependency(0, 2, "need-C")  # Creates cycle!

        # Detect deadlock
        assert dag.detect_deadlock() is True

        # Find the cycle
        cycles = dag.find_cycles()
        assert len(cycles) > 0

        # Rollback all shards involved
        for shard in {0, 1, 2}:
            handler.rollback_shard(shard, "Deadlock detected")

        assert len(handler.rollback_history) == 3
