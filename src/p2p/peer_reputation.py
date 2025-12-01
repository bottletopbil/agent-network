"""
Peer Reputation System

Tracks peer reliability, latency, and behavior to score peers
and maintain high-quality connections.
"""

import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PeerStats:
    """Statistics for a single peer"""

    peer_id: str
    messages_delivered: int = 0
    messages_failed: int = 0
    total_latency_ms: float = 0.0
    latency_samples: int = 0
    last_seen: float = field(default_factory=time.time)
    first_seen: float = field(default_factory=time.time)
    blacklisted: bool = False

    def get_reliability(self) -> float:
        """Calculate reliability score (0.0-1.0)"""
        total = self.messages_delivered + self.messages_failed
        if total == 0:
            return 0.5  # Neutral for new peers
        return self.messages_delivered / total

    def get_avg_latency_ms(self) -> float:
        """Get average latency in milliseconds"""
        if self.latency_samples == 0:
            return 0.0
        return self.total_latency_ms / self.latency_samples

    def get_uptime_seconds(self) -> float:
        """Get how long we've known this peer"""
        return time.time() - self.first_seen


class PeerReputation:
    """
    Manages peer reputation scoring.

    Tracks message delivery, latency, and behavior to score peers
    and identify problematic peers for blacklisting.
    """

    # Reputation thresholds
    BLACKLIST_THRESHOLD = 0.3  # Below this score → blacklist
    GOOD_PEER_THRESHOLD = 0.7  # Above this score → good

    # Latency thresholds (ms)
    GOOD_LATENCY_MS = 100
    BAD_LATENCY_MS = 1000

    def __init__(self, blacklist_threshold: float = BLACKLIST_THRESHOLD):
        """
        Initialize reputation tracker.

        Args:
            blacklist_threshold: Score below which peers are blacklisted
        """
        self.blacklist_threshold = blacklist_threshold

        # Peer statistics: peer_id → PeerStats
        self.peers: Dict[str, PeerStats] = {}

        # Blacklisted peers
        self.blacklist: set[str] = set()

        logger.info("Peer reputation system initialized")

    def record_message_delivered(self, peer_id: str, latency_ms: float = None):
        """
        Record successful message delivery.

        Args:
            peer_id: Peer that delivered message
            latency_ms: Optional message latency
        """
        stats = self._get_or_create_stats(peer_id)

        stats.messages_delivered += 1
        stats.last_seen = time.time()

        if latency_ms is not None:
            stats.total_latency_ms += latency_ms
            stats.latency_samples += 1

        # Check if should remove from blacklist (rehabilitation)
        if peer_id in self.blacklist:
            score = self.get_score(peer_id)
            if score > self.blacklist_threshold + 0.1:  # Hysteresis
                self.blacklist.remove(peer_id)
                stats.blacklisted = False
                logger.info(f"Peer {peer_id} rehabilitated (score: {score:.2f})")

    def record_message_failed(self, peer_id: str):
        """
        Record failed message delivery.

        Args:
            peer_id: Peer that failed to deliver
        """
        stats = self._get_or_create_stats(peer_id)

        stats.messages_failed += 1
        stats.last_seen = time.time()

        # Check if should blacklist
        score = self.get_score(peer_id)
        if score < self.blacklist_threshold and peer_id not in self.blacklist:
            self.blacklist.add(peer_id)
            stats.blacklisted = True
            logger.warning(f"Peer {peer_id} blacklisted (score: {score:.2f})")

    def get_score(self, peer_id: str) -> float:
        """
        Calculate overall reputation score (0.0-1.0).

        Combines reliability and latency into single score.

        Args:
            peer_id: Peer to score

        Returns:
            Score from 0.0 (worst) to 1.0 (best)
        """
        if peer_id not in self.peers:
            return 0.5  # Neutral for unknown peers

        stats = self.peers[peer_id]

        # Reliability component (70% weight)
        reliability = stats.get_reliability()
        reliability_score = reliability * 0.7

        # Latency component (30% weight)
        avg_latency = stats.get_avg_latency_ms()
        if avg_latency == 0:
            latency_score = 0.3  # Neutral if no latency data
        elif avg_latency <= self.GOOD_LATENCY_MS:
            latency_score = 0.3  # Full latency points
        elif avg_latency >= self.BAD_LATENCY_MS:
            latency_score = 0.0  # No latency points
        else:
            # Linear interpolation
            ratio = (self.BAD_LATENCY_MS - avg_latency) / (
                self.BAD_LATENCY_MS - self.GOOD_LATENCY_MS
            )
            latency_score = ratio * 0.3

        total_score = reliability_score + latency_score

        return max(0.0, min(1.0, total_score))

    def is_blacklisted(self, peer_id: str) -> bool:
        """Check if peer is blacklisted"""
        return peer_id in self.blacklist

    def get_stats(self, peer_id: str) -> Optional[PeerStats]:
        """Get statistics for peer"""
        return self.peers.get(peer_id)

    def get_best_peers(self, count: int = 10) -> list[str]:
        """
        Get best peers by score.

        Args:
            count: Number of peers to return

        Returns:
            List of peer IDs sorted by score (best first)
        """
        # Score all peers
        peer_scores = [
            (peer_id, self.get_score(peer_id))
            for peer_id in self.peers.keys()
            if peer_id not in self.blacklist
        ]

        # Sort by score (descending)
        peer_scores.sort(key=lambda x: x[1], reverse=True)

        # Return top N
        return [peer_id for peer_id, _ in peer_scores[:count]]

    def get_worst_peers(self, count: int = 10) -> list[str]:
        """
        Get worst peers by score.

        Args:
            count: Number of peers to return

        Returns:
            List of peer IDs sorted by score (worst first)
        """
        # Score all peers
        peer_scores = [(peer_id, self.get_score(peer_id)) for peer_id in self.peers.keys()]

        # Sort by score (ascending)
        peer_scores.sort(key=lambda x: x[1])

        # Return bottom N
        return [peer_id for peer_id, _ in peer_scores[:count]]

    def _get_or_create_stats(self, peer_id: str) -> PeerStats:
        """Get or create stats for peer"""
        if peer_id not in self.peers:
            self.peers[peer_id] = PeerStats(peer_id=peer_id)
        return self.peers[peer_id]

    def get_summary(self) -> Dict[str, any]:
        """Get reputation system summary"""
        return {
            "total_peers": len(self.peers),
            "blacklisted": len(self.blacklist),
            "avg_score": sum(self.get_score(p) for p in self.peers) / max(len(self.peers), 1),
            "best_peers": self.get_best_peers(5),
            "worst_peers": self.get_worst_peers(5),
        }
