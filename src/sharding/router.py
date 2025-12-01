"""Cross-shard message routing."""

from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
import logging

from .topology import ShardTopology, ShardRegistry

logger = logging.getLogger(__name__)


@dataclass
class CrossShardDependency:
    """Represents a dependency between shards."""

    need_id: str
    from_shard: int
    to_shard: int
    artifact_refs: List[str] = field(default_factory=list)


class CrossShardRouter:
    """Routes messages across shards and tracks cross-shard dependencies."""

    def __init__(self, topology: ShardTopology, registry: ShardRegistry):
        """
        Initialize cross-shard router.

        Args:
            topology: ShardTopology instance
            registry: ShardRegistry instance
        """
        self.topology = topology
        self.registry = registry
        # Track cross-shard dependencies: need_id -> list of dependencies
        self.dependencies: Dict[str, List[CrossShardDependency]] = {}
        # Cache of shard endpoints: shard_id -> address
        self._endpoint_cache: Dict[int, str] = {}

    def route_to_shard(self, need_id: str, message: dict) -> tuple:
        """
        Route a message to the appropriate shard.

        Args:
            need_id: NEED identifier
            message: Message payload to route

        Returns:
            Tuple of (shard_id, endpoint_address)
        """
        # Determine target shard using consistent hashing
        shard_id = self.topology.get_shard_for_need(need_id)

        # Get endpoint for shard
        endpoint = self.get_shard_endpoint(shard_id)

        if endpoint is None:
            logger.error(f"No healthy endpoint found for shard {shard_id}")
            raise ValueError(f"Shard {shard_id} has no healthy nodes")

        logger.debug(f"Routing need {need_id} to shard {shard_id} at {endpoint}")

        return (shard_id, endpoint)

    def get_shard_endpoint(self, shard_id: int) -> Optional[str]:
        """
        Get network endpoint for a shard.

        Uses round-robin selection among healthy nodes in the shard.

        Args:
            shard_id: Shard identifier

        Returns:
            Network address of a healthy node, or None if no healthy nodes
        """
        # Check cache first
        if shard_id in self._endpoint_cache:
            # Verify cached endpoint is still healthy
            cached_addr = self._endpoint_cache[shard_id]
            healthy_nodes = self.registry.get_healthy_nodes(shard_id)
            if any(n.address == cached_addr for n in healthy_nodes):
                return cached_addr
            else:
                # Cache invalid, remove it
                del self._endpoint_cache[shard_id]

        # Get healthy nodes
        healthy_nodes = self.registry.get_healthy_nodes(shard_id)

        if not healthy_nodes:
            logger.warning(f"No healthy nodes available for shard {shard_id}")
            return None

        # Simple round-robin: pick first healthy node
        # (In production, could use more sophisticated load balancing)
        selected_node = healthy_nodes[0]

        # Cache the endpoint
        self._endpoint_cache[shard_id] = selected_node.address

        return selected_node.address

    def track_cross_shard_deps(self, need_id: str, dep_shard_ids: List[int]) -> None:
        """
        Track cross-shard dependencies for a NEED.

        Args:
            need_id: NEED identifier
            dep_shard_ids: List of shard IDs this NEED depends on
        """
        # Get source shard for this need
        source_shard = self.topology.get_shard_for_need(need_id)

        # Create dependency records
        dependencies = []
        for dep_shard in dep_shard_ids:
            if dep_shard != source_shard:  # Only track cross-shard deps
                dep = CrossShardDependency(
                    need_id=need_id,
                    from_shard=source_shard,
                    to_shard=dep_shard,
                    artifact_refs=[],
                )
                dependencies.append(dep)
                logger.debug(
                    f"Tracking cross-shard dependency: "
                    f"need {need_id} shard {source_shard} -> {dep_shard}"
                )

        # Store dependencies
        if dependencies:
            self.dependencies[need_id] = dependencies

    def get_dependencies(self, need_id: str) -> List[CrossShardDependency]:
        """
        Get cross-shard dependencies for a NEED.

        Args:
            need_id: NEED identifier

        Returns:
            List of CrossShardDependency objects
        """
        return self.dependencies.get(need_id, [])

    def add_dependency_artifact(
        self, need_id: str, dep_shard: int, artifact_ref: str
    ) -> None:
        """
        Add an artifact reference to a cross-shard dependency.

        Args:
            need_id: NEED identifier
            dep_shard: Dependency shard ID
            artifact_ref: Artifact hash reference
        """
        if need_id not in self.dependencies:
            logger.warning(
                f"No dependency tracked for need {need_id} -> shard {dep_shard}"
            )
            return

        # Find matching dependency
        for dep in self.dependencies[need_id]:
            if dep.to_shard == dep_shard:
                dep.artifact_refs.append(artifact_ref)
                logger.debug(
                    f"Added artifact {artifact_ref} to dependency "
                    f"{need_id} -> shard {dep_shard}"
                )
                break

    def clear_dependencies(self, need_id: str) -> None:
        """
        Clear dependency tracking for a completed NEED.

        Args:
            need_id: NEED identifier
        """
        if need_id in self.dependencies:
            del self.dependencies[need_id]
            logger.debug(f"Cleared dependencies for need {need_id}")

    def get_shards_with_capability(self, capability: str) -> List[int]:
        """
        Find all shards that have a specific capability.

        Args:
            capability: Capability string to search for

        Returns:
            List of shard IDs with this capability
        """
        matching_shards = []
        for shard_id in self.registry.get_all_shards():
            caps = self.registry.get_shard_capabilities(shard_id)
            if capability in caps:
                matching_shards.append(shard_id)
        return matching_shards

    def invalidate_endpoint_cache(self, shard_id: Optional[int] = None) -> None:
        """
        Invalidate endpoint cache.

        Args:
            shard_id: Specific shard to invalidate, or None for all
        """
        if shard_id is not None:
            if shard_id in self._endpoint_cache:
                del self._endpoint_cache[shard_id]
        else:
            self._endpoint_cache.clear()
