"""Cross-shard dependency resolution and rollback handling.

This module provides dependency DAG management and rollback mechanisms
for cross-shard workflows, enabling detection of deadlocks and safe
rollback when coordination fails.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict, deque
import logging

logger = logging.getLogger(__name__)


@dataclass
class DependencyEdge:
    """Represents a dependency edge in the DAG."""

    from_shard: int
    to_shard: int
    need_id: str
    artifact_refs: List[str] = field(default_factory=list)


class DependencyDAG:
    """
    Directed Acyclic Graph for cross-shard dependencies.

    Tracks dependencies between shards for a workflow and provides
    topological sorting and deadlock detection.
    """

    def __init__(self):
        """Initialize empty dependency DAG."""
        # Adjacency list: from_shard -> list of to_shards
        self.graph: Dict[int, Set[int]] = defaultdict(set)

        # Reverse adjacency list for reverse traversal
        self.reverse_graph: Dict[int, Set[int]] = defaultdict(set)

        # Detailed edge information
        self.edges: List[DependencyEdge] = []

        # Track which shards are ready (have no pending dependencies)
        self.ready_shards: Set[int] = set()

        # Track which shards have been completed
        self.completed_shards: Set[int] = set()

        # In-degree count for topological sort
        self.in_degree: Dict[int, int] = defaultdict(int)

    def add_dependency(
        self,
        from_shard: int,
        to_shard: int,
        need_id: str,
        artifact_refs: Optional[List[str]] = None,
    ) -> None:
        """
        Add a dependency edge: from_shard depends on to_shard.

        Args:
            from_shard: Shard that depends on another
            to_shard: Shard that must complete first
            need_id: NEED this dependency is for
            artifact_refs: Optional artifact references
        """
        # Create edge
        edge = DependencyEdge(
            from_shard=from_shard,
            to_shard=to_shard,
            need_id=need_id,
            artifact_refs=artifact_refs or [],
        )
        self.edges.append(edge)

        # Update graph
        self.graph[from_shard].add(to_shard)
        self.reverse_graph[to_shard].add(from_shard)

        # Update in-degree
        self.in_degree[from_shard] += 1

        # Ensure to_shard exists in graph
        if to_shard not in self.graph:
            self.graph[to_shard] = set()
            self.in_degree[to_shard] = 0

        logger.debug(
            f"Added dependency: shard {from_shard} -> {to_shard} " f"for need {need_id}"
        )

    def mark_shard_complete(self, shard_id: int) -> Set[int]:
        """
        Mark a shard as completed and return newly ready shards.

        Args:
            shard_id: Shard that completed

        Returns:
            Set of shard IDs that became ready
        """
        self.completed_shards.add(shard_id)
        newly_ready = set()

        # Find shards that were waiting on this one
        for dependent_shard in self.reverse_graph.get(shard_id, set()):
            # Decrease in-degree
            self.in_degree[dependent_shard] -= 1

            # Check if now ready (no remaining dependencies)
            if self.in_degree[dependent_shard] == 0:
                if dependent_shard not in self.completed_shards:
                    self.ready_shards.add(dependent_shard)
                    newly_ready.add(dependent_shard)

        logger.debug(f"Shard {shard_id} completed, {len(newly_ready)} shards now ready")

        return newly_ready

    def get_ready_shards(self) -> List[int]:
        """
        Get list of shards that are ready to execute.

        A shard is ready if all its dependencies are completed.

        Returns:
            List of ready shard IDs
        """
        # Find shards with in-degree 0 that aren't completed
        ready = [
            shard
            for shard, degree in self.in_degree.items()
            if degree == 0 and shard not in self.completed_shards
        ]

        return ready

    def topo_sort_shards(self) -> Optional[List[int]]:
        """
        Perform topological sort on the dependency graph.

        Returns:
            Ordered list of shard IDs, or None if cycle detected
        """
        # Kahn's algorithm for topological sort
        # Note: graph[from_shard] contains shards that from_shard depends ON
        # So we need to process in reverse order (start with no dependencies)

        in_degree_copy = self.in_degree.copy()

        # Start with shards that have no dependencies
        queue = deque(
            [shard for shard in self.graph.keys() if in_degree_copy.get(shard, 0) == 0]
        )

        result = []

        while queue:
            shard = queue.popleft()
            result.append(shard)

            # For each shard that depends on this one (reverse graph)
            for dependent in self.reverse_graph.get(shard, set()):
                in_degree_copy[dependent] -= 1
                if in_degree_copy[dependent] == 0:
                    queue.append(dependent)

        # Check if all shards were processed (no cycle)
        if len(result) != len(self.graph):
            logger.warning("Cycle detected in dependency graph")
            return None

        return result

    def detect_deadlock(self) -> bool:
        """
        Detect if there's a deadlock (cycle) in the dependency graph.

        Returns:
            True if deadlock detected
        """
        return self.topo_sort_shards() is None

    def find_cycles(self) -> List[List[int]]:
        """
        Find all cycles in the dependency graph.

        Returns:
            List of cycles, each cycle is a list of shard IDs
        """
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(shard: int, path: List[int]) -> None:
            visited.add(shard)
            rec_stack.add(shard)
            path.append(shard)

            for neighbor in self.graph.get(shard, set()):
                if neighbor not in visited:
                    dfs(neighbor, path.copy())
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            rec_stack.remove(shard)

        for shard in self.graph.keys():
            if shard not in visited:
                dfs(shard, [])

        return cycles

    def get_dependencies(self, shard_id: int) -> Set[int]:
        """
        Get all shards that this shard depends on.

        Args:
            shard_id: Shard to query

        Returns:
            Set of shard IDs this shard depends on
        """
        return self.graph.get(shard_id, set()).copy()

    def get_dependents(self, shard_id: int) -> Set[int]:
        """
        Get all shards that depend on this shard.

        Args:
            shard_id: Shard to query

        Returns:
            Set of shard IDs that depend on this shard
        """
        return self.reverse_graph.get(shard_id, set()).copy()

    def get_blocking_shards(self, shard_id: int) -> Set[int]:
        """
        Get shards that are blocking this shard from executing.

        Args:
            shard_id: Shard to query

        Returns:
            Set of incomplete dependency shards
        """
        dependencies = self.get_dependencies(shard_id)
        return dependencies - self.completed_shards


@dataclass
class RollbackRecord:
    """Record of a rollback operation."""

    shard_id: int
    reason: str
    artifact_refs: List[str]
    salvaged: bool
    timestamp_ns: int


class RollbackHandler:
    """
    Handles rollback of failed cross-shard workflows.

    Provides mechanisms to rollback shards and salvage partial work
    when coordination fails.
    """

    def __init__(self):
        """Initialize rollback handler."""
        self.rollback_history: List[RollbackRecord] = []
        self.salvaged_artifacts: Dict[int, List[str]] = defaultdict(list)

    def rollback_shard(
        self, shard_id: int, reason: str, artifact_refs: Optional[List[str]] = None
    ) -> RollbackRecord:
        """
        Rollback a shard's work.

        Args:
            shard_id: Shard to rollback
            reason: Reason for rollback
            artifact_refs: Artifacts to invalidate

        Returns:
            RollbackRecord documenting the rollback
        """
        import time

        record = RollbackRecord(
            shard_id=shard_id,
            reason=reason,
            artifact_refs=artifact_refs or [],
            salvaged=False,
            timestamp_ns=int(time.time() * 1_000_000_000),
        )

        self.rollback_history.append(record)

        logger.warning(
            f"Rolled back shard {shard_id}: {reason} "
            f"({len(artifact_refs or [])} artifacts invalidated)"
        )

        return record

    def salvage_partial_work(
        self, shard_id: int, artifact_refs: List[str]
    ) -> List[str]:
        """
        Salvage partial work from a failed shard.

        Artifacts that passed validation can be salvaged and reused
        even if the overall workflow failed.

        Args:
            shard_id: Shard to salvage from
            artifact_refs: Artifacts to attempt salvage

        Returns:
            List of successfully salvaged artifact refs
        """
        salvaged = []

        for artifact_ref in artifact_refs:
            # In a real implementation, would validate artifact
            # For now, accept all as salvageable
            salvaged.append(artifact_ref)
            self.salvaged_artifacts[shard_id].append(artifact_ref)

        logger.info(f"Salvaged {len(salvaged)} artifacts from shard {shard_id}")

        # Mark last rollback as salvaged if exists
        for record in reversed(self.rollback_history):
            if record.shard_id == shard_id:
                record.salvaged = True
                break

        return salvaged

    def get_salvaged_artifacts(self, shard_id: int) -> List[str]:
        """
        Get salvaged artifacts for a shard.

        Args:
            shard_id: Shard identifier

        Returns:
            List of salvaged artifact refs
        """
        return self.salvaged_artifacts.get(shard_id, []).copy()

    def get_rollback_history(
        self, shard_id: Optional[int] = None
    ) -> List[RollbackRecord]:
        """
        Get rollback history.

        Args:
            shard_id: Optional shard filter

        Returns:
            List of rollback records
        """
        if shard_id is not None:
            return [r for r in self.rollback_history if r.shard_id == shard_id]
        return self.rollback_history.copy()

    def clear_history(self) -> None:
        """Clear rollback history and salvaged artifacts."""
        self.rollback_history.clear()
        self.salvaged_artifacts.clear()
        logger.debug("Cleared rollback history")
