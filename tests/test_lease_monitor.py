"""
Unit tests for Lease Monitoring Daemon.

Tests:
- LeaseMonitor lifecycle (start/stop)
- Expired lease detection
- Missed heartbeat detection
- RELEASE message publishing
- Integration with LeaseManager
"""

import sys
import os
import tempfile
from pathlib import Path
import time

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from leases.manager import LeaseManager
from leases.heartbeat import HeartbeatProtocol
from daemons.lease_monitor import LeaseMonitor


class MockBus:
    """Mock message bus for testing"""

    def __init__(self):
        self.published_messages = []


class TestLeaseMonitorLifecycle:
    """Test daemon start/stop lifecycle"""

    def test_monitor_start_stop(self):
        """Verify monitor can start and stop cleanly"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        protocol = HeartbeatProtocol(manager)
        bus = MockBus()

        monitor = LeaseMonitor(manager, protocol, bus)

        # Start monitor
        monitor.start()
        assert monitor._running is True
        assert monitor._thread is not None

        # Wait a bit
        time.sleep(0.2)

        # Stop monitor
        monitor.stop()
        assert monitor._running is False
        assert monitor._thread is None


class TestLeaseMonitorExpiry:
    """Test expired lease detection"""

    def test_monitor_detects_expired_lease(self):
        """Verify monitor detects expired leases"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        protocol = HeartbeatProtocol(manager)
        bus = MockBus()

        monitor = LeaseMonitor(manager, protocol, bus)

        # Create lease with TTL=0  (immediately expired)
        lease_id = manager.create_lease(
            "task-exp", "worker-exp", ttl=0, heartbeat_interval=30
        )

        # Wait to ensure expiry
        time.sleep(0.01)

        # Manually call check_expired_leases
        monitor.check_expired_leases()

        # Verify RELEASE published
        assert len(bus.published_messages) == 1
        msg = bus.published_messages[0]
        assert msg["kind"] == "RELEASE"
        assert msg["payload"]["lease_id"] == lease_id
        assert msg["payload"]["reason"] == "timeout"

        # Verify lease deleted
        assert manager.get_lease(lease_id) is None

    def test_monitor_publishes_release(self):
        """Verify monitor publishes RELEASE with correct payload"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        protocol = HeartbeatProtocol(manager)
        bus = MockBus()

        monitor = LeaseMonitor(manager, protocol, bus)

        # Create expired lease
        lease_id = manager.create_lease(
            "task-123", "worker-abc", ttl=0, heartbeat_interval=30
        )
        time.sleep(0.01)

        # Check
        monitor.check_expired_leases()

        # Verify RELEASE structure
        assert len(bus.published_messages) == 1
        release = bus.published_messages[0]

        assert release["kind"] == "RELEASE"
        assert release["thread_id"] == "task-123"
        assert release["payload"]["task_id"] == "task-123"
        assert release["payload"]["lease_id"] == lease_id
        assert release["payload"]["reason"] == "timeout"

    def test_scavenge_on_timeout(self):
        """Verify scavenge_expired removes expired leases"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)

        # Create expired lease
        lease_id = manager.create_lease(
            "task-scav", "worker-scav", ttl=0, heartbeat_interval=30
        )
        time.sleep(0.01)

        # Scavenge
        scavenged = manager.scavenge_expired()

        # Verify lease in scavenged list
        assert lease_id in scavenged

        # Verify lease deleted
        assert manager.get_lease(lease_id) is None

    def test_monitor_ignores_active_leases(self):
        """Verify monitor doesn't trigger on active leases"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        protocol = HeartbeatProtocol(manager)
        bus = MockBus()

        monitor = LeaseMonitor(manager, protocol, bus)

        # Create active lease (long TTL)
        lease_id = manager.create_lease(
            "task-active", "worker-active", ttl=3600, heartbeat_interval=30
        )

        # Check immediately
        monitor.check_expired_leases()

        # Should not publish RELEASE
        assert len(bus.published_messages) == 0

        # Lease should still exist
        assert manager.get_lease(lease_id) is not None


class TestLeaseMonitorHeartbeat:
    """Test missed heartbeat detection"""

    def test_monitor_handles_missed_heartbeat(self):
        """Verify monitor detects and handles missed heartbeats"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        protocol = HeartbeatProtocol(manager)
        bus = MockBus()

        monitor = LeaseMonitor(manager, protocol, bus)

        # Create lease
        lease_id = manager.create_lease(
            "task-hb-miss", "worker-hb-miss", ttl=3600, heartbeat_interval=30
        )

        # Set expectation with immediate expiry (interval=0)
        protocol.expect_heartbeat(lease_id, 0)

        # Wait to ensure miss
        time.sleep(0.01)

        # Check
        monitor.check_expired_leases()

        # Verify RELEASE published with heartbeat_miss reason
        assert len(bus.published_messages) == 1
        msg = bus.published_messages[0]
        assert msg["kind"] == "RELEASE"
        assert msg["payload"]["reason"] == "heartbeat_miss"
        assert msg["payload"]["lease_id"] == lease_id

        # Verify lease deleted
        assert manager.get_lease(lease_id) is None

        # Verify expectation removed
        assert protocol.get_next_expected_heartbeat(lease_id) is None

    def test_monitor_no_release_for_active_heartbeats(self):
        """Verify monitor doesn't trigger on active heartbeats"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        protocol = HeartbeatProtocol(manager)
        bus = MockBus()

        monitor = LeaseMonitor(manager, protocol, bus)

        # Create lease
        lease_id = manager.create_lease(
            "task-hb-ok", "worker-hb-ok", ttl=3600, heartbeat_interval=3600
        )

        # Set expectation with long interval
        protocol.expect_heartbeat(lease_id, 3600)

        # Check immediately
        monitor.check_expired_leases()

        # Should not publish RELEASE
        assert len(bus.published_messages) == 0


class TestLeaseMonitorBackground:
    """Test background monitoring loop"""

    def test_monitor_background_checking(self):
        """Verify background thread performs periodic checks"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        protocol = HeartbeatProtocol(manager)
        bus = MockBus()

        # Create monitor with short interval for testing
        monitor = LeaseMonitor(manager, protocol, bus)
        monitor.CHECK_INTERVAL = 0.2  # 0.2 seconds

        # Create expired lease
        lease_id = manager.create_lease(
            "task-bg", "worker-bg", ttl=0, heartbeat_interval=30
        )
        time.sleep(0.01)

        # Start monitor
        monitor.start()

        # Wait for at least one check cycle
        time.sleep(0.3)

        # Stop monitor
        monitor.stop()

        # Should have published RELEASE
        assert len(bus.published_messages) >= 1
        assert bus.published_messages[0]["kind"] == "RELEASE"

    def test_monitor_handles_errors_gracefully(self):
        """Verify monitor continues running after errors"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        protocol = HeartbeatProtocol(manager)
        bus = MockBus()

        monitor = LeaseMonitor(manager, protocol, bus)
        monitor.CHECK_INTERVAL = 0.1

        # Start monitor
        monitor.start()

        # Wait a bit (should not crash even with no leases)
        time.sleep(0.3)

        # Should still be running
        assert monitor._running is True

        # Stop cleanly
        monitor.stop()
        assert monitor._running is False


class TestLeaseMonitorIntegration:
    """Integration tests"""

    def test_monitor_both_expiry_and_heartbeat(self):
        """Verify monitor handles both types of failures"""
        db_path = Path(tempfile.mktemp())
        manager = LeaseManager(db_path)
        protocol = HeartbeatProtocol(manager)
        bus = MockBus()

        monitor = LeaseMonitor(manager, protocol, bus)

        # Create expired lease (TTL)
        lease_id1 = manager.create_lease(
            "task-exp", "worker-1", ttl=0, heartbeat_interval=30
        )

        # Create lease with missed heartbeat
        lease_id2 = manager.create_lease(
            "task-hb", "worker-2", ttl=3600, heartbeat_interval=30
        )
        protocol.expect_heartbeat(lease_id2, 0)  # Immediate miss

        time.sleep(0.01)

        # Check
        monitor.check_expired_leases()

        # Should have 2 RELEASE messages
        assert len(bus.published_messages) == 2

        reasons = {msg["payload"]["reason"] for msg in bus.published_messages}
        assert "timeout" in reasons
        assert "heartbeat_miss" in reasons

        # Both leases deleted
        assert manager.get_lease(lease_id1) is None
        assert manager.get_lease(lease_id2) is None
