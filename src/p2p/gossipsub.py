"""
Gossipsub Protocol Implementation

Provides topic-based pubsub with mesh networking and message propagation.
"""

import logging
import hashlib
import time
from typing import Dict, List, Callable, Set, Any
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GossipsubMessage:
    """Gossipsub message with metadata"""

    msg_id: str
    topic: str
    data: bytes
    from_peer: str
    sequence: int
    timestamp: float = field(default_factory=time.time)

    @classmethod
    def create(
        cls, topic: str, data: bytes, from_peer: str, sequence: int
    ) -> "GossipsubMessage":
        """Create message with computed ID"""
        # Message ID: hash(topic + data + from_peer + sequence)
        msg_str = f"{topic}{data.hex()}{from_peer}{sequence}"
        msg_id = hashlib.sha256(msg_str.encode()).hexdigest()[:16]

        return cls(
            msg_id=msg_id,
            topic=topic,
            data=data,
            from_peer=from_peer,
            sequence=sequence,
        )


@dataclass
class PeerScore:
    """Peer scoring for mesh quality"""

    peer_id: str
    score: float = 0.0
    messages_delivered: int = 0
    messages_invalid: int = 0
    last_seen: float = field(default_factory=time.time)

    def update_score(self):
        """Recalculate peer score"""
        # Simple scoring: delivered - invalid
        self.score = self.messages_delivered - (self.messages_invalid * 2)

        # Decay if not seen recently
        time_since_seen = time.time() - self.last_seen
        if time_since_seen > 60:  # 1 minute
            self.score *= 0.9


class GossipsubRouter:
    """
    Gossipsub protocol router with mesh networking.

    Implements a simplified gossipsub protocol for topic-based
    message propagation across peers.
    """

    # Mesh parameters
    D = 6  # Desired number of peers in mesh
    D_LOW = 4  # Lower bound for mesh peers
    D_HIGH = 12  # Upper bound for mesh peers
    D_LAZY = 6  # Number of peers to send gossip to

    # Timing parameters
    HEARTBEAT_INTERVAL = 1.0  # seconds
    SEEN_MSG_TTL = 120.0  # seconds

    def __init__(self, p2p_node=None):
        """
        Initialize gossipsub router.

        Args:
            p2p_node: P2P node instance (optional)
        """
        self.p2p_node = p2p_node

        # Topic subscriptions: topic -> handlers
        self.subscriptions: Dict[str, List[Callable]] = defaultdict(list)

        # Mesh membership: topic -> set of peer IDs
        self.mesh: Dict[str, Set[str]] = defaultdict(set)

        # Fanout: topic -> set of peer IDs (for topics we publish but don't subscribe)
        self.fanout: Dict[str, Set[str]] = defaultdict(set)

        # Message cache for deduplication: msg_id -> message
        self.seen_messages: Dict[str, GossipsubMessage] = {}

        # Peer scores: peer_id -> PeerScore
        self.peer_scores: Dict[str, PeerScore] = {}

        # All known peers: set of peer IDs
        self.peers: Set[str] = set()

        # Sequence counter for messages
        self.sequence = 0

        # Last heartbeat time
        self.last_heartbeat = time.time()

        logger.info("Gossipsub router initialized")

    def add_peer(self, peer_id: str):
        """Add a peer to the router"""
        if peer_id not in self.peers:
            self.peers.add(peer_id)
            self.peer_scores[peer_id] = PeerScore(peer_id=peer_id)
            logger.debug(f"Added peer: {peer_id}")

    def remove_peer(self, peer_id: str):
        """Remove a peer from the router"""
        if peer_id in self.peers:
            self.peers.remove(peer_id)

            # Remove from all meshes
            for topic_peers in self.mesh.values():
                topic_peers.discard(peer_id)

            # Remove from fanout
            for topic_peers in self.fanout.values():
                topic_peers.discard(peer_id)

            logger.debug(f"Removed peer: {peer_id}")

    def subscribe(self, topic: str, handler: Callable[[bytes], None]):
        """
        Subscribe to topic and register message handler.

        Args:
            topic: Topic to subscribe to
            handler: Callback function for messages
        """
        # Add handler
        if handler not in self.subscriptions[topic]:
            self.subscriptions[topic].append(handler)
            logger.info(f"Subscribed to topic: {topic}")

        # Join mesh if we have peers
        if topic not in self.mesh:
            self._join_mesh(topic)

    def unsubscribe(self, topic: str, handler: Callable[[bytes], None] = None):
        """
        Unsubscribe from topic.

        Args:
            topic: Topic to unsubscribe from
            handler: Specific handler to remove (None = remove all)
        """
        if handler:
            if handler in self.subscriptions[topic]:
                self.subscriptions[topic].remove(handler)
        else:
            self.subscriptions[topic].clear()

        # Leave mesh if no more handlers
        if not self.subscriptions[topic] and topic in self.mesh:
            self._leave_mesh(topic)
            logger.info(f"Unsubscribed from topic: {topic}")

    def publish(self, topic: str, message: bytes):
        """
        Publish message to topic.

        Args:
            topic: Topic to publish to
            message: Message data
        """
        self.sequence += 1

        # Create message
        from_peer = self.p2p_node.get_peer_id() if self.p2p_node else "local"
        msg = GossipsubMessage.create(topic, message, from_peer, self.sequence)

        # Add to seen messages
        self.seen_messages[msg.msg_id] = msg

        # Get peers to send to
        if topic in self.mesh:
            # We're in the mesh, send to mesh peers
            peers_to_send = self.mesh[topic]
        elif topic in self.fanout:
            # We have fanout peers
            peers_to_send = self.fanout[topic]
        else:
            # Create fanout
            peers_to_send = self._select_peers_for_fanout(topic)
            self.fanout[topic] = peers_to_send

        # Propagate to peers (simulated)
        logger.debug(
            f"Publishing to topic {topic}: {msg.msg_id} to {len(peers_to_send)} peers"
        )

        # Deliver locally if subscribed
        if topic in self.subscriptions:
            self._deliver_message(msg)

    def handle_message(self, msg: GossipsubMessage):
        """
        Handle received message.

        Args:
            msg: Received message
        """
        # Check for duplicates
        if msg.msg_id in self.seen_messages:
            logger.debug(f"Duplicate message: {msg.msg_id}")
            return

        # Add to seen messages
        self.seen_messages[msg.msg_id] = msg

        # Update peer score
        if msg.from_peer in self.peer_scores:
            self.peer_scores[msg.from_peer].messages_delivered += 1
            self.peer_scores[msg.from_peer].last_seen = time.time()
            self.peer_scores[msg.from_peer].update_score()

        # Deliver if subscribed
        if msg.topic in self.subscriptions:
            self._deliver_message(msg)

        # Propagate to mesh (if in mesh)
        if msg.topic in self.mesh:
            # Would forward to other mesh peers (except sender)
            pass

    def _deliver_message(self, msg: GossipsubMessage):
        """Deliver message to local handlers"""
        for handler in self.subscriptions.get(msg.topic, []):
            try:
                handler(msg.data)
            except Exception as e:
                logger.error(f"Handler error for {msg.topic}: {e}")

    def _join_mesh(self, topic: str):
        """Join mesh for topic"""
        # Select peers for mesh
        selected_peers = self._select_peers_for_mesh(topic)
        self.mesh[topic] = selected_peers

        logger.debug(f"Joined mesh for {topic} with {len(selected_peers)} peers")

    def _leave_mesh(self, topic: str):
        """Leave mesh for topic"""
        if topic in self.mesh:
            del self.mesh[topic]
            logger.debug(f"Left mesh for {topic}")

    def _select_peers_for_mesh(self, topic: str) -> Set[str]:
        """Select peers for mesh based on scores"""
        # Get available peers (excluding self)
        available_peers = list(self.peers)

        # Sort by score (best first)
        available_peers.sort(
            key=lambda p: self.peer_scores.get(p, PeerScore(p)).score, reverse=True
        )

        # Select up to D peers
        selected = set(available_peers[: self.D])

        return selected

    def _select_peers_for_fanout(self, topic: str) -> Set[str]:
        """Select peers for fanout"""
        # Similar to mesh selection
        return self._select_peers_for_mesh(topic)

    def get_peers_in_topic(self, topic: str) -> List[str]:
        """
        Get list of peers in topic mesh.

        Args:
            topic: Topic name

        Returns:
            List of peer IDs
        """
        return list(self.mesh.get(topic, set()))

    def heartbeat(self):
        """Perform periodic maintenance"""
        current_time = time.time()

        # Only heartbeat at interval
        if current_time - self.last_heartbeat < self.HEARTBEAT_INTERVAL:
            return

        self.last_heartbeat = current_time

        # Maintain mesh
        for topic in list(self.mesh.keys()):
            peers = self.mesh[topic]

            # Too few peers? Add more
            if len(peers) < self.D_LOW:
                additional = self._select_peers_for_mesh(topic) - peers
                peers.update(list(additional)[: self.D - len(peers)])

            # Too many peers? Remove some
            elif len(peers) > self.D_HIGH:
                to_remove = len(peers) - self.D
                # Remove lowest-scored peers
                sorted_peers = sorted(
                    peers, key=lambda p: self.peer_scores.get(p, PeerScore(p)).score
                )
                for peer in sorted_peers[:to_remove]:
                    peers.remove(peer)

        # Clean up old seen messages
        cutoff_time = current_time - self.SEEN_MSG_TTL
        old_msg_ids = [
            msg_id
            for msg_id, msg in self.seen_messages.items()
            if msg.timestamp < cutoff_time
        ]
        for msg_id in old_msg_ids:
            del self.seen_messages[msg_id]

        logger.debug(
            f"Heartbeat: {len(self.mesh)} topics, {len(self.seen_messages)} seen messages"
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get router statistics"""
        return {
            "subscriptions": len(self.subscriptions),
            "mesh_topics": len(self.mesh),
            "total_peers": len(self.peers),
            "seen_messages": len(self.seen_messages),
            "sequence": self.sequence,
        }
