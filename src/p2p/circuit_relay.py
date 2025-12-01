"""
Circuit Relay Client

Enables NAT traversal using circuit relay for peers behind firewalls.
"""

import logging
from typing import Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RelayNode:
    """Represents a relay node"""

    peer_id: str
    multiaddr: str
    is_available: bool = True
    connections_relayed: int = 0


class CircuitRelayClient:
    """
    Circuit relay client for NAT traversal.

    Automatically uses relay nodes when direct connections fail,
    enabling connectivity for peers behind NAT/firewalls.
    """

    def __init__(self, enable_auto_relay: bool = True):
        """
        Initialize circuit relay client.

        Args:
            enable_auto_relay: Automatically use relay on connection failure
        """
        self.enable_auto_relay = enable_auto_relay

        # Known relay nodes
        self.relay_nodes: List[RelayNode] = []

        # Connections using relay: peer_id → relay_node_id
        self.relayed_connections: dict[str, str] = {}

        # Connection attempts
        self.direct_attempts = 0
        self.relay_attempts = 0
        self.successful_direct = 0
        self.successful_relay = 0

        logger.info(f"Circuit relay initialized (auto={enable_auto_relay})")

    def add_relay_node(self, peer_id: str, multiaddr: str):
        """
        Add a known relay node.

        Args:
            peer_id: Relay node peer ID
            multiaddr: Relay node multiaddr
        """
        relay = RelayNode(peer_id=peer_id, multiaddr=multiaddr)
        self.relay_nodes.append(relay)

        logger.info(f"Added relay node: {peer_id}")

    def connect_direct(self, peer_id: str, host: str, port: int) -> bool:
        """
        Attempt direct connection.

        Args:
            peer_id: Peer to connect to
            host: Peer host
            port: Peer port

        Returns:
            True if successful
        """
        self.direct_attempts += 1

        # In real implementation, would attempt actual connection
        # For now, simulate success/failure

        # Simulate: 70% success rate for direct connections
        import random

        success = random.random() < 0.7

        if success:
            self.successful_direct += 1
            logger.info(f"Direct connection successful: {peer_id}")
            return True
        else:
            logger.warning(f"Direct connection failed: {peer_id}")
            return False

    def connect_via_relay(self, peer_id: str) -> Optional[str]:
        """
        Connect to peer via relay.

        Args:
            peer_id: Peer to connect to

        Returns:
            Relay node ID if successful, None otherwise
        """
        if not self.enable_auto_relay:
            logger.debug("Auto-relay disabled")
            return None

        if not self.relay_nodes:
            logger.warning("No relay nodes available")
            return None

        self.relay_attempts += 1

        # Find available relay node
        available_relays = [r for r in self.relay_nodes if r.is_available]

        if not available_relays:
            logger.warning("No available relay nodes")
            return None

        # Use first available relay (could be more sophisticated)
        relay = available_relays[0]

        # In real implementation, would establish relay circuit
        # For now, simulate

        self.successful_relay += 1
        self.relayed_connections[peer_id] = relay.peer_id
        relay.connections_relayed += 1

        logger.info(f"Connected via relay: {peer_id} → {relay.peer_id}")

        return relay.peer_id

    def connect(self, peer_id: str, host: str, port: int) -> bool:
        """
        Connect to peer with automatic relay fallback.

        Args:
            peer_id: Peer to connect to
            host: Peer host
            port: Peer port

        Returns:
            True if connected (direct or relay)
        """
        # Try direct connection first
        if self.connect_direct(peer_id, host, port):
            return True

        # Fall back to relay if enabled
        if self.enable_auto_relay:
            logger.info(f"Trying relay for {peer_id}")
            relay_id = self.connect_via_relay(peer_id)
            return relay_id is not None

        return False

    def is_relayed(self, peer_id: str) -> bool:
        """Check if connection is relayed"""
        return peer_id in self.relayed_connections

    def get_relay_for_peer(self, peer_id: str) -> Optional[str]:
        """Get relay node ID for peer connection"""
        return self.relayed_connections.get(peer_id)

    def close_relay(self, peer_id: str):
        """Close relayed connection"""
        if peer_id in self.relayed_connections:
            relay_id = self.relayed_connections[peer_id]
            del self.relayed_connections[peer_id]

            logger.info(f"Closed relay connection: {peer_id} (via {relay_id})")

    def get_stats(self) -> dict:
        """Get relay statistics"""
        return {
            "relay_nodes": len(self.relay_nodes),
            "relayed_connections": len(self.relayed_connections),
            "direct_attempts": self.direct_attempts,
            "relay_attempts": self.relay_attempts,
            "successful_direct": self.successful_direct,
            "successful_relay": self.successful_relay,
            "direct_success_rate": (self.successful_direct / max(self.direct_attempts, 1)),
            "relay_success_rate": (self.successful_relay / max(self.relay_attempts, 1)),
            "auto_relay_enabled": self.enable_auto_relay,
        }
