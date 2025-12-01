"""
DHT Peer Discovery

Provides distributed hash table-based peer discovery for wide-area network.
"""

import logging
import time
import hashlib
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class DHTDiscovery:
    """
    DHT-based peer discovery.

    Implements a simplified Kademlia-style DHT for peer discovery and
    content routing.

    Note: Simplified implementation. Full DHT would use libp2p-kad-dht.
    """

    def __init__(self, node_id: str, k_bucket_size: int = 20):
        """
        Initialize DHT discovery.

        Args:
            node_id: This node's peer ID
            k_bucket_size: Size of k-buckets (Kademlia parameter)
        """
        self.node_id = node_id
        self.k_bucket_size = k_bucket_size

        # Routing table: peer_id -> (host, port, last_seen)
        self.routing_table: Dict[str, Tuple[str, int, float]] = {}

        # DHT store: key -> value
        self.dht_store: Dict[str, any] = {}

        # Bootstrap nodes
        self.bootstrap_nodes: List[str] = []

        # Connected to DHT
        self.connected = False

        logger.info(f"DHT discovery initialized for {node_id}")

    def bootstrap(self, bootstrap_nodes: List[str]):
        """
        Bootstrap DHT from known nodes.

        Args:
            bootstrap_nodes: List of bootstrap node multiaddrs
        """
        self.bootstrap_nodes = bootstrap_nodes

        if not bootstrap_nodes:
            logger.warning("No bootstrap nodes provided")
            return

        logger.info(f"Bootstrapping DHT with {len(bootstrap_nodes)} nodes")

        # In real DHT, would connect to bootstrap nodes
        # and perform initial peer discovery

        # For now, mark as connected
        self.connected = True

        logger.info("DHT bootstrap complete")

    def announce(self, key: Optional[str] = None):
        """
        Announce self in DHT.

        Args:
            key: Optional custom key (default: use node_id)
        """
        if not self.connected:
            logger.warning("DHT not connected, cannot announce")
            return

        announce_key = key or self.node_id

        # Store announcement in DHT
        self.put(announce_key, {"peer_id": self.node_id, "announced_at": time.time()})

        logger.info(f"Announced in DHT with key: {announce_key}")

    def find_peer(self, peer_id: str) -> Optional[Tuple[str, int]]:
        """
        Find peer in DHT.

        Args:
            peer_id: Peer to find

        Returns:
            Tuple of (host, port) or None
        """
        # Check routing table first
        if peer_id in self.routing_table:
            host, port, _ = self.routing_table[peer_id]
            return (host, port)

        # Query DHT
        peer_info = self.get(peer_id)
        if peer_info:
            # Would extract host/port from peer_info
            # For now, return placeholder
            logger.info(f"Found peer {peer_id} in DHT")
            return ("127.0.0.1", 4001)

        logger.debug(f"Peer {peer_id} not found in DHT")
        return None

    def find_peers(self, limit: int = 10) -> List[str]:
        """
        Find random peers in DHT.

        Args:
            limit: Maximum number of peers to return

        Returns:
            List of peer IDs
        """
        # Return peers from routing table
        peers = list(self.routing_table.keys())[:limit]

        logger.debug(f"Found {len(peers)} peers in DHT")

        return peers

    def put(self, key: str, value: any):
        """
        Store value in DHT.

        Args:
            key: Storage key
            value: Value to store
        """
        self.dht_store[key] = value
        logger.debug(f"Stored in DHT: {key}")

    def get(self, key: str) -> Optional[any]:
        """
        Retrieve value from DHT.

        Args:
            key: Storage key

        Returns:
            Stored value or None
        """
        value = self.dht_store.get(key)

        if value:
            logger.debug(f"Retrieved from DHT: {key}")

        return value

    def add_peer(self, peer_id: str, host: str, port: int):
        """
        Add peer to routing table.

        Args:
            peer_id: Peer identifier
            host: Peer host
            port: Peer port
        """
        if peer_id == self.node_id:
            return  # Don't add self

        self.routing_table[peer_id] = (host, port, time.time())
        logger.info(f"Added peer to DHT routing table: {peer_id}")

    def get_routing_table_size(self) -> int:
        """Get number of peers in routing table"""
        return len(self.routing_table)

    def compute_distance(self, peer_id1: str, peer_id2: str) -> int:
        """
        Compute XOR distance between two peer IDs (Kademlia).

        Args:
            peer_id1: First peer ID
            peer_id2: Second peer ID

        Returns:
            XOR distance
        """
        # Simple hash-based distance
        hash1 = int(hashlib.sha256(peer_id1.encode()).hexdigest()[:16], 16)
        hash2 = int(hashlib.sha256(peer_id2.encode()).hexdigest()[:16], 16)

        return hash1 ^ hash2

    def find_closest_peers(self, target_id: str, k: int = 20) -> List[str]:
        """
        Find K closest peers to target ID.

        Args:
            target_id: Target peer ID
            k: Number of peers to return

        Returns:
            List of closest peer IDs
        """
        # Compute distances
        peers_with_distance = [
            (peer_id, self.compute_distance(peer_id, target_id))
            for peer_id in self.routing_table.keys()
        ]

        # Sort by distance
        peers_with_distance.sort(key=lambda x: x[1])

        # Return K closest
        closest = [peer_id for peer_id, _ in peers_with_distance[:k]]

        return closest

    def get_stats(self) -> Dict[str, any]:
        """Get DHT statistics"""
        return {
            "node_id": self.node_id,
            "connected": self.connected,
            "routing_table_size": len(self.routing_table),
            "dht_store_size": len(self.dht_store),
            "bootstrap_nodes": len(self.bootstrap_nodes),
        }
