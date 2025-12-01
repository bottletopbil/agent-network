"""
Partition detector for network split detection and recovery.

Monitors peer heartbeats and detects network partitions.
"""

import time
import threading
import logging
from typing import Dict, Set, Callable, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PeerStatus:
    """Status of a peer node."""

    peer_id: str
    last_heartbeat: float
    is_alive: bool = True


class PartitionDetector:
    """
    Detects network partitions by monitoring peer heartbeats.

    Responsibilities:
    - Monitor peer heartbeats
    - Detect missing heartbeats (partition)
    - Trigger epoch advancement on partition
    - Trigger RECONCILE on partition heal
    """

    def __init__(
        self,
        heartbeat_interval: float = 10.0,
        missed_heartbeat_threshold: int = 3,
        on_partition_callback: Optional[Callable] = None,
        on_heal_callback: Optional[Callable] = None,
    ):
        """
        Initialize partition detector.

        Args:
            heartbeat_interval: Seconds between heartbeats
            missed_heartbeat_threshold: Number of missed heartbeats before declaring partition
            on_partition_callback: Called when partition detected
            on_heal_callback: Called when partition heals
        """
        self.heartbeat_interval = heartbeat_interval
        self.missed_heartbeat_threshold = missed_heartbeat_threshold
        self.timeout = heartbeat_interval * missed_heartbeat_threshold

        self._peers: Dict[str, PeerStatus] = {}
        self._partitioned_peers: Set[str] = set()
        self._lock = threading.Lock()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None

        self._on_partition = on_partition_callback
        self._on_heal = on_heal_callback

    def start(self):
        """Start partition detection monitoring."""
        if self._running:
            return

        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Partition detector started")

    def stop(self):
        """Stop partition detection monitoring."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("Partition detector stopped")

    def register_peer(self, peer_id: str):
        """Register a peer for monitoring."""
        with self._lock:
            if peer_id not in self._peers:
                self._peers[peer_id] = PeerStatus(
                    peer_id=peer_id, last_heartbeat=time.time()
                )
                logger.info(f"Registered peer: {peer_id}")

    def heartbeat(self, peer_id: str):
        """Record heartbeat from peer."""
        with self._lock:
            if peer_id in self._peers:
                self._peers[peer_id].last_heartbeat = time.time()

                # Check if this peer was partitioned and is now healing
                if peer_id in self._partitioned_peers:
                    self._partitioned_peers.remove(peer_id)
                    self._peers[peer_id].is_alive = True
                    logger.info(f"Partition healed for peer: {peer_id}")

                    # Trigger heal callback
                    if self._on_heal:
                        try:
                            self._on_heal(peer_id)
                        except Exception as e:
                            logger.error(f"Error in heal callback: {e}")

    def _monitor_loop(self):
        """Monitor loop to detect partitions."""
        while self._running:
            try:
                self.detect_partition()
                time.sleep(self.heartbeat_interval)
            except Exception as e:
                logger.error(f"Error in partition detection: {e}", exc_info=True)

    def detect_partition(self) -> Set[str]:
        """
        Detect partitioned peers.

        Returns:
            Set of partitioned peer IDs
        """
        current_time = time.time()
        newly_partitioned = set()

        with self._lock:
            for peer_id, status in self._peers.items():
                time_since_heartbeat = current_time - status.last_heartbeat

                if time_since_heartbeat > self.timeout:
                    # Peer is partitioned
                    if peer_id not in self._partitioned_peers:
                        # Newly detected partition
                        self._partitioned_peers.add(peer_id)
                        status.is_alive = False
                        newly_partitioned.add(peer_id)

                        logger.warning(
                            f"Partition detected for peer {peer_id} "
                            f"(no heartbeat for {time_since_heartbeat:.1f}s)"
                        )

                        # Trigger partition callback
                        if self._on_partition:
                            try:
                                self._on_partition(peer_id)
                            except Exception as e:
                                logger.error(f"Error in partition callback: {e}")

        return newly_partitioned

    def get_partitioned_peers(self) -> Set[str]:
        """Get currently partitioned peer IDs."""
        with self._lock:
            return self._partitioned_peers.copy()

    def get_alive_peers(self) -> Set[str]:
        """Get currently alive peer IDs."""
        with self._lock:
            return {
                peer_id for peer_id, status in self._peers.items() if status.is_alive
            }

    def is_partitioned(self) -> bool:
        """Check if any partition exists."""
        with self._lock:
            return len(self._partitioned_peers) > 0
