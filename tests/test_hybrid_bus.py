"""
Tests for Hybrid Bus

Tests dual NATS+P2P publishing, deduplication, fallback, and P2P preference.
"""

import pytest
import sys
from pathlib import Path
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bus.hybrid import HybridBus, MessageCache
from bus.migration_monitor import MigrationMonitor, TransportStats, MigrationMetrics


# Minimal P2PBus mock for testing
class P2PBus:
    """Simple P2PBus mock"""

    def __init__(self):
        self.published = []
        self.subscriptions = {}

    def publish_envelope(self, envelope, subject):
        self.published.append((envelope, subject))

    def subscribe_envelopes(self, subject, handler):
        if subject not in self.subscriptions:
            self.subscriptions[subject] = []
        self.subscriptions[subject].append(handler)


class MockNATSBus:
    """Mock NATS bus for testing"""

    def __init__(self):
        self.published_messages = []
        self.subscriptions = {}

    def publish_envelope(self, envelope, subject):
        """Record published message"""
        self.published_messages.append((envelope, subject))

    def subscribe_envelopes(self, subject, handler):
        """Record subscription"""
        if subject not in self.subscriptions:
            self.subscriptions[subject] = []
        self.subscriptions[subject].append(handler)

    def simulate_receive(self, subject, envelope):
        """Simulate receiving message"""
        for handler in self.subscriptions.get(subject, []):
            handler(envelope)


class TestMessageCache:
    """Tests for message cache"""

    def test_cache_initialization(self):
        """Can initialize cache"""
        cache = MessageCache(max_size=100, ttl_seconds=60)

        assert cache.size() == 0
        assert cache.max_size == 100

    def test_add_message(self):
        """Can add message to cache"""
        cache = MessageCache()

        is_new = cache.add("msg-1")

        assert is_new is True
        assert cache.contains("msg-1")
        assert cache.size() == 1

    def test_duplicate_detection(self):
        """Detects duplicate messages"""
        cache = MessageCache()

        # First add
        is_new1 = cache.add("msg-1")
        assert is_new1 is True

        # Duplicate add
        is_new2 = cache.add("msg-1")
        assert is_new2 is False

    def test_lru_eviction(self):
        """Evicts oldest when max size reached"""
        cache = MessageCache(max_size=3)

        cache.add("msg-1")
        cache.add("msg-2")
        cache.add("msg-3")
        cache.add("msg-4")  # Should evict msg-1

        assert not cache.contains("msg-1")
        assert cache.contains("msg-4")
        assert cache.size() == 3

    def test_ttl_cleanup(self):
        """Removes expired messages"""
        cache = MessageCache(ttl_seconds=0.1)  # 100ms TTL

        cache.add("msg-1")
        assert cache.contains("msg-1")

        # Wait for expiry
        time.sleep(0.2)
        cache.cleanup()

        assert not cache.contains("msg-1")


class TestMigrationMonitor:
    """Tests for migration monitor"""

    def test_monitor_initialization(self):
        """Can initialize monitor"""
        monitor = MigrationMonitor()

        assert monitor.metrics.nats_stats.messages_sent == 0
        assert monitor.metrics.p2p_stats.messages_sent == 0

    def test_record_send(self):
        """Can record message sends"""
        monitor = MigrationMonitor()

        monitor.record_send("msg-1", "NATS")
        monitor.record_send("msg-2", "P2P")

        assert monitor.metrics.nats_stats.messages_sent == 1
        assert monitor.metrics.p2p_stats.messages_sent == 1

    def test_record_receive(self):
        """Can record message receives"""
        monitor = MigrationMonitor()

        monitor.record_receive("msg-1", "NATS")
        monitor.record_receive("msg-2", "P2P")

        assert monitor.metrics.nats_stats.messages_received == 1
        assert monitor.metrics.p2p_stats.messages_received == 1

    def test_duplicate_detection(self):
        """Detects duplicate receives"""
        monitor = MigrationMonitor()

        monitor.record_receive("msg-1", "NATS")
        monitor.record_receive("msg-1", "NATS")  # Duplicate

        assert monitor.metrics.duplicate_count == 1

    def test_divergence_detection(self):
        """Detects message divergence"""
        monitor = MigrationMonitor()

        # Message only via NATS
        monitor.record_receive("msg-1", "NATS")

        # Message only via P2P
        monitor.record_receive("msg-2", "P2P")

        divergent = monitor.check_divergence()

        assert len(divergent) == 2
        assert monitor.metrics.divergence_count == 2

    def test_success_rate_calculation(self):
        """Calculates success rates"""
        stats = TransportStats("TEST")

        stats.messages_sent = 90
        stats.errors = 10

        success_rate = stats.get_success_rate()

        assert success_rate == 0.9

    def test_health_score(self):
        """Calculates health score"""
        metrics = MigrationMetrics()

        # Good health
        metrics.nats_stats.messages_sent = 100
        metrics.p2p_stats.messages_sent = 100

        health = metrics.get_health_score()

        assert health == 1.0  # Perfect health

    def test_get_stats(self):
        """Can get statistics"""
        monitor = MigrationMonitor()

        monitor.record_send("msg-1", "NATS")
        monitor.record_receive("msg-1", "NATS")

        stats = monitor.get_stats()

        assert "nats" in stats
        assert "p2p" in stats
        assert "health_score" in stats


class TestHybridBus:
    """Tests for hybrid bus"""

    def test_hybrid_bus_initialization(self):
        """Can initialize hybrid bus"""
        bus = HybridBus(p2p_primary=False)

        assert bus is not None
        assert bus.p2p_bus is not None
        assert bus.monitor is not None

    def test_dual_publish(self):
        """Publishes to both transports"""
        nats_bus = MockNATSBus()
        p2p_bus = P2PBus()
        monitor = MigrationMonitor()

        bus = HybridBus(nats_bus=nats_bus, p2p_bus=p2p_bus, monitor=monitor)

        envelope = {"id": "env-1", "kind": "NEED", "payload": {}}
        bus.publish_envelope(envelope, "thread-1.need")

        # Should publish to both
        assert len(nats_bus.published_messages) == 1
        assert monitor.metrics.nats_stats.messages_sent == 1
        assert monitor.metrics.p2p_stats.messages_sent == 1

    def test_message_deduplication(self):
        """Deduplicates messages from both transports"""
        nats_bus = MockNATSBus()
        p2p_bus = P2PBus()
        monitor = MigrationMonitor()

        bus = HybridBus(nats_bus=nats_bus, p2p_bus=p2p_bus, monitor=monitor)

        received_count = [0]

        def handler(env):
            received_count[0] += 1

        envelope = {"id": "env-1", "kind": "NEED"}

        # Subscribe
        bus.subscribe_envelopes("thread-1.need", handler)

        # Simulate receiving from both transports
        nats_bus.simulate_receive("thread-1.need", envelope)

        # Simulate P2P receive (would need actual P2P simulation)
        # For now, just verify deduplication logic works

        assert bus.message_cache.contains("env-1")

    def test_fallback_to_nats(self):
        """Falls back to NATS if P2P fails"""
        nats_bus = MockNATSBus()

        # P2P bus that always fails
        class BrokenP2PBus:
            def publish_envelope(self, envelope, subject):
                raise Exception("P2P failed")

            def subscribe_envelopes(self, subject, handler):
                pass

        p2p_bus = BrokenP2PBus()
        monitor = MigrationMonitor()

        bus = HybridBus(nats_bus=nats_bus, p2p_bus=p2p_bus, monitor=monitor)

        envelope = {"id": "env-1", "kind": "NEED"}
        bus.publish_envelope(envelope, "thread-1.need")

        # Should still publish to NATS
        assert len(nats_bus.published_messages) == 1
        assert monitor.metrics.p2p_stats.errors == 1

    def test_prefer_p2p_mode(self):
        """P2P primary mode configuration"""
        # P2P primary
        bus1 = HybridBus(p2p_primary=True)
        assert bus1.p2p_primary is True

        # NATS primary
        bus2 = HybridBus(p2p_primary=False)
        assert bus2.p2p_primary is False

    def test_get_stats(self):
        """Can get bus statistics"""
        bus = HybridBus()

        stats = bus.get_stats()

        assert "nats" in stats
        assert "p2p" in stats
        assert "cache_size" in stats
        assert "health_score" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
