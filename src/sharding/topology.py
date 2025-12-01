"""Shard topology and registry for distributed task assignment."""

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from datetime import datetime


@dataclass
class NodeInfo:
    """Information about a node in the shard."""

    node_id: str
    address: str
    capabilities: List[str]
    joined_at_ns: int
    last_heartbeat_ns: int

    def is_healthy(self, timeout_ns: int = 30_000_000_000) -> bool:
        """Check if node is healthy based on heartbeat."""
        now_ns = datetime.utcnow().timestamp() * 1_000_000_000
        return (now_ns - self.last_heartbeat_ns) < timeout_ns


class ShardTopology:
    """Manages shard assignment using consistent hashing."""

    def __init__(self, num_shards: int = 256):
        """
        Initialize shard topology.

        Args:
            num_shards: Number of shards (default 256 for balanced distribution)
        """
        self.num_shards = num_shards

    def get_shard_for_need(self, need_id: str) -> int:
        """
        Determine which shard handles a given NEED using consistent hashing.

        Args:
            need_id: The NEED identifier

        Returns:
            Shard ID (0 to num_shards-1)
        """
        # Use SHA256 for consistent hashing
        hash_digest = hashlib.sha256(need_id.encode("utf-8")).digest()
        # Convert first 4 bytes to integer
        hash_value = int.from_bytes(hash_digest[:4], byteorder="big")
        # Modulo to get shard ID
        return hash_value % self.num_shards

    def get_bucket_range(self, shard_id: int) -> tuple:
        """
        Get the hash bucket range for a shard.

        Args:
            shard_id: The shard identifier

        Returns:
            Tuple of (min_hash, max_hash) for this shard
        """
        bucket_size = (2**32) // self.num_shards
        min_hash = shard_id * bucket_size
        max_hash = (shard_id + 1) * bucket_size - 1
        return (min_hash, max_hash)


class ShardRegistry:
    """Registry of shards and their member nodes."""

    def __init__(self):
        """Initialize empty shard registry."""
        # Map: shard_id -> set of node_ids
        self.shard_map: Dict[int, Set[str]] = {}
        # Map: node_id -> NodeInfo
        self.nodes: Dict[str, NodeInfo] = {}
        # Map: shard_id -> capabilities
        self.shard_capabilities: Dict[int, Set[str]] = {}

    def register_shard(
        self, shard_id: int, node_id: str, address: str, capabilities: List[str]
    ) -> None:
        """
        Register a node as part of a shard.

        Args:
            shard_id: Shard identifier
            node_id: Node identifier
            address: Node network address
            capabilities: List of capabilities this node provides
        """
        now_ns = int(datetime.utcnow().timestamp() * 1_000_000_000)

        # Create or update node info
        if node_id in self.nodes:
            # Update existing node
            node = self.nodes[node_id]
            node.address = address
            node.capabilities = capabilities
            node.last_heartbeat_ns = now_ns
        else:
            # Create new node
            node = NodeInfo(
                node_id=node_id,
                address=address,
                capabilities=capabilities,
                joined_at_ns=now_ns,
                last_heartbeat_ns=now_ns,
            )
            self.nodes[node_id] = node

        # Add node to shard
        if shard_id not in self.shard_map:
            self.shard_map[shard_id] = set()
        self.shard_map[shard_id].add(node_id)

        # Update shard capabilities
        if shard_id not in self.shard_capabilities:
            self.shard_capabilities[shard_id] = set()
        self.shard_capabilities[shard_id].update(capabilities)

    def get_shard_nodes(self, shard_id: int) -> List[NodeInfo]:
        """
        Get all nodes in a shard.

        Args:
            shard_id: Shard identifier

        Returns:
            List of NodeInfo for nodes in this shard
        """
        if shard_id not in self.shard_map:
            return []

        node_ids = self.shard_map[shard_id]
        return [self.nodes[nid] for nid in node_ids if nid in self.nodes]

    def get_healthy_nodes(self, shard_id: int) -> List[NodeInfo]:
        """
        Get healthy nodes in a shard.

        Args:
            shard_id: Shard identifier

        Returns:
            List of healthy NodeInfo
        """
        nodes = self.get_shard_nodes(shard_id)
        return [n for n in nodes if n.is_healthy()]

    def health_check(self, shard_id: int) -> bool:
        """
        Check if a shard is healthy (has at least one healthy node).

        Args:
            shard_id: Shard identifier

        Returns:
            True if shard has at least one healthy node
        """
        healthy_nodes = self.get_healthy_nodes(shard_id)
        return len(healthy_nodes) > 0

    def update_heartbeat(self, node_id: str) -> None:
        """
        Update heartbeat timestamp for a node.

        Args:
            node_id: Node identifier
        """
        if node_id in self.nodes:
            now_ns = int(datetime.utcnow().timestamp() * 1_000_000_000)
            self.nodes[node_id].last_heartbeat_ns = now_ns

    def unregister_node(self, node_id: str) -> None:
        """
        Remove a node from the registry.

        Args:
            node_id: Node identifier
        """
        if node_id not in self.nodes:
            return

        # Remove from all shards
        for shard_id, node_ids in self.shard_map.items():
            if node_id in node_ids:
                node_ids.remove(node_id)

        # Remove node info
        del self.nodes[node_id]

    def get_shard_capabilities(self, shard_id: int) -> Set[str]:
        """
        Get all capabilities available in a shard.

        Args:
            shard_id: Shard identifier

        Returns:
            Set of capability strings
        """
        return self.shard_capabilities.get(shard_id, set())

    def get_all_shards(self) -> List[int]:
        """
        Get list of all registered shard IDs.

        Returns:
            List of shard IDs
        """
        return list(self.shard_map.keys())
