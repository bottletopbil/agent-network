"""Tests for escrow system."""

import sys
import os
import pytest
import asyncio
import time

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sharding.escrow import EscrowArtifact, EscrowManager, EscrowState
from daemons.escrow_monitor import EscrowMonitor


class TestEscrowArtifact:
    """Test escrow artifact."""

    def test_create_escrow_artifact(self):
        """Test basic escrow creation."""
        now_ns = int(time.time() * 1_000_000_000)
        ttl_ns = 5_000_000_000  # 5 seconds

        escrow = EscrowArtifact(
            escrow_id="escrow-123",
            artifact_hash="hash-abc",
            ttl_ns=ttl_ns,
            shard_dependencies=[0, 1, 2],
            created_at_ns=now_ns,
        )

        assert escrow.escrow_id == "escrow-123"
        assert escrow.artifact_hash == "hash-abc"
        assert escrow.state == EscrowState.PENDING
        assert len(escrow.shard_dependencies) == 3
        assert escrow.expires_at_ns == now_ns + ttl_ns

    def test_is_expired(self):
        """Test expiration checking."""
        now_ns = int(time.time() * 1_000_000_000)
        ttl_ns = 1_000_000_000  # 1 second

        escrow = EscrowArtifact(
            escrow_id="escrow-123",
            artifact_hash="hash-abc",
            ttl_ns=ttl_ns,
            shard_dependencies=[0],
            created_at_ns=now_ns,
        )

        # Not expired yet
        assert escrow.is_expired(now_ns) is False
        assert escrow.is_expired(now_ns + ttl_ns - 1) is False

        # Expired
        assert escrow.is_expired(now_ns + ttl_ns) is True
        assert escrow.is_expired(now_ns + ttl_ns + 1000) is True

    def test_all_dependencies_ready(self):
        """Test dependency checking."""
        escrow = EscrowArtifact(
            escrow_id="escrow-123",
            artifact_hash="hash-abc",
            ttl_ns=5_000_000_000,
            shard_dependencies=[0, 1, 2],
            created_at_ns=int(time.time() * 1_000_000_000),
        )

        # Initially no dependencies ready
        assert escrow.all_dependencies_ready() is False

        # Add some ready
        escrow.ready_shards.add(0)
        assert escrow.all_dependencies_ready() is False

        escrow.ready_shards.add(1)
        assert escrow.all_dependencies_ready() is False

        # All ready
        escrow.ready_shards.add(2)
        assert escrow.all_dependencies_ready() is True


class TestEscrowManager:
    """Test escrow manager."""

    def test_create_escrow(self):
        """Test creating an escrow."""
        manager = EscrowManager()

        escrow_id = manager.create_escrow(
            artifact_hash="hash-abc123", dependencies=[0, 1], ttl_ns=5_000_000_000
        )

        assert escrow_id is not None

        escrow = manager.get_escrow(escrow_id)
        assert escrow is not None
        assert escrow.artifact_hash == "hash-abc123"
        assert escrow.state == EscrowState.PENDING

    def test_create_escrow_no_dependencies(self):
        """Test escrow with no dependencies becomes ready immediately."""
        manager = EscrowManager()

        escrow_id = manager.create_escrow(
            artifact_hash="hash-abc",
            dependencies=[],  # No dependencies
            ttl_ns=5_000_000_000,
        )

        escrow = manager.get_escrow(escrow_id)
        # Should transition to READY immediately
        assert escrow.state == EscrowState.READY

    def test_add_ready_shard(self):
        """Test signaling shard ready."""
        manager = EscrowManager()

        escrow_id = manager.create_escrow(
            artifact_hash="hash-abc", dependencies=[0, 1], ttl_ns=5_000_000_000
        )

        # Add first shard
        released = manager.add_ready_shard(escrow_id, 0)
        assert released is False  # Not all ready yet

        escrow = manager.get_escrow(escrow_id)
        assert len(escrow.ready_shards) == 1
        assert escrow.state == EscrowState.PENDING

        # Add second shard - should trigger ready
        released = manager.add_ready_shard(escrow_id, 1)
        assert released is True

        assert escrow.state == EscrowState.READY

    def test_check_all_ready(self):
        """Test checking if escrow is ready."""
        manager = EscrowManager()

        escrow_id = manager.create_escrow(
            artifact_hash="hash-abc", dependencies=[0, 1], ttl_ns=5_000_000_000
        )

        assert manager.check_all_ready(escrow_id) is False

        manager.add_ready_shard(escrow_id, 0)
        assert manager.check_all_ready(escrow_id) is False

        manager.add_ready_shard(escrow_id, 1)
        assert manager.check_all_ready(escrow_id) is True

    def test_release_escrow(self):
        """Test releasing an escrow."""
        manager = EscrowManager()

        escrow_id = manager.create_escrow(
            artifact_hash="hash-abc123",
            dependencies=[],  # No deps, immediately ready
            ttl_ns=5_000_000_000,
        )

        # Should be ready
        escrow = manager.get_escrow(escrow_id)
        assert escrow.state == EscrowState.READY

        # Release it
        artifact = manager.release_escrow(escrow_id)
        assert artifact == "hash-abc123"
        assert escrow.state == EscrowState.RELEASED

    def test_cannot_release_pending(self):
        """Test cannot release pending escrow."""
        manager = EscrowManager()

        escrow_id = manager.create_escrow(
            artifact_hash="hash-abc",
            dependencies=[0],  # Has dependency
            ttl_ns=5_000_000_000,
        )

        # Try to release while pending
        artifact = manager.release_escrow(escrow_id)
        assert artifact is None

        escrow = manager.get_escrow(escrow_id)
        assert escrow.state == EscrowState.PENDING

    def test_expire_escrow(self):
        """Test expiring an escrow."""
        manager = EscrowManager()

        escrow_id = manager.create_escrow(
            artifact_hash="hash-abc",
            dependencies=[0, 1],
            ttl_ns=1_000_000_000,  # 1 second
        )

        # Expire it
        success = manager.expire_escrow(escrow_id)
        assert success is True

        escrow = manager.get_escrow(escrow_id)
        assert escrow.state == EscrowState.EXPIRED

    def test_check_expirations(self):
        """Test automatic expiration checking."""
        manager = EscrowManager()

        ttl_ns = 1_000_000_000  # 1 second

        # Create escrow that will expire
        escrow_id = manager.create_escrow(
            artifact_hash="hash-abc", dependencies=[0], ttl_ns=ttl_ns
        )

        # Get actual creation time
        escrow = manager.get_escrow(escrow_id)
        created_at_ns = escrow.created_at_ns

        # Check before expiration
        expired = manager.check_expirations(created_at_ns + ttl_ns - 1)
        assert len(expired) == 0

        # Check after expiration
        expired = manager.check_expirations(created_at_ns + ttl_ns + 1000)
        assert len(expired) == 1
        assert expired[0] == escrow_id

        assert escrow.state == EscrowState.EXPIRED

    def test_cancel_escrow(self):
        """Test cancelling an escrow."""
        manager = EscrowManager()

        escrow_id = manager.create_escrow(
            artifact_hash="hash-abc", dependencies=[0], ttl_ns=5_000_000_000
        )

        success = manager.cancel_escrow(escrow_id)
        assert success is True

        escrow = manager.get_escrow(escrow_id)
        assert escrow.state == EscrowState.CANCELLED

    def test_get_pending_escrows(self):
        """Test getting pending escrows."""
        manager = EscrowManager()

        # Create mix of escrows
        pending_id = manager.create_escrow(
            artifact_hash="hash-pending", dependencies=[0], ttl_ns=5_000_000_000
        )

        ready_id = manager.create_escrow(
            artifact_hash="hash-ready",
            dependencies=[],  # Immediately ready
            ttl_ns=5_000_000_000,
        )

        pending = manager.get_pending_escrows()
        assert len(pending) == 1
        assert pending[0].escrow_id == pending_id

    def test_cleanup_completed(self):
        """Test cleanup of completed escrows."""
        manager = EscrowManager()

        # Create and release escrow
        escrow_id1 = manager.create_escrow(
            artifact_hash="hash-1", dependencies=[], ttl_ns=5_000_000_000
        )
        manager.release_escrow(escrow_id1)

        # Create and expire escrow
        escrow_id2 = manager.create_escrow(
            artifact_hash="hash-2", dependencies=[0], ttl_ns=1_000_000_000
        )
        manager.expire_escrow(escrow_id2)

        # Create pending escrow
        escrow_id3 = manager.create_escrow(
            artifact_hash="hash-3", dependencies=[0], ttl_ns=5_000_000_000
        )

        assert len(manager.escrows) == 3

        # Cleanup
        removed = manager.cleanup_completed()
        assert removed == 2
        assert len(manager.escrows) == 1
        assert escrow_id3 in manager.escrows

    def test_callbacks(self):
        """Test release and expire callbacks."""
        manager = EscrowManager()

        released_escrows = []
        expired_escrows = []

        manager.register_on_release(lambda e: released_escrows.append(e))
        manager.register_on_expire(lambda e: expired_escrows.append(e))

        # Create and release
        escrow_id1 = manager.create_escrow(
            artifact_hash="hash-1", dependencies=[], ttl_ns=5_000_000_000
        )
        manager.release_escrow(escrow_id1)

        assert len(released_escrows) == 1
        assert released_escrows[0].escrow_id == escrow_id1

        # Create and expire
        escrow_id2 = manager.create_escrow(
            artifact_hash="hash-2", dependencies=[0], ttl_ns=1_000_000_000
        )
        manager.expire_escrow(escrow_id2)

        assert len(expired_escrows) == 1
        assert expired_escrows[0].escrow_id == escrow_id2


class TestEscrowMonitor:
    """Test escrow monitor daemon."""

    @pytest.mark.asyncio
    async def test_monitor_start_stop(self):
        """Test starting and stopping monitor."""
        manager = EscrowManager()
        monitor = EscrowMonitor(manager, check_interval_seconds=0.1)

        assert monitor.running is False

        await monitor.start()
        assert monitor.running is True

        await asyncio.sleep(0.2)  # Let it run a bit

        await monitor.stop()
        assert monitor.running is False

    @pytest.mark.asyncio
    async def test_monitor_expires_escrows(self):
        """Test monitor automatically expires timed-out escrows."""
        manager = EscrowManager()
        monitor = EscrowMonitor(manager, check_interval_seconds=0.1)

        # Create escrow with short TTL
        escrow_id = manager.create_escrow(
            artifact_hash="hash-abc",
            dependencies=[0],
            ttl_ns=100_000_000,  # 0.1 seconds
        )

        escrow = manager.get_escrow(escrow_id)
        assert escrow.state == EscrowState.PENDING

        # Start monitor
        await monitor.start()

        # Wait for expiration
        await asyncio.sleep(0.3)

        # Should be expired
        assert escrow.state == EscrowState.EXPIRED

        await monitor.stop()

    @pytest.mark.asyncio
    async def test_monitor_status(self):
        """Test getting monitor status."""
        manager = EscrowManager()
        monitor = EscrowMonitor(manager, check_interval_seconds=0.5)

        # Create some escrows
        manager.create_escrow("hash-1", [0], 5_000_000_000)
        manager.create_escrow("hash-2", [], 5_000_000_000)  # Ready

        status = monitor.get_status()

        assert status["running"] is False
        assert status["check_interval_seconds"] == 0.5
        assert status["pending_escrows"] == 1
        assert status["total_escrows"] == 2
