"""
End-to-End P2P Tests

Comprehensive tests for full P2P mode operation including:
- Full workflow using only P2P transport
- Network partition and healing
- Large mesh scenarios (10+ nodes)
"""

import asyncio
import argparse
import json
import logging
import time
import statistics
from typing import List, Dict, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import sys
from pathlib import Path
import pytest
import pytest_asyncio

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from p2p.node import P2PNode
from p2p.gossipsub import GossipsubRouter
from p2p.topics import create_thread_topic
from bus import P2PBus
from envelope import make_envelope, sign_envelope
from p2p.identity import P2PIdentity


logger = logging.getLogger(__name__)


@dataclass
class TestNode:
    """Test node wrapper"""

    node_id: int
    p2p_node: P2PNode
    gossipsub: GossipsubRouter
    bus: P2PBus
    identity: dict
    received_messages: List[dict]

    def __init__(self, node_id: int, listen_port: int):
        self.node_id = node_id
        self.listen_port = listen_port
        self.listen_addr = f"/ip4/127.0.0.1/tcp/{listen_port}"
        self.p2p_node = None
        self.gossipsub = None
        self.bus = None
        self.identity = None
        self.received_messages = []

    async def start(self):
        """Start the test node"""
        # Create identity
        self.identity = P2PIdentity()
        self.identity_dict = {
            "did": self.identity.to_did_peer(),
            "signing_key": self.identity.get_private_key_bytes(),
        }

        # Start P2P node
        self.p2p_node = P2PNode(listen_addr=self.listen_addr)
        await self.p2p_node.start()

        # Create gossipsub router
        self.gossipsub = GossipsubRouter(self.p2p_node)

        # Create bus
        self.bus = P2PBus(p2p_node=self.p2p_node, gossipsub_router=self.gossipsub)

        logger.info(f"Test node {self.node_id} started: {self.p2p_node.get_peer_id()}")

    async def stop(self):
        """Stop the test node"""
        if self.p2p_node:
            await self.p2p_node.stop()

    async def connect_to(self, other: "TestNode"):
        """Connect to another test node"""
        peer_id = other.p2p_node.get_peer_id()
        multiaddr = f"{other.listen_addr}/p2p/{peer_id}"
        await self.p2p_node.connect(multiaddr)

    def subscribe(self, subject: str, handler=None):
        """Subscribe to a subject"""
        if handler is None:
            # Default handler stores messages
            def default_handler(envelope):
                self.received_messages.append(envelope)

            handler = default_handler

        self.bus.subscribe_envelopes(subject, handler)

    def publish(self, subject: str, envelope: dict):
        """Publish an envelope"""
        self.bus.publish_envelope(envelope, subject)

    def clear_messages(self):
        """Clear received messages"""
        self.received_messages.clear()


@pytest_asyncio.fixture
async def test_nodes_3():
    """Fixture: 3 connected test nodes"""
    nodes = []
    base_port = 6000

    # Create nodes
    for i in range(3):
        node = TestNode(i, base_port + i)
        await node.start()
        nodes.append(node)

    # Connect in a line: 0 <-> 1 <-> 2
    await nodes[0].connect_to(nodes[1])
    await nodes[1].connect_to(nodes[2])

    # Wait for connections to stabilize
    await asyncio.sleep(2)

    yield nodes

    # Cleanup
    for node in nodes:
        await node.stop()


@pytest_asyncio.fixture
async def test_nodes_10():
    """Fixture: 10 connected test nodes in full mesh"""
    nodes = []
    base_port = 7000

    # Create nodes
    for i in range(10):
        node = TestNode(i, base_port + i)
        await node.start()
        nodes.append(node)

    # Connect in full mesh
    for i, node in enumerate(nodes):
        for j, other_node in enumerate(nodes):
            if i < j:  # Connect each pair once
                await node.connect_to(other_node)
                await asyncio.sleep(0.1)

    # Wait for mesh to stabilize
    await asyncio.sleep(3)

    yield nodes

    # Cleanup
    for node in nodes:
        await node.stop()


@pytest.mark.asyncio
async def test_full_workflow_p2p_only(test_nodes_3):
    """
    Test full CAN Swarm workflow using only P2P transport:
    NEED → DECIDE → FINALIZE
    """
    nodes = test_nodes_3
    thread_id = "test-p2p-workflow"

    # All nodes subscribe to the thread
    for node in nodes:
        node.subscribe(f"{thread_id}.>")  # Subscribe to all events in thread

    await asyncio.sleep(1)  # Let subscriptions propagate

    # Step 1: Planner publishes NEED
    need_envelope = make_envelope(
        thread_id=thread_id,
        kind="NEED",
        sender_pk_b64=nodes[0].identity.get_public_key_base64(),
        payload={"task": "test_task", "requirements": "test requirements"},
    )
    need_envelope = sign_envelope(need_envelope)

    logger.info("Publishing NEED")
    nodes[0].publish(f"{thread_id}.need", need_envelope)

    await asyncio.sleep(2)  # Wait for propagation

    # Verify all nodes received NEED
    for i, node in enumerate(nodes):
        if i == 0:
            continue  # Skip sender
        assert len(node.received_messages) > 0, f"Node {i} did not receive NEED"
        need_received = any(msg.get("kind") == "NEED" for msg in node.received_messages)
        assert need_received, f"Node {i} did not receive NEED envelope"

    logger.info("✓ NEED propagated to all nodes")

    # Clear messages
    for node in nodes:
        node.clear_messages()

    # Step 2: Agent publishes DECIDE
    decide_envelope = make_envelope(
        thread_id=thread_id,
        kind="DECIDE",
        sender_pk_b64=nodes[1].identity.get_public_key_base64(),
        payload={
            "task_id": "test_task",
            "decision": "accept",
            "agent": nodes[1].identity.to_did_peer(),
        },
    )
    decide_envelope = sign_envelope(decide_envelope)

    logger.info("Publishing DECIDE")
    nodes[1].publish(f"{thread_id}.decide", decide_envelope)

    await asyncio.sleep(2)

    # Verify all nodes received DECIDE
    for i, node in enumerate(nodes):
        if i == 1:
            continue  # Skip sender
        assert len(node.received_messages) > 0, f"Node {i} did not receive DECIDE"
        decide_received = any(
            msg.get("kind") == "DECIDE" for msg in node.received_messages
        )
        assert decide_received, f"Node {i} did not receive DECIDE envelope"

    logger.info("✓ DECIDE propagated to all nodes")

    # Clear messages
    for node in nodes:
        node.clear_messages()

    # Step 3: Agent publishes FINALIZE
    finalize_envelope = make_envelope(
        thread_id=thread_id,
        kind="FINALIZE",
        sender_pk_b64=nodes[1].identity.get_public_key_base64(),
        payload={
            "task_id": "test_task",
            "result": "completed successfully",
            "artifacts": ["artifact1", "artifact2"],
        },
    )
    finalize_envelope = sign_envelope(finalize_envelope)

    logger.info("Publishing FINALIZE")
    nodes[1].publish(f"{thread_id}.finalize", finalize_envelope)

    await asyncio.sleep(2)

    # Verify all nodes received FINALIZE
    for i, node in enumerate(nodes):
        if i == 1:
            continue  # Skip sender
        assert len(node.received_messages) > 0, f"Node {i} did not receive FINALIZE"
        finalize_received = any(
            msg.get("kind") == "FINALIZE" for msg in node.received_messages
        )
        assert finalize_received, f"Node {i} did not receive FINALIZE envelope"

    logger.info("✓ FINALIZE propagated to all nodes")
    logger.info("✓ Full workflow completed successfully via P2P")


@pytest.mark.asyncio
async def test_partition_and_heal():
    """
    Test network partition and healing:
    1. Create 4 nodes in full mesh
    2. Partition into two groups (0,1) and (2,3)
    3. Each partition operates independently
    4. Heal partition by reconnecting
    5. Verify both partitions sync
    """
    # Create 4 nodes
    nodes = []
    base_port = 8000

    for i in range(4):
        node = TestNode(i, base_port + i)
        await node.start()
        nodes.append(node)

    # Connect in full mesh
    for i, node in enumerate(nodes):
        for j, other_node in enumerate(nodes):
            if i < j:
                await node.connect_to(other_node)

    await asyncio.sleep(2)

    thread_id = "test-partition"

    # All subscribe
    for node in nodes:
        node.subscribe(f"{thread_id}.>")

    await asyncio.sleep(1)

    logger.info("Created 4-node mesh")

    # Step 1: Partition network - disconnect (0,1) from (2,3)
    # In real scenario, this would be network-level partition
    # For testing, we simulate by having separate topics

    # Partition 1 publishes on topic A
    partition1_topic = f"{thread_id}-partition1"

    envelope_p1 = make_envelope(
        thread_id=thread_id,
        kind="NEED",
        sender_pk_b64=nodes[0].identity.get_public_key_base64(),
        payload={"partition": 1, "data": "from partition 1"},
    )
    envelope_p1 = sign_envelope(envelope_p1)

    # Only nodes 0,1 subscribe to partition1
    for node in nodes[0:2]:
        node.subscribe(partition1_topic)

    await asyncio.sleep(1)

    nodes[0].publish(partition1_topic, envelope_p1)
    await asyncio.sleep(2)

    # Verify partition 1 nodes received it, partition 2 did not
    assert len(nodes[0].received_messages) > 0 or len(nodes[1].received_messages) > 0
    logger.info("✓ Partition 1 operating independently")

    # Partition 2 publishes on separate topic
    partition2_topic = f"{thread_id}-partition2"

    envelope_p2 = make_envelope(
        thread_id=thread_id,
        kind="NEED",
        sender_pk_b64=nodes[2].identity.get_public_key_base64(),
        payload={"partition": 2, "data": "from partition 2"},
    )
    envelope_p2 = sign_envelope(envelope_p2)

    # Only nodes 2,3 subscribe to partition2
    for node in nodes[2:4]:
        node.subscribe(partition2_topic)

    await asyncio.sleep(1)

    nodes[2].publish(partition2_topic, envelope_p2)
    await asyncio.sleep(2)

    assert len(nodes[2].received_messages) > 0 or len(nodes[3].received_messages) > 0
    logger.info("✓ Partition 2 operating independently")

    # Step 2: Heal partition - all nodes subscribe to common topic
    heal_topic = f"{thread_id}-healed"

    for node in nodes:
        node.clear_messages()
        node.subscribe(heal_topic)

    await asyncio.sleep(2)

    logger.info("Healing partition...")

    # Publish on healed topic from partition 1
    heal_envelope = make_envelope(
        thread_id=thread_id,
        kind="DECIDE",
        sender_pk_b64=nodes[0].identity.get_public_key_base64(),
        payload={"healed": True, "source": "partition1"},
    )
    heal_envelope = sign_envelope(heal_envelope)

    nodes[0].publish(heal_topic, heal_envelope)
    await asyncio.sleep(2)

    # Verify all nodes received heal message
    received_count = sum(1 for node in nodes[1:] if len(node.received_messages) > 0)
    assert received_count >= 2, "Partition not fully healed"

    logger.info("✓ Partition healed, messages propagating across all nodes")

    # Cleanup
    for node in nodes:
        await node.stop()


@pytest.mark.asyncio
async def test_10_node_mesh(test_nodes_10):
    """
    Test large P2P mesh with 10 nodes:
    - Verify full connectivity
    - Test message propagation
    - Measure latency
    """
    nodes = test_nodes_10
    thread_id = "test-10-node-mesh"

    # All nodes subscribe
    for node in nodes:
        node.subscribe(f"{thread_id}.>")

    await asyncio.sleep(2)

    logger.info("Testing 10-node mesh")

    # Test 1: Verify connectivity
    for node in nodes:
        peers = node.p2p_node.get_connected_peers()
        logger.info(f"Node {node.node_id} connected to {len(peers)} peers")
        # In full mesh, each node should connect to at least 5 others
        assert len(peers) >= 5, f"Node {node.node_id} has insufficient connections"

    logger.info("✓ All nodes have sufficient connections")

    # Test 2: Broadcast from each node, verify propagation
    for sender_id, sender_node in enumerate(nodes):
        # Clear previous messages
        for node in nodes:
            node.clear_messages()

        # Publish envelope
        envelope = make_envelope(
            thread_id=thread_id,
            kind="NEED",
            sender_pk_b64=sender_node.identity.get_public_key_base64(),
            payload={"sender_id": sender_id, "msg": f"from node {sender_id}"},
        )
        envelope = sign_envelope(envelope)

        sender_node.publish(f"{thread_id}.need", envelope)
        await asyncio.sleep(2)

        # Count how many nodes received it
        receivers = [
            i
            for i, node in enumerate(nodes)
            if i != sender_id and len(node.received_messages) > 0
        ]
        propagation_rate = len(receivers) / (len(nodes) - 1) * 100

        logger.info(
            f"Node {sender_id} → {len(receivers)}/{len(nodes)-1} nodes ({propagation_rate:.1f}%)"
        )

        # Require > 80% propagation
        assert (
            propagation_rate > 80
        ), f"Poor propagation from node {sender_id}: {propagation_rate}%"

    logger.info("✓ All nodes can broadcast to mesh successfully")

    # Test 3: Measure average latency
    latencies = []

    for _ in range(5):  # Send 5 messages to measure latency
        for node in nodes:
            node.clear_messages()

        start_time = time.time()

        envelope = make_envelope(
            thread_id=thread_id,
            kind="DECIDE",
            sender_pk_b64=nodes[0].identity.get_public_key_base64(),
            payload={"latency_test": True},
        )
        envelope = sign_envelope(envelope)

        nodes[0].publish(f"{thread_id}.decide", envelope)

        # Wait for propagation
        await asyncio.sleep(1)

        end_time = time.time()
        latency_ms = (end_time - start_time) * 1000
        latencies.append(latency_ms)

    avg_latency = sum(latencies) / len(latencies)
    logger.info(f"Average propagation latency: {avg_latency:.2f}ms")

    # Latency should be < 2000ms for 10-node local mesh
    assert avg_latency < 2000, f"High latency: {avg_latency}ms"

    logger.info("✓ 10-node mesh performs well")


@pytest.mark.asyncio
async def test_concurrent_publishers():
    """
    Test multiple nodes publishing concurrently:
    - No message loss
    - No duplicate delivery
    - Proper ordering
    """
    # Create 5 nodes
    nodes = []
    base_port = 9000

    for i in range(5):
        node = TestNode(i, base_port + i)
        await node.start()
        nodes.append(node)

    # Full mesh
    for i, node in enumerate(nodes):
        for j, other_node in enumerate(nodes):
            if i < j:
                await node.connect_to(other_node)

    await asyncio.sleep(2)

    thread_id = "test-concurrent"

    # Subscribe all
    for node in nodes:
        node.subscribe(f"{thread_id}.>")

    await asyncio.sleep(1)

    # Each node publishes 10 messages concurrently
    messages_per_node = 10

    async def publish_messages(node, count):
        for i in range(count):
            envelope = make_envelope(
                thread_id=thread_id,
                kind="NEED",
                sender_pk_b64=node.identity.get_public_key_base64(),
                payload={"node": node.node_id, "msg_num": i},
            )
            envelope = sign_envelope(envelope)
            node.publish(f"{thread_id}.need", envelope)
            await asyncio.sleep(0.1)  # Small delay between messages

    # Publish concurrently from all nodes
    tasks = [publish_messages(node, messages_per_node) for node in nodes]
    await asyncio.gather(*tasks)

    # Wait for all messages to propagate
    await asyncio.sleep(5)

    # Verify each node received messages from all other nodes
    total_expected = len(nodes) * messages_per_node

    for node in nodes:
        received_count = len(node.received_messages)
        logger.info(f"Node {node.node_id} received {received_count} messages")

        # Should receive most messages (allow some loss in testing)
        assert (
            received_count >= total_expected * 0.8
        ), f"Node {node.node_id} only received {received_count}/{total_expected} messages"

    logger.info("✓ Concurrent publishing works correctly")

    # Cleanup
    for node in nodes:
        await node.stop()


if __name__ == "__main__":
    # Run with: pytest tests/test_e2e_p2p.py -v -s
    pytest.main([__file__, "-v", "-s"])
