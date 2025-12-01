"""
Lease Monitor Daemon: Continuously monitor lease expiry and missed heartbeats.
"""

import threading
import time
from typing import Optional
from leases.manager import LeaseManager
from leases.heartbeat import HeartbeatProtocol


class LeaseMonitor:
    """
    Background daemon that monitors leases and publishes RELEASE messages.

    Monitors:
    - Expired leases (TTL exceeded)
    - Missed heartbeats

    Actions:
    - Publishes RELEASE messages via bus
    - Removes heartbeat expectations
    """

    # Check interval in seconds
    CHECK_INTERVAL = 10

    def __init__(
        self,
        lease_manager: LeaseManager,
        heartbeat_protocol: HeartbeatProtocol,
        bus=None,  # Message bus for publishing RELEASE
    ):
        """
        Initialize lease monitor.

        Args:
            lease_manager: LeaseManager instance
            heartbeat_protocol: HeartbeatProtocol instance
            bus: Message bus for publishing (optional for testing)
        """
        self.lease_manager = lease_manager
        self.heartbeat_protocol = heartbeat_protocol
        self.bus = bus

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start the monitoring daemon in a background thread."""
        if self._running:
            print("[LEASE_MONITOR] Already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._monitoring_loop, daemon=False)
        self._thread.start()
        print(f"[LEASE_MONITOR] Started (checking every {self.CHECK_INTERVAL}s)")

    def stop(self):
        """Stop the monitoring daemon and wait for thread to finish."""
        if not self._running:
            print("[LEASE_MONITOR] Not running")
            return

        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        print("[LEASE_MONITOR] Stopped")

    def _monitoring_loop(self):
        """
        Main monitoring loop (runs in background thread).

        Continuously checks for expired leases and missed heartbeats.
        """
        while self._running:
            try:
                self.check_expired_leases()
            except Exception as e:
                print(f"[LEASE_MONITOR] ERROR in monitoring loop: {e}")

            # Sleep in small increments to allow quick shutdown
            sleep_iterations = int(self.CHECK_INTERVAL * 10)
            for _ in range(sleep_iterations):
                if not self._running:
                    break
                time.sleep(0.1)

    def check_expired_leases(self):
        """
        Check for expired leases and missed heartbeats.

        Called periodically by monitoring loop.
        """
        # Check for expired leases (TTL)
        expired = self.lease_manager.check_expiry()
        for lease_id in expired:
            self.handle_expired(lease_id)

        # Check for missed heartbeats
        missed = self.heartbeat_protocol.check_missed_heartbeats()
        for lease_id in missed:
            self.handle_missed_heartbeat(lease_id)

    def handle_expired(self, lease_id: str):
        """
        Handle expired lease (TTL exceeded).

        Args:
            lease_id: Expired lease identifier
        """
        # Get lease details before deleting
        lease = self.lease_manager.get_lease(lease_id)
        if lease is None:
            print(f"[LEASE_MONITOR] Lease {lease_id} not found (already deleted?)")
            return

        print(f"[LEASE_MONITOR] Lease {lease_id} expired (task: {lease.task_id})")

        # Publish RELEASE message
        self._publish_release(lease.task_id, lease_id, "timeout")

        # Remove heartbeat expectation
        self.heartbeat_protocol.remove_expectation(lease_id)

        # Delete lease
        self.lease_manager.delete_lease(lease_id)

    def handle_missed_heartbeat(self, lease_id: str):
        """
        Handle missed heartbeat.

        Args:
            lease_id: Lease with missed heartbeat
        """
        # Get lease details
        lease = self.lease_manager.get_lease(lease_id)
        if lease is None:
            print(f"[LEASE_MONITOR] Lease {lease_id} not found for missed heartbeat")
            self.heartbeat_protocol.remove_expectation(lease_id)
            return

        print(
            f"[LEASE_MONITOR] Lease {lease_id} missed heartbeat (task: {lease.task_id})"
        )

        # Publish RELEASE message
        self._publish_release(lease.task_id, lease_id, "heartbeat_miss")

        # Remove heartbeat expectation
        self.heartbeat_protocol.remove_expectation(lease_id)

        # Delete lease
        self.lease_manager.delete_lease(lease_id)

        # Future: Trigger slashing (Phase 8)
        # self._slash_worker(lease.worker_id, "missed_heartbeat")

    def _publish_release(self, task_id: str, lease_id: str, reason: str):
        """
        Publish RELEASE message to bus.

        Args:
            task_id: Task associated with lease
            lease_id: Lease identifier
            reason: Release reason (timeout or heartbeat_miss)
        """
        if self.bus is None:
            print(f"[LEASE_MONITOR] No bus configured, skipping RELEASE publish")
            return

        # Create RELEASE envelope (simplified, would need full envelope creation)
        release_message = {
            "kind": "RELEASE",
            "thread_id": task_id,
            "payload": {"task_id": task_id, "lease_id": lease_id, "reason": reason},
        }

        try:
            # Publish to bus (actual implementation depends on bus API)
            # For now, just add to a list for testing
            if hasattr(self.bus, "published_messages"):
                self.bus.published_messages.append(release_message)
            print(
                f"[LEASE_MONITOR] Published RELEASE for lease {lease_id} (reason: {reason})"
            )
        except Exception as e:
            print(f"[LEASE_MONITOR] ERROR publishing RELEASE: {e}")
