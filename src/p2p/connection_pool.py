"""
Connection Pool Management

Manages active peer connections with limits, timeouts, and quality control.
"""

import time
import logging
from typing import Dict, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Connection:
    """Represents a connection to a peer"""

    peer_id: str
    host: str
    port: int
    connected_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    messages_sent: int = 0
    messages_received: int = 0
    is_active: bool = True

    def get_connection_age(self) -> float:
        """Get connection age in seconds"""
        return time.time() - self.connected_at

    def get_idle_time(self) -> float:
        """Get time since last activity in seconds"""
        return time.time() - self.last_activity

    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = time.time()


class ConnectionPool:
    """
    Manages pool of peer connections.

    Enforces connection limits, handles timeouts, and rotates
    low-quality connections to maintain network health.
    """

    def __init__(
        self,
        max_connections: int = 100,
        connection_timeout: int = 30,
        target_peer_count: int = 50,
    ):
        """
        Initialize connection pool.

        Args:
            max_connections: Maximum simultaneous connections
            connection_timeout: Idle timeout in seconds
            target_peer_count: Target number of active connections
        """
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        self.target_peer_count = target_peer_count

        # Active connections: peer_id → Connection
        self.connections: Dict[str, Connection] = {}

        # Peer reputation (optional, injected)
        self.reputation = None

        logger.info(
            f"Connection pool initialized: max={max_connections}, "
            f"timeout={connection_timeout}s, target={target_peer_count}"
        )

    def set_reputation(self, reputation):
        """Set reputation tracker for quality-based rotation"""
        self.reputation = reputation

    def add_connection(
        self, peer_id: str, host: str, port: int
    ) -> Optional[Connection]:
        """
        Add connection to pool.

        Args:
            peer_id: Peer identifier
            host: Peer host
            port: Peer port

        Returns:
            Connection object or None if rejected
        """
        # Check if already connected
        if peer_id in self.connections:
            logger.debug(f"Already connected to {peer_id}")
            return self.connections[peer_id]

        # Check blacklist if reputation available
        if self.reputation and self.reputation.is_blacklisted(peer_id):
            logger.warning(f"Rejected blacklisted peer: {peer_id}")
            return None

        # Check if at capacity
        if len(self.connections) >= self.max_connections:
            # Try to evict low-quality connection
            if not self._evict_connection():
                logger.warning("Connection pool full, cannot add connection")
                return None

        # Create connection
        connection = Connection(peer_id=peer_id, host=host, port=port)
        self.connections[peer_id] = connection

        logger.info(f"Added connection: {peer_id} ({host}:{port})")

        return connection

    def get_connection(self, peer_id: str) -> Optional[Connection]:
        """
        Get connection by peer ID.

        Args:
            peer_id: Peer identifier

        Returns:
            Connection object or None
        """
        connection = self.connections.get(peer_id)

        if connection and connection.is_active:
            connection.update_activity()
            return connection

        return None

    def close_connection(self, peer_id: str) -> bool:
        """
        Close connection to peer.

        Args:
            peer_id: Peer to disconnect

        Returns:
            True if closed, False if not found
        """
        if peer_id not in self.connections:
            return False

        connection = self.connections[peer_id]
        connection.is_active = False

        del self.connections[peer_id]

        logger.info(f"Closed connection: {peer_id}")

        return True

    def maintain_connections(self):
        """
        Maintain connection pool health.

        - Remove timed-out connections
        - Rotate low-quality connections
        - Ensure target peer count
        """
        # Remove timed-out connections
        self._remove_timed_out()

        # Rotate low-quality if we have reputation data
        if self.reputation:
            self._rotate_low_quality()

    def _remove_timed_out(self):
        """Remove connections that have timed out"""
        time.time()
        timed_out = []

        for peer_id, connection in self.connections.items():
            idle_time = connection.get_idle_time()
            if idle_time > self.connection_timeout:
                timed_out.append(peer_id)

        for peer_id in timed_out:
            logger.info(f"Connection timed out: {peer_id}")
            self.close_connection(peer_id)

    def _rotate_low_quality(self):
        """Rotate connections to low-quality peers"""
        # Only rotate if above target
        if len(self.connections) <= self.target_peer_count:
            return

        # Find worst peers currently connected
        connected_peers = list(self.connections.keys())
        peer_scores = [
            (peer_id, self.reputation.get_score(peer_id)) for peer_id in connected_peers
        ]

        # Sort by score (worst first)
        peer_scores.sort(key=lambda x: x[1])

        # Disconnect worst peer if score is poor
        if peer_scores and peer_scores[0][1] < 0.5:
            worst_peer = peer_scores[0][0]
            logger.info(
                f"Rotating low-quality connection: {worst_peer} "
                f"(score: {peer_scores[0][1]:.2f})"
            )
            self.close_connection(worst_peer)

    def _evict_connection(self) -> bool:
        """
        Evict a connection to make room.

        Evicts worst-scoring or oldest idle connection.

        Returns:
            True if evicted, False if no candidates
        """
        if not self.connections:
            return False

        # If we have reputation, evict worst scoring
        if self.reputation:
            worst_peers = self.reputation.get_worst_peers(count=1)
            if worst_peers and worst_peers[0] in self.connections:
                logger.info(f"Evicting low-score peer: {worst_peers[0]}")
                self.close_connection(worst_peers[0])
                return True

        # Otherwise evict oldest idle connection
        idle_connections = [
            (peer_id, conn.get_idle_time())
            for peer_id, conn in self.connections.items()
        ]

        idle_connections.sort(key=lambda x: x[1], reverse=True)

        if idle_connections:
            oldest_peer = idle_connections[0][0]
            logger.info(f"Evicting idle peer: {oldest_peer}")
            self.close_connection(oldest_peer)
            return True

        return False

    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self.connections)

    def get_peer_ids(self) -> Set[str]:
        """Get set of connected peer IDs"""
        return set(self.connections.keys())

    def get_stats(self) -> Dict[str, any]:
        """Get connection pool statistics"""
        total_sent = sum(c.messages_sent for c in self.connections.values())
        total_received = sum(c.messages_received for c in self.connections.values())

        return {
            "active_connections": len(self.connections),
            "max_connections": self.max_connections,
            "target_peer_count": self.target_peer_count,
            "messages_sent": total_sent,
            "messages_received": total_received,
            "utilization": len(self.connections) / self.max_connections,
        }
