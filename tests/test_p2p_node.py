"""
Tests for P2P Node

Tests P2P node startup, peer ID generation, and multiaddr listening.
"""

import pytest
import sys
from pathlib import Path
import tempfile
import shutil

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from p2p.node import P2PNode
from p2p.identity import P2PIdentity, generate_peer_id, get_or_create_identity


class TestP2PIdentity:
    """Tests for P2P identity management"""

    def test_identity_generation(self):
        """Can generate new identity"""
        identity = P2PIdentity()

        assert identity.private_key is not None
        assert identity.public_key is not None

    def test_peer_id_generation(self):
        """Can generate peer ID from identity"""
        identity = P2PIdentity()
        peer_id = identity.to_peer_id()

        assert peer_id is not None
        assert isinstance(peer_id, str)
        assert peer_id.startswith("12D3Koo")  # Standard libp2p peer ID prefix

    def test_did_peer_generation(self):
        """Can generate DID:peer from identity"""
        identity = P2PIdentity()
        did_peer = identity.to_did_peer()

        assert did_peer is not None
        assert isinstance(did_peer, str)
        assert did_peer.startswith("did:peer:")

    def test_identity_persistence(self):
        """Can save and load identity"""
        with tempfile.TemporaryDirectory() as tmpdir:
            identity_path = Path(tmpdir) / "identity.json"

            # Create and save
            original_identity = P2PIdentity()
            original_peer_id = original_identity.to_peer_id()
            original_identity.save(identity_path)

            # Load
            loaded_identity = P2PIdentity.load(identity_path)
            loaded_peer_id = loaded_identity.to_peer_id()

            # Should match
            assert loaded_peer_id == original_peer_id

    def test_get_or_create_identity_creates_new(self):
        """get_or_create_identity creates new when file doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            identity_path = Path(tmpdir) / "identity.json"

            # Should create new
            identity = get_or_create_identity(identity_path)

            assert identity is not None
            assert identity_path.exists()

    def test_get_or_create_identity_loads_existing(self):
        """get_or_create_identity loads existing identity"""
        with tempfile.TemporaryDirectory() as tmpdir:
            identity_path = Path(tmpdir) / "identity.json"

            # Create first identity
            identity1 = get_or_create_identity(identity_path)
            peer_id1 = identity1.to_peer_id()

            # Load same identity
            identity2 = get_or_create_identity(identity_path)
            peer_id2 = identity2.to_peer_id()

            # Should be same
            assert peer_id1 == peer_id2

    def test_generate_peer_id_helper(self):
        """generate_peer_id helper works"""
        identity, peer_id = generate_peer_id()

        assert identity is not None
        assert peer_id is not None
        assert peer_id == identity.to_peer_id()


class TestP2PNode:
    """Tests for P2P node"""

    def test_node_initialization(self):
        """Can initialize P2P node"""
        with tempfile.TemporaryDirectory() as tmpdir:
            identity_path = Path(tmpdir) / "identity.json"

            node = P2PNode(identity_path=identity_path)

            assert node is not None
            assert node.identity is not None
            assert node.is_running is False

    def test_node_startup(self):
        """Can start P2P node"""
        with tempfile.TemporaryDirectory() as tmpdir:
            identity_path = Path(tmpdir) / "identity.json"

            node = P2PNode(identity_path=identity_path)
            node.start()

            assert node.is_running is True

            node.stop()

    def test_node_shutdown(self):
        """Can stop P2P node"""
        with tempfile.TemporaryDirectory() as tmpdir:
            identity_path = Path(tmpdir) / "identity.json"

            node = P2PNode(identity_path=identity_path)
            node.start()
            node.stop()

            assert node.is_running is False

    def test_peer_id_available(self):
        """Peer ID is available"""
        with tempfile.TemporaryDirectory() as tmpdir:
            identity_path = Path(tmpdir) / "identity.json"

            node = P2PNode(identity_path=identity_path)
            peer_id = node.get_peer_id()

            assert peer_id is not None
            assert isinstance(peer_id, str)
            assert peer_id.startswith("12D3Koo")

    def test_did_peer_available(self):
        """DID:peer is available"""
        with tempfile.TemporaryDirectory() as tmpdir:
            identity_path = Path(tmpdir) / "identity.json"

            node = P2PNode(identity_path=identity_path)
            did_peer = node.get_did_peer()

            assert did_peer is not None
            assert isinstance(did_peer, str)
            assert did_peer.startswith("did:peer:")

    def test_multiaddr_listening(self):
        """Multiaddrs available when node is running"""
        with tempfile.TemporaryDirectory() as tmpdir:
            identity_path = Path(tmpdir) / "identity.json"

            node = P2PNode(
                listen_addr="/ip4/0.0.0.0/tcp/4001", identity_path=identity_path
            )

            # No addrs before starting
            assert len(node.get_multiaddrs()) == 0

            node.start()

            # Should have addrs after starting
            addrs = node.get_multiaddrs()
            assert len(addrs) > 0

            # Should contain peer ID
            peer_id = node.get_peer_id()
            assert any(peer_id in addr for addr in addrs)

            # Should have correct port
            assert any("4001" in addr for addr in addrs)

            node.stop()

    def test_custom_listen_address(self):
        """Can use custom listen address"""
        with tempfile.TemporaryDirectory() as tmpdir:
            identity_path = Path(tmpdir) / "identity.json"

            node = P2PNode(
                listen_addr="/ip4/127.0.0.1/tcp/5001", identity_path=identity_path
            )

            assert node.listen_host == "127.0.0.1"
            assert node.listen_port == 5001

    def test_context_manager(self):
        """Node works as context manager"""
        with tempfile.TemporaryDirectory() as tmpdir:
            identity_path = Path(tmpdir) / "identity.json"

            with P2PNode(identity_path=identity_path) as node:
                assert node.is_running is True

            # Should be stopped after context exit
            assert node.is_running is False

    def test_peer_id_consistent(self):
        """Peer ID is consistent across restarts"""
        with tempfile.TemporaryDirectory() as tmpdir:
            identity_path = Path(tmpdir) / "identity.json"

            # Create first node
            node1 = P2PNode(identity_path=identity_path)
            peer_id1 = node1.get_peer_id()
            node1.start()
            node1.stop()
            del node1

            # Create second node with same identity
            node2 = P2PNode(identity_path=identity_path)
            peer_id2 = node2.get_peer_id()

            # Should be same
            assert peer_id1 == peer_id2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
