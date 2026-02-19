"""
Hybrid Bus Implementation

Provides dual-mode message transport using both NATS and libp2p
with message deduplication and configurable preference.
"""

import os
import logging
import hashlib
import time
from typing import Dict, Any, Callable
from collections import OrderedDict

from policy.enforcement import validate_ingress_envelope, PolicyEnforcementError

logger = logging.getLogger(__name__)


class MessageCache:
    """
    LRU cache for message deduplication.

    Tracks seen messages to prevent duplicate delivery when
    messages arrive from both NATS and P2P.
    """

    def __init__(self, max_size: int = 10000, ttl_seconds: float = 300.0):
        """
        Initialize message cache.

        Args:
            max_size: Maximum cached messages
            ttl_seconds: Time-to-live for cached entries
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds

        # OrderedDict for LRU: msg_id -> timestamp
        self.cache: OrderedDict[str, float] = OrderedDict()

    def add(self, msg_id: str) -> bool:
        """
        Add message to cache.

        Args:
            msg_id: Message identifier

        Returns:
            True if added (not duplicate), False if already in cache
        """
        current_time = time.time()

        # Check if already in cache
        if msg_id in self.cache:
            # Move to end (most recently used)
            self.cache.move_to_end(msg_id)
            return False  # Duplicate

        # Add to cache
        self.cache[msg_id] = current_time

        # Evict if over size
        while len(self.cache) > self.max_size:
            self.cache.popitem(last=False)  # Remove oldest

        return True  # New message

    def cleanup(self):
        """Remove expired entries"""
        current_time = time.time()
        cutoff_time = current_time - self.ttl_seconds

        # Remove expired entries
        expired = [msg_id for msg_id, timestamp in self.cache.items() if timestamp < cutoff_time]

        for msg_id in expired:
            del self.cache[msg_id]

        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired messages")

    def contains(self, msg_id: str) -> bool:
        """Check if message is in cache"""
        return msg_id in self.cache

    def size(self) -> int:
        """Get cache size"""
        return len(self.cache)


class HybridBus:
    """
    Hybrid message bus using both NATS and libp2p.

    Publishes to both transports and deduplicates received messages.
    Supports configurable preference for P2P-first mode.
    """

    def __init__(self, nats_bus=None, p2p_bus=None, monitor=None, p2p_primary: bool = None):
        """
        Initialize hybrid bus.

        Args:
            nats_bus: NATS bus instance (created if None)
            p2p_bus: P2P bus instance (created if None)
            monitor: Migration monitor (created if None)
            p2p_primary: Prefer P2P if True (from env if None)
        """
        # Get buses
        if nats_bus is None:
            # Import here to avoid circular dependency
            import sys
            from pathlib import Path

            sys.path.insert(0, str(Path(__file__).parent.parent))
            # Use mock NATS bus for testing
            self.nats_bus = None  # Would be NATSBus() in production
        else:
            self.nats_bus = nats_bus

        if p2p_bus is None:
            from bus import P2PBus

            self.p2p_bus = P2PBus()
        else:
            self.p2p_bus = p2p_bus

        # Migration monitor
        if monitor is None:
            from bus.migration_monitor import MigrationMonitor

            self.monitor = MigrationMonitor()
        else:
            self.monitor = monitor

        # P2P preference
        if p2p_primary is None:
            p2p_primary = os.getenv("P2P_PRIMARY", "false").lower() == "true"
        self.p2p_primary = p2p_primary

        # Message cache for deduplication
        self.message_cache = MessageCache()

        # Cleanup counter
        self.message_count = 0
        self.cleanup_interval = 100

        logger.info(f"Hybrid bus initialized (P2P primary: {self.p2p_primary})")

    def _compute_msg_id(self, envelope: Dict[str, Any]) -> str:
        """Compute deterministic message ID from envelope"""
        # Use envelope ID if available
        if "id" in envelope:
            return str(envelope["id"])

        # Otherwise hash the envelope
        import json

        envelope_str = json.dumps(envelope, sort_keys=True)
        return hashlib.sha256(envelope_str.encode()).hexdigest()[:16]

    def publish_envelope(self, envelope: Dict[str, Any], subject: str):
        """
        Publish envelope via both transports.

        Args:
            envelope: Envelope dictionary
            subject: Subject/topic
        """
        msg_id = self._compute_msg_id(envelope)

        # Publish via P2P
        try:
            self.p2p_bus.publish_envelope(envelope, subject)
            self.monitor.record_send(msg_id, "P2P")
        except Exception as e:
            logger.error(f"P2P publish error: {e}")
            self.monitor.record_error("P2P", str(e))

        # Publish via NATS
        if self.nats_bus:
            try:
                self.nats_bus.publish_envelope(envelope, subject)
                self.monitor.record_send(msg_id, "NATS")
            except Exception as e:
                logger.error(f"NATS publish error: {e}")
                self.monitor.record_error("NATS", str(e))

        logger.debug(f"Published via hybrid bus: {msg_id}")

    def subscribe_envelopes(self, subject: str, handler: Callable[[Dict[str, Any]], None]):
        """
        Subscribe to envelopes from both transports with deduplication.

        Args:
            subject: Subject/topic
            handler: Message handler
        """
        # Periodic cleanup
        self.message_count += 1
        if self.message_count % self.cleanup_interval == 0:
            self.message_cache.cleanup()

        # Wrapper for deduplication
        def deduplicated_handler(envelope: Dict[str, Any], transport: str):
            try:
                validate_ingress_envelope(
                    envelope,
                    source=f"hybrid.{transport.lower()}_ingress",
                )
            except PolicyEnforcementError as e:
                logger.warning(f"Rejected envelope from {transport}: {e}")
                self.monitor.record_error(transport, str(e))
                return

            msg_id = self._compute_msg_id(envelope)

            # Check cache
            if not self.message_cache.add(msg_id):
                # Duplicate - already handled
                logger.debug(f"Deduplicated message from {transport}: {msg_id}")
                return

            # Record reception
            self.monitor.record_receive(msg_id, transport)

            # Call user handler
            try:
                handler(envelope)
            except Exception as e:
                logger.error(f"Handler error: {e}")

        # Subscribe to P2P
        self.p2p_bus.subscribe_envelopes(subject, lambda env: deduplicated_handler(env, "P2P"))

        # Subscribe to NATS
        if self.nats_bus:
            self.nats_bus.subscribe_envelopes(
                subject, lambda env: deduplicated_handler(env, "NATS")
            )

        logger.info(f"Subscribed via hybrid bus: {subject}")

    def get_stats(self) -> Dict[str, Any]:
        """Get hybrid bus statistics"""
        stats = self.monitor.get_stats()
        stats["cache_size"] = self.message_cache.size()
        stats["p2p_primary"] = self.p2p_primary

        return stats

    def log_status(self):
        """Log migration status"""
        self.monitor.log_status()
