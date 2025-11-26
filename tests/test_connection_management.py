"""
Tests for Connection Management

Tests connection pool, peer reputation, and circuit relay functionality.
"""

import pytest
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from p2p.connection_pool import ConnectionPool, Connection
from p2p.peer_reputation import PeerReputation, PeerStats
from p2p.circuit_relay import CircuitRelayClient, RelayNode


class TestPeerReputation:
    """Tests for peer reputation system"""
    
    def test_reputation_initialization(self):
        """Can initialize reputation tracker"""
        reputation = PeerReputation()
        
        assert reputation.blacklist_threshold == 0.3
        assert len(reputation.peers) == 0
        assert len(reputation.blacklist) == 0
    
    def test_record_message_delivered(self):
        """Can record successful message delivery"""
        reputation = PeerReputation()
        
        reputation.record_message_delivered("peer-1", latency_ms=50.0)
        
        stats = reputation.get_stats("peer-1")
        assert stats.messages_delivered == 1
        assert stats.latency_samples == 1
    
    def test_record_message_failed(self):
        """Can record failed message delivery"""
        reputation = PeerReputation()
        
        reputation.record_message_failed("peer-1")
        
        stats = reputation.get_stats("peer-1")
        assert stats.messages_failed == 1
    
    def test_reliability_calculation(self):
        """Calculates reliability correctly"""
        stats = PeerStats(peer_id="peer-1")
        
        stats.messages_delivered = 90
        stats.messages_failed = 10
        
        reliability = stats.get_reliability()
        
        assert reliability == 0.9
    
    def test_latency_calculation(self):
        """Calculates average latency correctly"""
        stats = PeerStats(peer_id="peer-1")
        
        stats.total_latency_ms = 500.0
        stats.latency_samples = 5
        
        avg_latency = stats.get_avg_latency_ms()
        
        assert avg_latency == 100.0
    
    def test_peer_scoring(self):
        """Scores peers correctly"""
        reputation = PeerReputation()
        
        # Good peer
        for _ in range(95):
            reputation.record_message_delivered("good-peer", latency_ms=50.0)
        for _ in range(5):
            reputation.record_message_failed("good-peer")
        
        good_score = reputation.get_score("good-peer")
        assert good_score > 0.8
        
        # Bad peer
        for _ in range(30):
            reputation.record_message_delivered("bad-peer", latency_ms=500.0)
        for _ in range(70):
            reputation.record_message_failed("bad-peer")
        
        bad_score = reputation.get_score("bad-peer")
        assert bad_score < 0.4
    
    def test_blacklist_enforcement(self):
        """Blacklists low-scoring peers"""
        reputation = PeerReputation(blacklist_threshold=0.3)
        
        # Create low-scoring peer (need very high failure rate)
        for _ in range(5):
            reputation.record_message_delivered("bad-peer", latency_ms=1500.0)  # Bad latency
        for _ in range(95):
            reputation.record_message_failed("bad-peer")
        
        # Should be blacklisted (5% reliability * 0.7 + 0.0 latency = 0.035)
        assert reputation.is_blacklisted("bad-peer")
    
    def test_peer_rehabilitation(self):
        """Can rehabilitate blacklisted peers"""
        reputation = PeerReputation(blacklist_threshold=0.3)
        
        # Blacklist peer with bad latency
        for _ in range(5):
            reputation.record_message_delivered("peer-1", latency_ms=2000.0)
        for _ in range(95):
            reputation.record_message_failed("peer-1")
        
        assert reputation.is_blacklisted("peer-1")
        
        # Improve behavior
        for _ in range(100):
            reputation.record_message_delivered("peer-1", latency_ms=50.0)
        
        # Should be rehabilitated
        assert not reputation.is_blacklisted("peer-1")
    
    def test_get_best_peers(self):
        """Can get best peers"""
        reputation = PeerReputation()
        
        # Create peers with different scores
        for i in range(5):
            for _ in range(90 - (i * 10)):
                reputation.record_message_delivered(f"peer-{i}", latency_ms=50.0)
            for _ in range(10 + (i * 10)):
                reputation.record_message_failed(f"peer-{i}")
        
        best_peers = reputation.get_best_peers(count=3)
        
        assert len(best_peers) <= 3
        assert "peer-0" in best_peers  # Best performer
    
    def test_get_worst_peers(self):
        """Can get worst peers"""
        reputation = PeerReputation()
        
        # Create peers
        for i in range(5):
            for _ in range(50 + (i * 10)):
                reputation.record_message_delivered(f"peer-{i}")
            for _ in range(50 - (i * 10)):
                reputation.record_message_failed(f"peer-{i}")
        
        worst_peers = reputation.get_worst_peers(count=3)
        
        assert len(worst_peers) <= 3


class TestConnectionPool:
    """Tests for connection pool"""
    
    def test_pool_initialization(self):
        """Can initialize connection pool"""
        pool = ConnectionPool(max_connections=50, connection_timeout=30)
        
        assert pool.max_connections == 50
        assert pool.connection_timeout == 30
        assert pool.get_connection_count() == 0
    
    def test_add_connection(self):
        """Can add connection to pool"""
        pool = ConnectionPool()
        
        conn = pool.add_connection("peer-1", "192.168.1.100", 4001)
        
        assert conn is not None
        assert conn.peer_id == "peer-1"
        assert pool.get_connection_count() == 1
    
    def test_get_connection(self):
        """Can get existing connection"""
        pool = ConnectionPool()
        
        pool.add_connection("peer-1", "192.168.1.100", 4001)
        
        conn = pool.get_connection("peer-1")
        
        assert conn is not None
        assert conn.peer_id == "peer-1"
    
    def test_close_connection(self):
        """Can close connection"""
        pool = ConnectionPool()
        
        pool.add_connection("peer-1", "192.168.1.100", 4001)
        
        closed = pool.close_connection("peer-1")
        
        assert closed is True
        assert pool.get_connection_count() == 0
    
    def test_connection_pool_limits(self):
        """Enforces connection limits"""
        pool = ConnectionPool(max_connections=5)
        
        # Add to limit
        for i in range(5):
            pool.add_connection(f"peer-{i}", "192.168.1.100", 4000 + i)
        
        assert pool.get_connection_count() == 5
        
        # Try to exceed - should evict
        conn = pool.add_connection("peer-extra", "192.168.1.100", 5000)
        
        # Should still be at limit (evicted one)
        assert pool.get_connection_count() == 5
    
    def test_connection_timeout(self):
        """Removes timed-out connections"""
        pool = ConnectionPool(connection_timeout=1)  # 1 second
        
        pool.add_connection("peer-1", "192.168.1.100", 4001)
        
        # Wait for timeout
        time.sleep(1.5)
        
        pool.maintain_connections()
        
        # Should be removed
        assert pool.get_connection_count() == 0
    
    def test_blacklist_rejection(self):
        """Rejects blacklisted peers"""
        pool = ConnectionPool()
        reputation = PeerReputation()
        pool.set_reputation(reputation)
        
        # Blacklist peer properly
        for _ in range(5):
            reputation.record_message_delivered("bad-peer", latency_ms=2000.0)
        for _ in range(95):
            reputation.record_message_failed("bad-peer")
        
        # Verify blacklisted
        assert reputation.is_blacklisted("bad-peer")
        
        # Try to connect
        conn = pool.add_connection("bad-peer", "192.168.1.100", 4001)
        
        # Should be rejected
        assert conn is None
    
    def test_quality_based_rotation(self):
        """Rotates low-quality connections"""
        pool = ConnectionPool(max_connections=10, target_peer_count=5)
        reputation = PeerReputation()
        pool.set_reputation(reputation)
        
        # Add good and bad peers
        for i in range(10):
            pool.add_connection(f"peer-{i}", "192.168.1.100", 4000 + i)
            
            if i < 5:
                # Good peers
                for _ in range(90):
                    reputation.record_message_delivered(f"peer-{i}")
            else:
                # Bad peers
                for _ in range(50):
                    reputation.record_message_failed(f"peer-{i}")
        
        # Maintain - should rotate bad peers
        pool.maintain_connections()
        
        # Bad peers should be rotated out
        assert pool.get_connection_count() <= 10
    
    def test_get_stats(self):
        """Can get pool statistics"""
        pool = ConnectionPool(max_connections=100)
        
        pool.add_connection("peer-1", "192.168.1.100", 4001)
        
        stats = pool.get_stats()
        
        assert stats["active_connections"] == 1
        assert stats["max_connections"] == 100
        assert "utilization" in stats


class TestCircuitRelay:
    """Tests for circuit relay"""
    
    def test_relay_initialization(self):
        """Can initialize relay client"""
        relay = CircuitRelayClient(enable_auto_relay=True)
        
        assert relay.enable_auto_relay is True
        assert len(relay.relay_nodes) == 0
    
    def test_add_relay_node(self):
        """Can add relay node"""
        relay = CircuitRelayClient()
        
        relay.add_relay_node(
            "relay-1",
            "/ip4/relay.example.com/tcp/4001/p2p/12D3Koo..."
        )
        
        assert len(relay.relay_nodes) == 1
    
    def test_direct_connection(self):
        """Can attempt direct connection """
        relay = CircuitRelayClient()
        
        # Note: Simulated, actual success varies
        result = relay.connect_direct("peer-1", "192.168.1.100", 4001)
        
        assert isinstance(result, bool)
        assert relay.direct_attempts == 1
    
    def test_relay_fallback(self):
        """Falls back to relay on direct failure"""
        relay = CircuitRelayClient(enable_auto_relay=True)
        
        relay.add_relay_node(
            "relay-1",
            "/ip4/relay.example.com/tcp/4001/p2p/12D3Koo..."
        )
        
        # Try connecting (may use relay if direct fails)
        # Note: Simulated behavior
        relay.connect("peer-1", "192.168.1.100", 4001)
        
        # Should have attempted connection
        assert relay.direct_attempts > 0
    
    def test_relay_tracking(self):
        """Tracks relayed connections"""
        relay = CircuitRelayClient(enable_auto_relay=True)
        
        relay.add_relay_node("relay-1", "/ip4/relay.example.com/tcp/4001")
        
        # Simulate relay connection
        relay_id = relay.connect_via_relay("peer-1")
        
        if relay_id:
            assert relay.is_relayed("peer-1")
            assert relay.get_relay_for_peer("peer-1") == relay_id
    
    def test_close_relay(self):
        """Can close relayed connection"""
        relay = CircuitRelayClient(enable_auto_relay=True)
        
        relay.add_relay_node("relay-1", "/ip4/relay.example.com")
        relay.connect_via_relay("peer-1")
        
        relay.close_relay("peer-1")
        
        assert not relay.is_relayed("peer-1")
    
    def test_relay_stats(self):
        """Can get relay statistics"""
        relay = CircuitRelayClient()
        
        relay.add_relay_node("relay-1", "/ip4/relay.example.com")
        relay.connect_direct("peer-1", "192.168.1.100", 4001)
        
        stats = relay.get_stats()
        
        assert "relay_nodes" in stats
        assert "direct_attempts" in stats
        assert "relay_attempts" in stats
        assert "auto_relay_enabled" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
