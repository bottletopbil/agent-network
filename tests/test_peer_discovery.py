"""
Tests for Peer Discovery

Tests mDNS and DHT-based peer discovery mechanisms.
"""

import pytest
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from p2p.mdns_discovery import MDNSDiscovery
from p2p.dht_discovery import DHTDiscovery
from p2p.bootstrap_nodes import get_bootstrap_nodes, parse_multiaddr
from p2p.node import P2PNode


class TestMDNSDiscovery:
    """Tests for mDNS peer discovery"""

    def test_mdns_initialization(self):
        """Can initialize mDNS discovery"""
        mdns = MDNSDiscovery("peer-1", port=4001)

        assert mdns.node_id == "peer-1"
        assert mdns.port == 4001
        assert mdns.get_peer_count() == 0

    def test_mdns_start_stop(self):
        """Can start and stop mDNS"""
        mdns = MDNSDiscovery("peer-1")

        mdns.start()
        assert mdns.running is True

        mdns.stop()
        assert mdns.running is False

    def test_mdns_local_discovery(self):
        """Two nodes discover each other via mDNS"""
        # Create two mDNS instances
        mdns1 = MDNSDiscovery("peer-1", port=4001)
        mdns2 = MDNSDiscovery("peer-2", port=4002)

        # Track discoveries
        discovered_by_1 = []
        discovered_by_2 = []

        mdns1.on_peer_discovered(lambda pid, h, p: discovered_by_1.append(pid))
        mdns2.on_peer_discovered(lambda pid, h, p: discovered_by_2.append(pid))

        # Simulate mutual discovery
        mdns1.announce_peer("peer-2", "127.0.0.1", 4002)
        mdns2.announce_peer("peer-1", "127.0.0.1", 4001)

        # Check discoveries
        assert mdns1.get_peer_count() == 1
        assert mdns2.get_peer_count() == 1
        assert "peer-2" in mdns1.get_peers()
        assert "peer-1" in mdns2.get_peers()

    def test_mdns_callback(self):
        """mDNS discovery triggers callback"""
        mdns = MDNSDiscovery("peer-1")

        discovered_peers = []

        def on_discovered(peer_id, host, port):
            discovered_peers.append((peer_id, host, port))

        mdns.on_peer_discovered(on_discovered)
        mdns.announce_peer("peer-2", "192.168.1.100", 4001)

        assert len(discovered_peers) == 1
        assert discovered_peers[0] == ("peer-2", "192.168.1.100", 4001)

    def test_mdns_ignores_self(self):
        """mDNS doesn't discover self"""
        mdns = MDNSDiscovery("peer-1")

        mdns.announce_peer("peer-1", "127.0.0.1", 4001)  # Self

        assert mdns.get_peer_count() == 0


class TestDHTDiscovery:
    """Tests for DHT peer discovery"""

    def test_dht_initialization(self):
        """Can initialize DHT discovery"""
        dht = DHTDiscovery("peer-1")

        assert dht.node_id == "peer-1"
        assert dht.connected is False
        assert dht.get_routing_table_size() == 0

    def test_dht_bootstrap(self):
        """Can bootstrap DHT"""
        dht = DHTDiscovery("peer-1")

        bootstrap_nodes = ["/ip4/127.0.0.1/tcp/4001/p2p/bootstrap-peer"]
        dht.bootstrap(bootstrap_nodes)

        assert dht.connected is True

    def test_dht_announce_and_find(self):
        """Can announce and find peers in DHT"""
        dht1 = DHTDiscovery("peer-1")
        dht2 = DHTDiscovery("peer-2")

        # Bootstrap both
        dht1.bootstrap(["/ip4/127.0.0.1/tcp/4001/p2p/boot"])
        dht2.bootstrap(["/ip4/127.0.0.1/tcp/4001/p2p/boot"])

        # Peer 1 announces
        dht1.announce()

        # Peer 2 tries to find peer 1
        # In real DHT, would query network
        # For testing, manually add peer
        dht2.add_peer("peer-1", "127.0.0.1", 4001)

        found = dht2.find_peer("peer-1")
        assert found is not None

    def test_dht_put_get(self):
        """Can store and retrieve from DHT"""
        dht = DHTDiscovery("peer-1")
        dht.bootstrap(["/ip4/127.0.0.1/tcp/4001/p2p/boot"])

        # Store value
        dht.put("test-key", {"data": "test-value"})

        # Retrieve value
        value = dht.get("test-key")

        assert value == {"data": "test-value"}

    def test_dht_distance_calculation(self):
        """Can compute XOR distance"""
        dht = DHTDiscovery("peer-1")

        distance = dht.compute_distance("peer-1", "peer-2")

        assert distance > 0
        assert isinstance(distance, int)

    def test_dht_closest_peers(self):
        """Can find closest peers"""
        dht = DHTDiscovery("peer-1")
        dht.bootstrap(["/ip4/127.0.0.1/tcp/4001/p2p/boot"])

        # Add several peers
        for i in range(5):
            dht.add_peer(f"peer-{i}", "127.0.0.1", 4000 + i)

        # Find closest to target
        closest = dht.find_closest_peers("peer-target", k=3)

        assert len(closest) <= 3

    def test_dht_stats(self):
        """Can get DHT statistics"""
        dht = DHTDiscovery("peer-1")
        dht.bootstrap(["/ip4/127.0.0.1/tcp/4001/p2p/boot"])
        dht.add_peer("peer-2", "127.0.0.1", 4002)

        stats = dht.get_stats()

        assert stats["node_id"] == "peer-1"
        assert stats["connected"] is True
        assert stats["routing_table_size"] == 1


class TestBootstrapNodes:
    """Tests for bootstrap node configuration"""

    def test_get_bootstrap_nodes(self):
        """Can get bootstrap nodes"""
        nodes = get_bootstrap_nodes(include_ipfs=True)

        assert len(nodes) > 0
        assert any("bootstrap.libp2p.io" in node for node in nodes)

    def test_parse_multiaddr(self):
        """Can parse multiaddr"""
        multiaddr = "/ip4/127.0.0.1/tcp/4001/p2p/12D3KooTest"

        parsed = parse_multiaddr(multiaddr)

        assert parsed["host"] == "127.0.0.1"
        assert parsed["port"] == 4001
        assert parsed["peer_id"] == "12D3KooTest"


class TestP2PNodeWithDiscovery:
    """Tests for P2P node with discovery enabled"""

    def test_node_with_mdns(self):
        """Node initializes with mDNS"""
        with tempfile.TemporaryDirectory() as tmpdir:
            identity_path = Path(tmpdir) / "identity.json"

            node = P2PNode(
                identity_path=identity_path, enable_mdns=True, enable_dht=False
            )
            node.start()

            assert node.mdns is not None
            assert node.mdns.running is True

            node.stop()

    def test_node_with_dht(self):
        """Node initializes with DHT"""
        with tempfile.TemporaryDirectory() as tmpdir:
            identity_path = Path(tmpdir) / "identity.json"

            node = P2PNode(
                identity_path=identity_path, enable_mdns=False, enable_dht=True
            )
            node.start()

            assert node.dht is not None
            assert node.dht.connected is True

            node.stop()

    def test_node_peer_discovery(self):
        """Nodes can discover each other"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two nodes
            node1 = P2PNode(
                identity_path=Path(tmpdir) / "id1.json",
                listen_addr="/ip4/127.0.0.1/tcp/4001",
            )
            node2 = P2PNode(
                identity_path=Path(tmpdir) / "id2.json",
                listen_addr="/ip4/127.0.0.1/tcp/4002",
            )

            node1.start()
            node2.start()

            # Simulate discovery (in real scenario, would happen automatically)
            peer2_id = node2.get_peer_id()
            node1._on_peer_discovered(peer2_id, "127.0.0.1", 4002)

            # Check discovery
            assert node1.get_peer_count() == 1
            assert peer2_id in node1.get_discovered_peers()

            node1.stop()
            node2.stop()

    def test_node_tracks_discovered_peers(self):
        """Node tracks discovered peers"""
        with tempfile.TemporaryDirectory() as tmpdir:
            node = P2PNode(identity_path=Path(tmpdir) / "identity.json")
            node.start()

            # Simulate peer discoveries
            node._on_peer_discovered("peer-1", "192.168.1.10", 4001)
            node._on_peer_discovered("peer-2", "192.168.1.11", 4002)

            discovered = node.get_discovered_peers()

            assert len(discovered) == 2
            assert "peer-1" in discovered
            assert "peer-2" in discovered

            node.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
