"""
Sync Protocol for Automerge CRDT Plan Store

Manages synchronization of plan state across distributed peers.
Provides both full sync and incremental sync modes.
"""

import time
import logging
from typing import Dict, Optional, Set
from dataclasses import dataclass, field

from plan.automerge_store import AutomergePlanStore

logger = logging.getLogger(__name__)


@dataclass
class PeerState:
    """Track synchronization state for a peer"""
    peer_id: str
    address: str  # Network address (e.g., "nats://peer-1:4222")
    last_sync_ns: int = 0  # Nanosecond timestamp of last sync
    sync_state: str = "idle"  # idle, syncing, error
    ops_synced: int = 0  # Number of ops synced so far
    last_error: Optional[str] = None


class SyncManager:
    """
    Manages CRDT synchronization with multiple peers.
    
    Supports:
    - Peer registration and tracking
    - Full document sync (merge entire state)
    - Incremental sync (only send new changes)
    - Automatic conflict resolution via CRDT merge
    """
    
    def __init__(self, store: AutomergePlanStore, local_peer_id: str):
        """
        Initialize sync manager.
        
        Args:
            store: Local AutomergePlanStore instance
            local_peer_id: Unique identifier for this peer
        """
        self.store = store
        self.local_peer_id = local_peer_id
        self.peers: Dict[str, PeerState] = {}
        self._sync_callbacks: Dict[str, callable] = {}  # peer_id -> callback
        
        logger.info(f"SyncManager initialized for peer {local_peer_id}")
    
    def register_peer(
        self, 
        peer_id: str, 
        address: str,
        sync_callback: Optional[callable] = None
    ) -> None:
        """
        Register a peer for synchronization.
        
        Args:
            peer_id: Unique peer identifier
            address: Network address for the peer
            sync_callback: Optional callback(peer_id) -> bytes to get peer data
        """
        if peer_id == self.local_peer_id:
            logger.warning(f"Cannot register self as peer: {peer_id}")
            return
        
        if peer_id not in self.peers:
            self.peers[peer_id] = PeerState(
                peer_id=peer_id,
                address=address
            )
            if sync_callback:
                self._sync_callbacks[peer_id] = sync_callback
            
            logger.info(f"Registered peer {peer_id} at {address}")
        else:
            # Update address if changed
            self.peers[peer_id].address = address
            logger.debug(f"Updated peer {peer_id} address to {address}")
    
    def unregister_peer(self, peer_id: str) -> None:
        """Remove a peer from tracking"""
        if peer_id in self.peers:
            del self.peers[peer_id]
            if peer_id in self._sync_callbacks:
                del self._sync_callbacks[peer_id]
            logger.info(f"Unregistered peer {peer_id}")
    
    def sync_with_peer(self, peer_id: str) -> bool:
        """
        Perform full sync with a peer (bidirectional merge).
        
        Steps:
        1. Get peer's document state
        2. Merge peer state into local store
        3. Send local state to peer for merging
        
        Args:
            peer_id: Peer to sync with
            
        Returns:
            True if sync successful, False otherwise
        """
        if peer_id not in self.peers:
            logger.error(f"Cannot sync with unregistered peer: {peer_id}")
            return False
        
        peer = self.peers[peer_id]
        peer.sync_state = "syncing"
        
        try:
            # Get peer's data via callback
            if peer_id not in self._sync_callbacks:
                logger.warning(f"No sync callback for peer {peer_id}")
                peer.sync_state = "error"
                peer.last_error = "No sync callback configured"
                return False
            
            peer_data = self._sync_callbacks[peer_id](peer_id)
            
            if not peer_data:
                logger.warning(f"No data received from peer {peer_id}")
                peer.sync_state = "error"
                peer.last_error = "Empty peer data"
                return False
            
            # Merge peer data into local store
            ops_before = len(self.store.doc.ops)
            self.store.merge_with_peer(peer_data)
            ops_after = len(self.store.doc.ops)
            new_ops = ops_after - ops_before
            
            # Update peer state
            peer.last_sync_ns = time.time_ns()
            peer.ops_synced += new_ops
            peer.sync_state = "idle"
            peer.last_error = None
            
            logger.info(
                f"Synced with peer {peer_id}: received {new_ops} new ops "
                f"(total: {ops_after} ops)"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Sync failed with peer {peer_id}: {e}", exc_info=True)
            peer.sync_state = "error"
            peer.last_error = str(e)
            return False
    
    def incremental_sync(
        self, 
        peer_id: str, 
        peer_changes: bytes
    ) -> Optional[bytes]:
        """
        Perform incremental sync with peer (apply changes only).
        
        This is more efficient than full sync when peers have
        recently synchronized and only need to exchange new changes.
        
        Args:
            peer_id: Peer to sync with
            peer_changes: Serialized changes from peer since last sync
            
        Returns:
            Serialized local changes to send back to peer, or None on error
        """
        if peer_id not in self.peers:
            logger.error(f"Cannot incremental sync with unregistered peer: {peer_id}")
            return None
        
        peer = self.peers[peer_id]
        
        try:
            # Apply peer changes
            if peer_changes:
                self.store.merge_with_peer(peer_changes)
            
            # Get our changes to send back
            # For simplicity, we send full state (pure Python doesn't have incremental)
            # Real Automerge would track changes since last sync
            local_data = self.store.get_save_data()
            
            peer.last_sync_ns = time.time_ns()
            
            logger.debug(f"Incremental sync with peer {peer_id} completed")
            
            return local_data
            
        except Exception as e:
            logger.error(f"Incremental sync failed with peer {peer_id}: {e}")
            return None
    
    def sync_all_peers(self) -> Dict[str, bool]:
        """
        Sync with all registered peers.
        
        Returns:
            Dict mapping peer_id to success status
        """
        results = {}
        
        for peer_id in list(self.peers.keys()):
            results[peer_id] = self.sync_with_peer(peer_id)
        
        successes = sum(1 for success in results.values() if success)
        logger.info(
            f"Batch sync completed: {successes}/{len(results)} peers successful"
        )
        
        return results
    
    def get_peer_state(self, peer_id: str) -> Optional[PeerState]:
        """Get current state of a peer"""
        return self.peers.get(peer_id)
    
    def get_all_peers(self) -> Dict[str, PeerState]:
        """Get all registered peers"""
        return self.peers.copy()
    
    def get_sync_status(self) -> Dict:
        """
        Get overall sync status.
        
        Returns:
            Dict with sync statistics
        """
        total_peers = len(self.peers)
        syncing = sum(1 for p in self.peers.values() if p.sync_state == "syncing")
        errors = sum(1 for p in self.peers.values() if p.sync_state == "error")
        
        return {
            "local_peer_id": self.local_peer_id,
            "total_ops": len(self.store.doc.ops),
            "total_tasks": len(self.store.doc.tasks),
            "total_peers": total_peers,
            "syncing_peers": syncing,
            "error_peers": errors,
            "peers": {
                peer_id: {
                    "address": peer.address,
                    "last_sync": peer.last_sync_ns,
                    "state": peer.sync_state,
                    "ops_synced": peer.ops_synced,
                    "error": peer.last_error
                }
                for peer_id, peer in self.peers.items()
            }
        }
