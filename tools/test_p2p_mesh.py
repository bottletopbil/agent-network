#!/usr/bin/env python3
"""
P2P Mesh Testing Tool

This tool spawns multiple P2P nodes, connects them via libp2p,
publishes NEEDs, verifies propagation, and measures performance metrics.

Usage:
    python tools/test_p2p_mesh.py --nodes 10 --duration 60
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
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.p2p.node import P2PNode
from src.p2p.gossipsub import GossipsubRouter
from src.p2p.topics import create_thread_topic
from src.envelope import create_envelope

logger = logging.getLogger(__name__)


@dataclass
class MessageTracker:
    """Track message propagation across the mesh"""
    message_id: str
    sender_node: int
    send_time: float
    received_by: Set[int] = field(default_factory=set)
    reception_times: Dict[int, float] = field(default_factory=dict)
    
    def record_reception(self, node_id: int, reception_time: float):
        """Record when a node received this message"""
        self.received_by.add(node_id)
        self.reception_times[node_id] = reception_time
    
    def latency_to_node(self, node_id: int) -> float:
        """Get latency to specific node in milliseconds"""
        if node_id in self.reception_times:
            return (self.reception_times[node_id] - self.send_time) * 1000
        return None
    
    def average_latency(self) -> float:
        """Get average propagation latency in milliseconds"""
        if not self.reception_times:
            return 0.0
        latencies = [(t - self.send_time) * 1000 for t in self.reception_times.values()]
        return statistics.mean(latencies)
    
    def propagation_rate(self, total_nodes: int) -> float:
        """Get percentage of nodes that received the message"""
        # Exclude sender from total
        return len(self.received_by) / (total_nodes - 1) * 100 if total_nodes > 1 else 0.0


@dataclass
class MeshStats:
    """Statistics for the entire mesh"""
    total_messages: int = 0
    total_receptions: int = 0
    latencies: List[float] = field(default_factory=list)
    propagation_rates: List[float] = field(default_factory=list)
    failed_propagations: int = 0
    
    def record_message(self, tracker: MessageTracker, total_nodes: int):
        """Record statistics for a message"""
        self.total_messages += 1
        self.total_receptions += len(tracker.received_by)
        
        avg_latency = tracker.average_latency()
        if avg_latency > 0:
            self.latencies.append(avg_latency)
        
        prop_rate = tracker.propagation_rate(total_nodes)
        self.propagation_rates.append(prop_rate)
        
        # Consider propagation failed if < 90% of nodes received it
        if prop_rate < 90.0:
            self.failed_propagations += 1
    
    def summary(self) -> Dict:
        """Get summary statistics"""
        return {
            "total_messages": self.total_messages,
            "total_receptions": self.total_receptions,
            "failed_propagations": self.failed_propagations,
            "latency_ms": {
                "min": min(self.latencies) if self.latencies else 0,
                "max": max(self.latencies) if self.latencies else 0,
                "mean": statistics.mean(self.latencies) if self.latencies else 0,
                "median": statistics.median(self.latencies) if self.latencies else 0,
                "p95": statistics.quantiles(self.latencies, n=20)[18] if len(self.latencies) > 20 else 0,
                "p99": statistics.quantiles(self.latencies, n=100)[98] if len(self.latencies) > 100 else 0,
            },
            "propagation_rate": {
                "min": min(self.propagation_rates) if self.propagation_rates else 0,
                "max": max(self.propagation_rates) if self.propagation_rates else 0,
                "mean": statistics.mean(self.propagation_rates) if self.propagation_rates else 0,
            }
        }


class MeshNode:
    """Wrapper for a P2P node in the test mesh"""
    
    def __init__(self, node_id: int, listen_port: int):
        self.node_id = node_id
        self.listen_port = listen_port
        self.listen_addr = f"/ip4/127.0.0.1/tcp/{listen_port}"
        self.p2p_node = None
        self.gossipsub = None
        self.received_messages: Set[str] = set()
        self.message_handlers: List = []
    
    async def start(self):
        """Start the P2P node"""
        logger.info(f"Starting node {self.node_id} on {self.listen_addr}")
        self.p2p_node = P2PNode(listen_addr=self.listen_addr)
        await self.p2p_node.start()
        self.gossipsub = GossipsubRouter(self.p2p_node)
        logger.info(f"Node {self.node_id} started with peer ID: {self.p2p_node.get_peer_id()}")
    
    async def stop(self):
        """Stop the P2P node"""
        logger.info(f"Stopping node {self.node_id}")
        if self.p2p_node:
            await self.p2p_node.stop()
    
    async def connect_to(self, other_node: 'MeshNode'):
        """Connect to another node"""
        if not other_node.p2p_node:
            raise ValueError(f"Target node {other_node.node_id} not started")
        
        peer_id = other_node.p2p_node.get_peer_id()
        multiaddr = f"{other_node.listen_addr}/p2p/{peer_id}"
        
        logger.debug(f"Node {self.node_id} connecting to node {other_node.node_id} at {multiaddr}")
        await self.p2p_node.connect(multiaddr)
    
    def subscribe(self, topic: str, handler):
        """Subscribe to a topic"""
        logger.debug(f"Node {self.node_id} subscribing to {topic}")
        self.gossipsub.subscribe(topic, handler)
    
    def publish(self, topic: str, message: bytes):
        """Publish a message to a topic"""
        logger.debug(f"Node {self.node_id} publishing to {topic}")
        self.gossipsub.publish(topic, message)
    
    def get_stats(self) -> Dict:
        """Get node statistics"""
        return {
            "node_id": self.node_id,
            "peer_id": self.p2p_node.get_peer_id() if self.p2p_node else None,
            "messages_received": len(self.received_messages),
            "connected_peers": len(self.p2p_node.get_connected_peers()) if self.p2p_node else 0,
        }


class P2PMeshTest:
    """P2P Mesh Test Orchestrator"""
    
    def __init__(self, num_nodes: int, base_port: int = 5000):
        self.num_nodes = num_nodes
        self.base_port = base_port
        self.nodes: List[MeshNode] = []
        self.message_trackers: Dict[str, MessageTracker] = {}
        self.stats = MeshStats()
        self.test_thread_id = f"test-mesh-{int(time.time())}"
    
    async def setup_mesh(self):
        """Create and start all nodes"""
        logger.info(f"Setting up mesh with {self.num_nodes} nodes")
        
        # Create all nodes
        for i in range(self.num_nodes):
            node = MeshNode(i, self.base_port + i)
            self.nodes.append(node)
        
        # Start all nodes
        start_tasks = [node.start() for node in self.nodes]
        await asyncio.gather(*start_tasks)
        
        logger.info("All nodes started")
    
    async def connect_mesh(self, topology: str = "full"):
        """Connect nodes in specified topology"""
        logger.info(f"Connecting mesh with {topology} topology")
        
        if topology == "full":
            # Full mesh: every node connects to every other node
            for i, node in enumerate(self.nodes):
                for j, other_node in enumerate(self.nodes):
                    if i < j:  # Only connect once (bidirectional)
                        await node.connect_to(other_node)
                        await asyncio.sleep(0.1)  # Small delay to avoid overwhelming
        
        elif topology == "ring":
            # Ring: each node connects to next node (circular)
            for i, node in enumerate(self.nodes):
                next_node = self.nodes[(i + 1) % self.num_nodes]
                await node.connect_to(next_node)
                await asyncio.sleep(0.1)
        
        elif topology == "star":
            # Star: all nodes connect to node 0
            hub = self.nodes[0]
            for node in self.nodes[1:]:
                await node.connect_to(hub)
                await asyncio.sleep(0.1)
        
        logger.info(f"Mesh connected with {topology} topology")
        await asyncio.sleep(2)  # Let DHT stabilize
    
    def subscribe_all(self, topic: str):
        """Subscribe all nodes to a topic"""
        logger.info(f"Subscribing all {self.num_nodes} nodes to {topic}")
        
        for node in self.nodes:
            def make_handler(node_id):
                def handler(message_bytes: bytes):
                    try:
                        message = json.loads(message_bytes.decode('utf-8'))
                        msg_id = message.get('message_id', 'unknown')
                        
                        # Track reception
                        if msg_id in self.message_trackers:
                            tracker = self.message_trackers[msg_id]
                            tracker.record_reception(node_id, time.time())
                        
                        # Record that this node received it
                        self.nodes[node_id].received_messages.add(msg_id)
                        
                        logger.debug(f"Node {node_id} received message {msg_id}")
                    except Exception as e:
                        logger.error(f"Error in handler for node {node_id}: {e}")
                
                return handler
            
            node.subscribe(topic, make_handler(node.node_id))
        
        logger.info("All nodes subscribed")
    
    async def publish_test_message(self, sender_node_id: int, topic: str, payload: Dict) -> str:
        """Publish a test message from a specific node"""
        message_id = f"msg-{sender_node_id}-{int(time.time() * 1000000)}"
        
        message = {
            "message_id": message_id,
            "sender": sender_node_id,
            "timestamp": time.time(),
            "payload": payload
        }
        
        # Create tracker
        tracker = MessageTracker(
            message_id=message_id,
            sender_node=sender_node_id,
            send_time=time.time()
        )
        self.message_trackers[message_id] = tracker
        
        # Publish
        message_bytes = json.dumps(message).encode('utf-8')
        self.nodes[sender_node_id].publish(topic, message_bytes)
        
        logger.info(f"Published message {message_id} from node {sender_node_id}")
        return message_id
    
    async def run_propagation_test(self, num_messages: int = 10, interval: float = 1.0):
        """Run message propagation test"""
        logger.info(f"Running propagation test: {num_messages} messages, {interval}s interval")
        
        topic = create_thread_topic(self.test_thread_id, "need")
        self.subscribe_all(topic)
        
        # Wait for subscriptions to propagate
        await asyncio.sleep(2)
        
        # Publish messages from random nodes
        for i in range(num_messages):
            sender = i % self.num_nodes  # Round-robin across nodes
            payload = {
                "test_number": i,
                "description": f"Test NEED {i}",
                "data": "x" * 100  # ~100 bytes payload
            }
            
            await self.publish_test_message(sender, topic, payload)
            await asyncio.sleep(interval)
        
        # Wait for propagation
        logger.info("Waiting for message propagation...")
        await asyncio.sleep(5)
        
        # Analyze results
        for msg_id, tracker in self.message_trackers.items():
            self.stats.record_message(tracker, self.num_nodes)
    
    async def run_throughput_test(self, duration: int = 30, target_rate: int = 10):
        """Run throughput test"""
        logger.info(f"Running throughput test: {duration}s at {target_rate} msg/s")
        
        topic = create_thread_topic(self.test_thread_id, "need")
        self.subscribe_all(topic)
        await asyncio.sleep(2)
        
        start_time = time.time()
        message_count = 0
        interval = 1.0 / target_rate
        
        while time.time() - start_time < duration:
            sender = message_count % self.num_nodes
            payload = {
                "test_number": message_count,
                "throughput_test": True
            }
            
            await self.publish_test_message(sender, topic, payload)
            message_count += 1
            await asyncio.sleep(interval)
        
        # Wait for propagation
        await asyncio.sleep(5)
        
        # Analyze results
        for msg_id, tracker in self.message_trackers.items():
            self.stats.record_message(tracker, self.num_nodes)
        
        elapsed = time.time() - start_time
        actual_rate = message_count / elapsed
        logger.info(f"Sent {message_count} messages in {elapsed:.2f}s ({actual_rate:.2f} msg/s)")
    
    async def teardown(self):
        """Stop all nodes"""
        logger.info("Tearing down mesh")
        stop_tasks = [node.stop() for node in self.nodes]
        await asyncio.gather(*stop_tasks)
        logger.info("All nodes stopped")
    
    def print_report(self):
        """Print test report"""
        print("\n" + "=" * 80)
        print("P2P MESH TEST REPORT")
        print("=" * 80)
        print(f"\nMesh Configuration:")
        print(f"  Nodes: {self.num_nodes}")
        print(f"  Test Thread: {self.test_thread_id}")
        
        print(f"\nMessage Statistics:")
        summary = self.stats.summary()
        print(f"  Total Messages: {summary['total_messages']}")
        print(f"  Total Receptions: {summary['total_receptions']}")
        print(f"  Failed Propagations: {summary['failed_propagations']}")
        
        print(f"\nLatency (ms):")
        lat = summary['latency_ms']
        print(f"  Min: {lat['min']:.2f}")
        print(f"  Mean: {lat['mean']:.2f}")
        print(f"  Median: {lat['median']:.2f}")
        print(f"  Max: {lat['max']:.2f}")
        print(f"  P95: {lat['p95']:.2f}")
        print(f"  P99: {lat['p99']:.2f}")
        
        print(f"\nPropagation Rate (%):")
        prop = summary['propagation_rate']
        print(f"  Min: {prop['min']:.2f}")
        print(f"  Mean: {prop['mean']:.2f}")
        print(f"  Max: {prop['max']:.2f}")
        
        print(f"\nNode Statistics:")
        for node in self.nodes:
            stats = node.get_stats()
            print(f"  Node {stats['node_id']}: {stats['messages_received']} msgs, "
                  f"{stats['connected_peers']} peers")
        
        print("\n" + "=" * 80)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="P2P Mesh Testing Tool")
    parser.add_argument("--nodes", type=int, default=5, help="Number of nodes (default: 5)")
    parser.add_argument("--topology", choices=["full", "ring", "star"], default="full",
                       help="Mesh topology (default: full)")
    parser.add_argument("--test", choices=["propagation", "throughput", "both"], default="both",
                       help="Test type (default: both)")
    parser.add_argument("--messages", type=int, default=10, help="Number of messages for propagation test")
    parser.add_argument("--duration", type=int, default=30, help="Duration for throughput test (seconds)")
    parser.add_argument("--rate", type=int, default=10, help="Target message rate (msg/s)")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    # Create test orchestrator
    mesh_test = P2PMeshTest(num_nodes=args.nodes)
    
    try:
        # Setup
        await mesh_test.setup_mesh()
        await mesh_test.connect_mesh(topology=args.topology)
        
        # Run tests
        if args.test in ["propagation", "both"]:
            await mesh_test.run_propagation_test(num_messages=args.messages)
        
        if args.test in ["throughput", "both"]:
            # Reset stats between tests
            if args.test == "both":
                mesh_test.stats = MeshStats()
                mesh_test.message_trackers.clear()
            
            await mesh_test.run_throughput_test(duration=args.duration, target_rate=args.rate)
        
        # Print report
        mesh_test.print_report()
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return 1
    
    finally:
        # Cleanup
        await mesh_test.teardown()
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
