"""
P2P Node Implementation

Provides libp2p-based peer-to-peer node for decentralized communication.
"""

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class P2PNode:
    """
    libp2p-based P2P node.

    Note: This is a simplified implementation since py-libp2p has complex
    async requirements. In production, would use full libp2p stack.

    For now, this provides the interface and basic functionality.
    """

    def __init__(
        self,
        listen_addr: str = "/ip4/0.0.0.0/tcp/4001",
        identity_path: Optional[Path] = None,
        enable_mdns: bool = True,
        enable_dht: bool = True,
    ):
        """
        Initialize P2P node.

        Args:
            listen_addr: Multiaddr to listen on
            identity_path: Optional path to identity file
            enable_mdns: Enable mDNS discovery
            enable_dht: Enable DHT discovery
        """
        self.listen_addr = listen_addr
        self.identity_path = identity_path or Path(".p2p/identity.json")

        # Load or create identity
        from p2p.identity import get_or_create_identity

        self.identity = get_or_create_identity(self.identity_path)

        # Node state
        self.is_running = False
        self.host = None

        # Parse listen address
        self._parse_listen_addr()

        # Discovery systems
        self.enable_mdns = enable_mdns
        self.enable_dht = enable_dht
        self.mdns = None
        self.dht = None

        # Discovered peers: peer_id -> (host, port)
        self.discovered_peers: dict[str, tuple[str, int]] = {}

        logger.info(f"P2P node initialized with peer ID: {self.get_peer_id()}")

    def _parse_listen_addr(self):
        """Parse multiaddr into host and port"""
        # Simple parsing for /ip4/{host}/tcp/{port} format
        parts = self.listen_addr.split("/")

        try:
            if len(parts) >= 5 and parts[1] == "ip4" and parts[3] == "tcp":
                self.listen_host = parts[2]
                self.listen_port = int(parts[4])
            else:
                # Default fallback
                self.listen_host = "0.0.0.0"
                self.listen_port = 4001
        except (ValueError, IndexError):
            self.listen_host = "0.0.0.0"
            self.listen_port = 4001

        logger.debug(f"Listen address parsed: {self.listen_host}:{self.listen_port}")

    def start(self):
        """
        Start the P2P node with discovery.
        """
        if self.is_running:
            logger.warning("P2P node already running")
            return

        logger.info(f"Starting P2P node on {self.listen_addr}")

        try:
            # Start node
            self.is_running = True

            # Start mDNS discovery
            if self.enable_mdns:
                from p2p.mdns_discovery import MDNSDiscovery

                self.mdns = MDNSDiscovery(self.get_peer_id(), self.listen_port)
                self.mdns.on_peer_discovered(self._on_peer_discovered)
                self.mdns.start()
                logger.info("mDNS discovery enabled")

            # Start DHT discovery
            if self.enable_dht:
                from p2p.dht_discovery import DHTDiscovery
                from p2p.bootstrap_nodes import get_bootstrap_nodes

                self.dht = DHTDiscovery(self.get_peer_id())
                bootstrap_nodes = get_bootstrap_nodes(include_local=True)
                self.dht.bootstrap(bootstrap_nodes)
                self.dht.announce()
                logger.info("DHT discovery enabled")

            logger.info(f"P2P node started successfully")
            logger.info(f"Peer ID:{self.get_peer_id()}")
            logger.info(f"DID:peer: {self.get_did_peer()}")
            logger.info(f"Listening on: {self.get_multiaddrs()}")

        except Exception as e:
            logger.error(f"Failed to start P2P node: {e}")
            raise

    def _on_peer_discovered(self, peer_id: str, host: str, port: int):
        """
        Callback when peer is discovered.

        Args:
            peer_id: Discovered peer ID
            host: Peer host
            port: Peer port
        """
        if peer_id == self.get_peer_id():
            return  # Ignore self

        self.discovered_peers[peer_id] = (host, port)

        # Add to DHT if enabled
        if self.dht:
            self.dht.add_peer(peer_id, host, port)

        logger.info(f"Discovered peer: {peer_id} at {host}:{port}")

    def get_discovered_peers(self) -> dict[str, tuple[str, int]]:
        """Get all discovered peers"""
        return self.discovered_peers.copy()

    def get_peer_count(self) -> int:
        """Get number of discovered peers"""
        return len(self.discovered_peers)

    def stop(self) -> None:
        """Stop the P2P node"""
        if not self.is_running:
            logger.warning("P2P node not running")
            return

        logger.info("Stopping P2P node")

        try:
            # Stop discovery systems
            if self.mdns:
                self.mdns.stop()
            if self.dht:
                # DHT cleanup if needed
                pass

            self.is_running = False
            self.host = None
            logger.info("P2P node stopped")

        except Exception as e:
            logger.error(f"Error stopping P2P node: {e}")
            raise

    def get_peer_id(self) -> str:
        """
        Get node's peer ID.

        Returns:
            Peer ID string
        """
        return self.identity.to_peer_id()

    def get_did_peer(self) -> str:
        """
        Get node's DID:peer identifier.

        Returns:
            DID:peer string
        """
        return self.identity.to_did_peer()

    def get_multiaddrs(self) -> List[str]:
        """
        Get list of multiaddrs the node is listening on.

        Returns:
            List of multiaddr strings
        """
        if not self.is_running:
            return []

        peer_id = self.get_peer_id()

        # Return listen addresses with peer ID
        addrs = [f"/ip4/{self.listen_host}/tcp/{self.listen_port}/p2p/{peer_id}"]

        # Add localhost variant if listening on 0.0.0.0
        if self.listen_host == "0.0.0.0":
            addrs.append(f"/ip4/127.0.0.1/tcp/{self.listen_port}/p2p/{peer_id}")

        return addrs

    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop()


# Async version (for future full libp2p integration)
class AsyncP2PNode:
    """
    Async version of P2P node for full libp2p integration.

    This would be used when integrating with py-libp2p's async APIs.
    """

    def __init__(self, listen_addr: str = "/ip4/0.0.0.0/tcp/4001"):
        self.listen_addr = listen_addr
        self.host = None
        self.identity = None

    async def start(self):
        """Start node asynchronously"""
        # Would use libp2p async APIs here

    async def stop(self):
        """Stop node asynchronously"""
