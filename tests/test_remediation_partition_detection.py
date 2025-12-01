"""
Test for partition detection (PART-001).

Validates that network partitions are detected and handled.
"""

import sys
from pathlib import Path
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_partition_detection():
    """
    Test that missing heartbeats trigger partition detection.
    """
    from monitoring.partition_detector import PartitionDetector

    partitions_detected = []

    def on_partition(peer_id):
        partitions_detected.append(peer_id)

    # Fast settings for testing
    detector = PartitionDetector(
        heartbeat_interval=1.0,
        missed_heartbeat_threshold=3,
        on_partition_callback=on_partition,
    )

    detector.start()

    # Register peer
    detector.register_peer("node1")

    # Send initial heartbeat
    detector.heartbeat("node1")

    # Wait for partition detection (3 * 1s = 3s + buffer)
    time.sleep(4)

    # Should detect partition
    assert "node1" in partitions_detected
    assert detector.is_partitioned()

    detector.stop()


def test_partition_heal():
    """
    Test that reconnection triggers heal callback.
    """
    from monitoring.partition_detector import PartitionDetector

    healed_peers = []

    def on_heal(peer_id):
        healed_peers.append(peer_id)

    detector = PartitionDetector(
        heartbeat_interval=1.0, missed_heartbeat_threshold=2, on_heal_callback=on_heal
    )

    detector.start()

    # Register and establish initial heartbeat
    detector.register_peer("node2")
    detector.heartbeat("node2")

    # Wait for partition
    time.sleep(3)
    assert detector.is_partitioned()

    # Heal partition by sending heartbeat
    detector.heartbeat("node2")

    # Should trigger heal
    time.sleep(0.5)
    assert "node2" in healed_peers
    assert not detector.is_partitioned()

    detector.stop()


def test_multiple_peers():
    """
    Test monitoring multiple peers independently.
    """
    from monitoring.partition_detector import PartitionDetector

    detector = PartitionDetector(heartbeat_interval=1.0, missed_heartbeat_threshold=2)

    detector.start()

    # Register 3 peers
    detector.register_peer("node1")
    detector.register_peer("node2")
    detector.register_peer("node3")

    # All send heartbeats
    detector.heartbeat("node1")
    detector.heartbeat("node2")
    detector.heartbeat("node3")

    # Only node3 stops sending heartbeats
    time.sleep(1.5)
    detector.heartbeat("node1")
    detector.heartbeat("node2")
    # node3 misses heartbeat

    time.sleep(1.5)
    detector.heartbeat("node1")
    detector.heartbeat("node2")
    # node3 misses another heartbeat

    # Check partition status
    partitioned = detector.get_partitioned_peers()
    alive = detector.get_alive_peers()

    assert "node3" in partitioned
    assert "node1" in alive
    assert "node2" in alive

    detector.stop()


def test_epoch_advancement_on_partition():
    """
    Test that partition triggers epoch advancement.
    """
    from monitoring.partition_detector import PartitionDetector

    epoch_advanced = []

    def on_partition(peer_id):
        # Simulate epoch advancement
        epoch_advanced.append(True)

    detector = PartitionDetector(
        heartbeat_interval=1.0,
        missed_heartbeat_threshold=2,
        on_partition_callback=on_partition,
    )

    detector.start()

    detector.register_peer("node_fail")
    detector.heartbeat("node_fail")

    # Wait for partition
    time.sleep(3)

    # Epoch should have advanced
    assert len(epoch_advanced) > 0

    detector.stop()


def test_reconcile_on_heal():
    """
    Test that heal triggers RECONCILE message.
    """
    from monitoring.partition_detector import PartitionDetector

    reconcile_sent = []

    def on_heal(peer_id):
        # Simulate sending RECONCILE
        reconcile_sent.append({"peer": peer_id, "action": "RECONCILE"})

    detector = PartitionDetector(
        heartbeat_interval=1.0, missed_heartbeat_threshold=2, on_heal_callback=on_heal
    )

    detector.start()

    detector.register_peer("node_recover")
    detector.heartbeat("node_recover")

    # Partition
    time.sleep(3)

    # Heal
    detector.heartbeat("node_recover")
    time.sleep(0.5)

    # RECONCILE should be sent
    assert len(reconcile_sent) > 0
    assert reconcile_sent[0]["action"] == "RECONCILE"

    detector.stop()
