"""
mDNS Peer Discovery

Provides multicast DNS-based peer discovery for local network.
"""

import socket
import logging
import time
import threading
from typing import Set, Callable, Optional

logger = logging.getLogger(__name__)


class MDNSDiscovery:
    """
    mDNS-based peer discovery for local network.
    
    Announces service via multicast DNS and discovers peers
    on the same local network.
    
    Note: Simplified implementation. Full mDNS would use zeroconf library.
    """
    
    SERVICE_TYPE = "_swarm._tcp.local"
    MULTICAST_GROUP = "224.0.0.251"
    MULTICAST_PORT = 5353
    
    def __init__(self, node_id: str, port: int = 4001):
        """
        Initialize mDNS discovery.
        
        Args:
            node_id: This node's peer ID
            port: P2P listen port
        """
        self.node_id = node_id
        self.port = port
        
        # Discovered peers: peer_id -> (host, port)
        self.peers: dict[str, tuple[str, int]] = {}
        
        # Discovery callbacks
        self.callbacks: list[Callable[[str, str, int], None]] = []
        
        # Running state
        self.running = False
        self.announce_thread = None
        self.listen_thread = None
        
        logger.info(f"mDNS discovery initialized for {node_id}")
    
    def start(self):
        """Start mDNS announcement and discovery"""
        if self.running:
            logger.warning("mDNS discovery already running")
            return
        
        self.running = True
        
        # Start announcement thread
        self.announce_thread = threading.Thread(
            target=self._announce_loop,
            daemon=True
        )
        self.announce_thread.start()
        
        # Start listener thread
        self.listen_thread = threading.Thread(
            target=self._listen_loop,
            daemon=True
        )
        self.listen_thread.start()
        
        logger.info("mDNS discovery started")
    
    def stop(self):
        """Stop mDNS discovery"""
        self.running = False
        
        if self.announce_thread:
            self.announce_thread.join(timeout=1.0)
        if self.listen_thread:
            self.listen_thread.join(timeout=1.0)
        
        logger.info("mDNS discovery stopped")
    
    def _announce_loop(self):
        """Periodically announce presence (simplified)"""
        while self.running:
            try:
                # In real mDNS, would send multicast DNS packets
                # For now, simulate announcement
                logger.debug(f"Announcing {self.node_id} on mDNS")
                
                # Wait before next announcement
                time.sleep(5.0)
                
            except Exception as e:
                logger.error(f"mDNS announce error: {e}")
    
    def _listen_loop(self):
        """Listen for peer announcements (simplified)"""
        while self.running:
            try:
                # In real mDNS, would listen for multicast packets
                # For now, simulate listening
                logger.debug("Listening for mDNS announcements")
                
                time.sleep(5.0)
                
            except Exception as e:
                logger.error(f"mDNS listen error: {e}")
    
    def announce_peer(self, peer_id: str, host: str, port: int):
        """
        Manually announce a discovered peer (for testing).
        
        Args:
            peer_id: Peer identifier
            host: Peer host address
            port: Peer port
        """
        if peer_id == self.node_id:
            return  # Don't discover self
        
        if peer_id not in self.peers:
            self.peers[peer_id] = (host, port)
            logger.info(f"Discovered peer via mDNS: {peer_id} at {host}:{port}")
            
            # Notify callbacks
            for callback in self.callbacks:
                try:
                    callback(peer_id, host, port)
                except Exception as e:
                    logger.error(f"mDNS callback error: {e}")
    
    def on_peer_discovered(self, callback: Callable[[str, str, int], None]):
        """
        Register callback for peer discovery.
        
        Args:
            callback: Function(peer_id, host, port)
        """
        self.callbacks.append(callback)
    
    def get_peers(self) -> dict[str, tuple[str, int]]:
        """Get all discovered peers"""
        return self.peers.copy()
    
    def get_peer_count(self) -> int:
        """Get number of discovered peers"""
        return len(self.peers)
