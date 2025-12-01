"""
Tests for Gossipsub Protocol

Tests topic subscription, message propagation, deduplication, and peer scoring.
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from p2p.gossipsub import GossipsubRouter, GossipsubMessage, PeerScore
from p2p.topics import (
    SwarmTopic,
    create_thread_topic,
    parse_topic,
    filter_topics,
    get_thread_topics,
    is_valid_topic,
)


class TestSwarmTopics:
    """Tests for topic management"""

    def test_topic_creation(self):
        """Can create swarm topic"""
        topic = create_thread_topic("thread-123", "need")

        assert topic == "/swarm/thread/thread-123/need"

    def test_topic_parsing(self):
        """Can parse topic string"""
        topic_str = "/swarm/thread/thread-123/propose"
        topic = parse_topic(topic_str)

        assert topic is not None
        assert topic.thread_id == "thread-123"
        assert topic.verb == "propose"

    def test_topic_round_trip(self):
        """Topic survives round trip"""
        original = SwarmTopic(thread_id="thread-456", verb="decide")
        topic_str = original.to_string()
        parsed = parse_topic(topic_str)

        assert parsed.thread_id == original.thread_id
        assert parsed.verb == original.verb

    def test_invalid_topic(self):
        """Invalid topic returns None"""
        invalid = "/invalid/topic/format"
        topic = parse_topic(invalid)

        assert topic is None
        assert not is_valid_topic(invalid)

    def test_topic_filtering(self):
        """Can filter topics"""
        topics = [
            "/swarm/thread/thread-1/need",
            "/swarm/thread/thread-1/propose",
            "/swarm/thread/thread-2/need",
            "/swarm/thread/thread-2/decide",
        ]

        # Filter by thread_id
        filtered = filter_topics(topics, thread_id="thread-1")
        assert len(filtered) == 2

        # Filter by verb
        filtered = filter_topics(topics, verb="need")
        assert len(filtered) == 2

        # Filter by both
        filtered = filter_topics(topics, thread_id="thread-2", verb="decide")
        assert len(filtered) == 1

    def test_get_thread_topics(self):
        """Can get all topics for thread"""
        topics = get_thread_topics("thread-789")

        assert len(topics) > 0
        assert all("thread-789" in t for t in topics)


class TestGossipsubMessage:
    """Tests for gossipsub messages"""

    def test_message_creation(self):
        """Can create gossipsub message"""
        msg = GossipsubMessage.create(
            topic="/swarm/thread/test/need",
            data=b"test message",
            from_peer="peer-123",
            sequence=1,
        )

        assert msg.msg_id is not None
        assert msg.topic == "/swarm/thread/test/need"
        assert msg.data == b"test message"
        assert msg.sequence == 1

    def test_message_id_deterministic(self):
        """Message ID is deterministic"""
        msg1 = GossipsubMessage.create(
            topic="/test", data=b"data", from_peer="peer1", sequence=1
        )

        msg2 = GossipsubMessage.create(
            topic="/test", data=b"data", from_peer="peer1", sequence=1
        )

        assert msg1.msg_id == msg2.msg_id

    def test_different_messages_different_ids(self):
        """Different messages have different IDs"""
        msg1 = GossipsubMessage.create("/test", b"data1", "peer1", 1)
        msg2 = GossipsubMessage.create("/test", b"data2", "peer1", 2)

        assert msg1.msg_id != msg2.msg_id


class TestPeerScoring:
    """Tests for peer scoring"""

    def test_peer_score_initialization(self):
        """Peer score starts at zero"""
        score = PeerScore(peer_id="peer-123")

        assert score.score == 0.0
        assert score.messages_delivered == 0
        assert score.messages_invalid == 0

    def test_peer_score_update(self):
        """Peer score updates based on behavior"""
        score = PeerScore(peer_id="peer-123")

        # Good behavior
        score.messages_delivered = 10
        score.update_score()

        assert score.score == 10.0

        # Bad behavior
        score.messages_invalid = 2
        score.update_score()

        assert score.score == 6.0  # 10 - (2 * 2)


class TestGossipsubRouter:
    """Tests for gossipsub router"""

    def test_router_initialization(self):
        """Can initialize router"""
        router = GossipsubRouter()

        assert router is not None
        assert len(router.subscriptions) == 0
        assert len(router.mesh) == 0

    def test_topic_subscription(self):
        """Can subscribe to topic"""
        router = GossipsubRouter()

        messages_received = []

        def handler(data: bytes):
            messages_received.append(data)

        topic = "/swarm/thread/test/need"
        router.subscribe(topic, handler)

        assert topic in router.subscriptions
        assert handler in router.subscriptions[topic]

    def test_message_publish_and_receive(self):
        """Can publish and receive messages"""
        router = GossipsubRouter()

        messages_received = []

        def handler(data: bytes):
            messages_received.append(data)

        topic = "/swarm/thread/test/propose"
        router.subscribe(topic, handler)

        # Publish message
        test_data = b"test envelope data"
        router.publish(topic, test_data)

        # Should receive message
        assert len(messages_received) == 1
        assert messages_received[0] == test_data

    def test_message_deduplication(self):
        """Duplicate messages are filtered"""
        router = GossipsubRouter()

        messages_received = []

        def handler(data: bytes):
            messages_received.append(data)

        topic = "/swarm/thread/test/decide"
        router.subscribe(topic, handler)

        # Create message
        msg = GossipsubMessage.create(topic, b"data", "peer1", 1)

        # Handle same message twice
        router.handle_message(msg)
        router.handle_message(msg)

        # Should only receive once
        assert len(messages_received) == 1

    def test_peer_management(self):
        """Can add and remove peers"""
        router = GossipsubRouter()

        router.add_peer("peer-1")
        router.add_peer("peer-2")

        assert "peer-1" in router.peers
        assert "peer-2" in router.peers

        router.remove_peer("peer-1")

        assert "peer-1" not in router.peers
        assert "peer-2" in router.peers

    def test_mesh_formation(self):
        """Mesh forms when subscribing"""
        router = GossipsubRouter()

        # Add some peers
        for i in range(5):
            router.add_peer(f"peer-{i}")

        topic = "/swarm/thread/test/commit"
        router.subscribe(topic, lambda d: None)

        # Should have mesh
        assert topic in router.mesh

    def test_get_peers_in_topic(self):
        """Can get peers in topic mesh"""
        router = GossipsubRouter()

        # Add peers
        for i in range(3):
            router.add_peer(f"peer-{i}")

        topic = "/swarm/thread/test/attest"
        router.subscribe(topic, lambda d: None)

        peers = router.get_peers_in_topic(topic)

        assert isinstance(peers, list)
        # Peers should be in mesh (up to D limit)
        assert len(peers) <= router.D

    def test_message_propagation_multi_node(self):
        """Messages propagate between nodes"""
        # Create 3 routers (simulating 3 nodes)
        router1 = GossipsubRouter()
        router2 = GossipsubRouter()
        router3 = GossipsubRouter()

        # Connect routers (simplified)
        router1.add_peer("peer-2")
        router1.add_peer("peer-3")
        router2.add_peer("peer-1")
        router2.add_peer("peer-3")
        router3.add_peer("peer-1")
        router3.add_peer("peer-2")

        # Track messages
        router2_messages = []
        router3_messages = []

        topic = "/swarm/thread/test/finalize"

        # Subscribe on router2 and router3
        router2.subscribe(topic, lambda d: router2_messages.append(d))
        router3.subscribe(topic, lambda d: router3_messages.append(d))

        # Publish on router1
        test_data = b"propagated message"
        router1.publish(topic, test_data)

        # Simulate propagation by manually handling messages
        # In real implementation, would use network
        msg = list(router1.seen_messages.values())[0]
        router2.handle_message(msg)
        router3.handle_message(msg)

        # Both should receive
        assert len(router2_messages) == 1
        assert len(router3_messages) == 1

    def test_heartbeat_maintenance(self):
        """Heartbeat performs maintenance"""
        router = GossipsubRouter()

        # Add peers
        for i in range(10):
            router.add_peer(f"peer-{i}")

        topic = "/swarm/thread/test/patch"
        router.subscribe(topic, lambda d: None)

        # Run heartbeat
        router.heartbeat()

        # Mesh should be maintained within limits
        mesh_size = len(router.mesh.get(topic, set()))
        assert mesh_size <= router.D_HIGH

    def test_router_stats(self):
        """Can get router statistics"""
        router = GossipsubRouter()

        router.subscribe("/test", lambda d: None)
        router.publish("/test", b"data")

        stats = router.get_stats()

        assert "subscriptions" in stats
        assert "mesh_topics" in stats
        assert "seen_messages" in stats
        assert stats["sequence"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
