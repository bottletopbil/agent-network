"""
Peer Discovery for Distributed Plan Store

Discovers and announces peers on the network for CRDT synchronization.
Uses NATS pub/sub for peer announcements and discovery.
"""

import json
import asyncio
import logging
import time
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class PeerInfo:
    """Information about a discovered peer"""
    peer_id: str
    address: str  # NATS address or endpoint
    capabilities: List[str]  # e.g., ["plan_sync", "consensus"]
    announced_at: int = 0  # Nanosecond timestamp
    last_seen: int = 0  # Nanosecond timestamp for heartbeat


class PeerDiscovery:
    """
    Discovers peers for plan synchronization via NATS.
    
    Protocol:
    - Peers announce themselves on "peers.announce"
    - Peers send heartbeats on "peers.heartbeat"
    - Discovery queries on "peers.query"
    """
    
    def __init__(
        self, 
        local_peer_id: str,
        local_address: str,
        capabilities: Optional[List[str]] = None,
        nats_client = None  # Optional NATS client for real network
    ):
        """
        Initialize peer discovery.
        
        Args:
            local_peer_id: This peer's ID
            local_address: This peer's network address
            capabilities: List of capabilities this peer supports
            nats_client: Optional NATS client for publishing/subscribing
        """
        self.local_peer_id = local_peer_id
        self.local_address = local_address
        self.capabilities = capabilities or ["plan_sync"]
        self.nats_client = nats_client
        
        self.discovered_peers: Dict[str, PeerInfo] = {}
        self.announcement_interval = 30  # Announce every 30 seconds
        self.peer_timeout = 90  # Remove peers not seen in 90 seconds
        
        logger.info(
            f"PeerDiscovery initialized: {local_peer_id} at {local_address}"
        )
    
    async def announce_self(self) -> None:
        """
        Announce this peer to the network.
        
        Broadcasts availability on NATS "peers.announce" subject.
        """
        announcement = {
            "peer_id": self.local_peer_id,
            "address": self.local_address,
            "capabilities": self.capabilities,
            "announced_at": time.time_ns()
        }
        
        if self.nats_client:
            try:
                await self.nats_client.publish(
                    "peers.announce",
                    json.dumps(announcement).encode()
                )
                logger.debug(f"Announced peer {self.local_peer_id}")
            except Exception as e:
                logger.error(f"Failed to announce peer: {e}")
        else:
            logger.debug(
                f"No NATS client - simulating announcement: {announcement}"
            )
    
    async def discover_peers(self) -> List[PeerInfo]:
        """
        Discover active peers on the network.
        
        Returns:
            List of discovered peer info (excluding self)
        """
        if self.nats_client:
            # Real implementation would subscribe to peers.announce
            # and collect responses
            try:
                # Query for peers
                await self.nats_client.publish(
                    "peers.query",
                    json.dumps({"from": self.local_peer_id}).encode()
                )
                
                # Wait briefly for responses
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Failed to discover peers: {e}")
        
        # Return discovered peers (excluding self)
        return [
            peer for peer in self.discovered_peers.values()
            if peer.peer_id != self.local_peer_id
        ]
    
    def add_discovered_peer(self, peer_info: PeerInfo) -> None:
        """
        Add or update a discovered peer.
        
        Args:
            peer_info: Peer information from announcement
        """
        if peer_info.peer_id == self.local_peer_id:
            return  # Don't add self
        
        peer_info.last_seen = time.time_ns()
        
        if peer_info.peer_id not in self.discovered_peers:
            logger.info(
                f"Discovered new peer: {peer_info.peer_id} at {peer_info.address}"
            )
        
        self.discovered_peers[peer_info.peer_id] = peer_info
    
    def handle_announcement(self, message_data: bytes) -> None:
        """
        Handle peer announcement message.
        
        Args:
            message_data: JSON-encoded peer announcement
        """
        try:
            data = json.loads(message_data.decode())
            
            peer_info = PeerInfo(
                peer_id=data["peer_id"],
                address=data["address"],
                capabilities=data.get("capabilities", []),
                announced_at=data.get("announced_at", time.time_ns())
            )
            
            self.add_discovered_peer(peer_info)
            
        except Exception as e:
            logger.error(f"Failed to handle announcement: {e}")
    
    def remove_stale_peers(self) -> List[str]:
        """
        Remove peers that haven't been seen recently.
        
        Returns:
            List of removed peer IDs
        """
        now = time.time_ns()
        timeout_ns = self.peer_timeout * 1_000_000_000  # Convert to nanoseconds
        
        stale_peers = [
            peer_id
            for peer_id, peer in self.discovered_peers.items()
            if (now - peer.last_seen) > timeout_ns
        ]
        
        for peer_id in stale_peers:
            logger.info(f"Removing stale peer: {peer_id}")
            del self.discovered_peers[peer_id]
        
        return stale_peers
    
    def get_peer(self, peer_id: str) -> Optional[PeerInfo]:
        """Get information about a specific peer"""
        return self.discovered_peers.get(peer_id)
    
    def get_all_peers(self) -> List[PeerInfo]:
        """Get all discovered peers"""
        return list(self.discovered_peers.values())
    
    def get_peers_with_capability(self, capability: str) -> List[PeerInfo]:
        """
        Get peers that have a specific capability.
        
        Args:
            capability: Capability to filter by (e.g., "plan_sync")
            
        Returns:
            List of peers with that capability
        """
        return [
            peer for peer in self.discovered_peers.values()
            if capability in peer.capabilities
        ]
    
    async def start_announcement_loop(self):
        """
        Start periodic peer announcements.
        
        Runs until cancelled - should be run as an asyncio task.
        """
        logger.info(
            f"Starting announcement loop (interval: {self.announcement_interval}s)"
        )
        
        while True:
            try:
                await self.announce_self()
                self.remove_stale_peers()
                await asyncio.sleep(self.announcement_interval)
            except asyncio.CancelledError:
                logger.info("Announcement loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in announcement loop: {e}")
                await asyncio.sleep(self.announcement_interval)
    
    def get_discovery_status(self) -> Dict:
        """
        Get current discovery status.
        
        Returns:
            Dict with discovery statistics
        """
        return {
            "local_peer_id": self.local_peer_id,
            "local_address": self.local_address,
            "local_capabilities": self.capabilities,
            "discovered_peers": len(self.discovered_peers),
            "peers": {
                peer.peer_id: {
                    "address": peer.address,
                    "capabilities": peer.capabilities,
                    "last_seen": peer.last_seen
                }
                for peer in self.discovered_peers.values()
            }
        }


# Singleton for easy access
_peer_discovery: Optional[PeerDiscovery] = None


def get_peer_discovery() -> Optional[PeerDiscovery]:
    """Get global peer discovery instance"""
    return _peer_discovery


def init_peer_discovery(
    peer_id: str,
    address: str,
    capabilities: Optional[List[str]] = None,
    nats_client = None
) -> PeerDiscovery:
    """
    Initialize global peer discovery.
    
    Args:
        peer_id: Local peer ID
        address: Local address
        capabilities: Optional capability list
        nats_client: Optional NATS client
        
    Returns:
        PeerDiscovery instance
    """
    global _peer_discovery
    _peer_discovery = PeerDiscovery(peer_id, address, capabilities, nats_client)
    return _peer_discovery
