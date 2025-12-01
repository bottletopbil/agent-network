"""Escrow system for cross-shard artifact coordination.

Escrow artifacts allow multiple shards to coordinate without blocking 2PC.
Each shard publishes its commitment to an escrow with a TTL. The escrow
only releases when all dependencies are ready, or expires if TTL is exceeded.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List, Set, Callable
from datetime import datetime
from enum import Enum
import logging
import uuid

logger = logging.getLogger(__name__)


class EscrowState(Enum):
    """States an escrow can be in."""

    PENDING = "pending"  # Waiting for dependencies
    READY = "ready"  # All dependencies satisfied
    RELEASED = "released"  # Artifact released to requestor
    EXPIRED = "expired"  # TTL exceeded, rolled back
    CANCELLED = "cancelled"  # Manually cancelled


@dataclass
class EscrowArtifact:
    """
    Represents an artifact held in escrow pending cross-shard dependencies.

    The escrow holds the artifact until all shard dependencies signal ready,
    or the TTL expires and triggers rollback.
    """

    escrow_id: str
    artifact_hash: str
    ttl_ns: int  # Time-to-live in nanoseconds
    shard_dependencies: List[int]  # List of shard IDs that must be ready
    created_at_ns: int
    expires_at_ns: int = 0
    state: EscrowState = EscrowState.PENDING
    ready_shards: Set[int] = field(default_factory=set)
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        """Calculate expiration time."""
        if not self.expires_at_ns:
            self.expires_at_ns = self.created_at_ns + self.ttl_ns

    def is_expired(self, current_time_ns: int) -> bool:
        """Check if escrow has expired."""
        return current_time_ns >= self.expires_at_ns

    def all_dependencies_ready(self) -> bool:
        """Check if all shard dependencies are ready."""
        return all(
            shard_id in self.ready_shards for shard_id in self.shard_dependencies
        )


class EscrowManager:
    """
    Manages escrow artifacts with TTL-based coordination.

    Provides optimistic cross-shard coordination:
    1. Shards create escrows with dependencies and TTL
    2. Dependent shards signal ready
    3. Escrow releases when all ready OR expires on timeout
    """

    def __init__(self):
        """Initialize escrow manager."""
        # Map: escrow_id -> EscrowArtifact
        self.escrows: Dict[str, EscrowArtifact] = {}

        # Callbacks for escrow events
        self.on_release_callbacks: List[Callable[[EscrowArtifact], None]] = []
        self.on_expire_callbacks: List[Callable[[EscrowArtifact], None]] = []

    def create_escrow(
        self,
        artifact_hash: str,
        dependencies: List[int],
        ttl_ns: int,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Create a new escrow for an artifact.

        Args:
            artifact_hash: Hash of the artifact to escrow
            dependencies: List of shard IDs that must signal ready
            ttl_ns: Time-to-live in nanoseconds
            metadata: Optional metadata to attach

        Returns:
            Escrow ID
        """
        escrow_id = str(uuid.uuid4())
        now_ns = int(datetime.utcnow().timestamp() * 1_000_000_000)

        escrow = EscrowArtifact(
            escrow_id=escrow_id,
            artifact_hash=artifact_hash,
            ttl_ns=ttl_ns,
            shard_dependencies=dependencies,
            created_at_ns=now_ns,
            metadata=metadata or {},
        )

        self.escrows[escrow_id] = escrow

        logger.info(
            f"Created escrow {escrow_id} for artifact {artifact_hash[:8]} "
            f"with {len(dependencies)} dependencies, TTL={ttl_ns/1e9:.2f}s"
        )

        # Check if immediately ready (no dependencies)
        if not dependencies:
            self._transition_to_ready(escrow_id)

        return escrow_id

    def add_ready_shard(self, escrow_id: str, shard_id: int) -> bool:
        """
        Signal that a shard is ready.

        Args:
            escrow_id: Escrow identifier
            shard_id: Shard ID that is ready

        Returns:
            True if this triggered escrow release
        """
        escrow = self.escrows.get(escrow_id)
        if not escrow:
            logger.warning(f"Escrow {escrow_id} not found")
            return False

        if escrow.state != EscrowState.PENDING:
            logger.debug(
                f"Escrow {escrow_id} is in state {escrow.state.value}, "
                f"ignoring ready signal"
            )
            return False

        # Add to ready set
        escrow.ready_shards.add(shard_id)

        logger.debug(
            f"Shard {shard_id} ready for escrow {escrow_id} "
            f"({len(escrow.ready_shards)}/{len(escrow.shard_dependencies)})"
        )

        # Check if all dependencies satisfied
        if escrow.all_dependencies_ready():
            self._transition_to_ready(escrow_id)
            return True

        return False

    def check_all_ready(self, escrow_id: str) -> bool:
        """
        Check if all dependencies for an escrow are ready.

        Args:
            escrow_id: Escrow identifier

        Returns:
            True if all dependencies ready
        """
        escrow = self.escrows.get(escrow_id)
        if not escrow:
            return False

        return escrow.state == EscrowState.READY or escrow.all_dependencies_ready()

    def release_escrow(self, escrow_id: str) -> Optional[str]:
        """
        Release an escrow and return the artifact.

        Can only release escrows in READY state.

        Args:
            escrow_id: Escrow identifier

        Returns:
            Artifact hash if released, None if cannot release
        """
        escrow = self.escrows.get(escrow_id)
        if not escrow:
            logger.error(f"Escrow {escrow_id} not found")
            return None

        if escrow.state != EscrowState.READY:
            logger.error(
                f"Cannot release escrow {escrow_id} in state {escrow.state.value}"
            )
            return None

        # Transition to released
        escrow.state = EscrowState.RELEASED

        logger.info(f"Released escrow {escrow_id}, artifact {escrow.artifact_hash[:8]}")

        # Trigger callbacks
        for callback in self.on_release_callbacks:
            try:
                callback(escrow)
            except Exception as e:
                logger.error(f"Error in release callback: {e}")

        return escrow.artifact_hash

    def expire_escrow(self, escrow_id: str) -> bool:
        """
        Expire an escrow due to timeout.

        Args:
            escrow_id: Escrow identifier

        Returns:
            True if escrow was expired
        """
        escrow = self.escrows.get(escrow_id)
        if not escrow:
            logger.warning(f"Escrow {escrow_id} not found for expiration")
            return False

        if escrow.state not in (EscrowState.PENDING, EscrowState.READY):
            logger.debug(
                f"Escrow {escrow_id} already in final state {escrow.state.value}"
            )
            return False

        # Transition to expired
        escrow.state = EscrowState.EXPIRED

        logger.warning(
            f"Expired escrow {escrow_id}, artifact {escrow.artifact_hash[:8]} "
            f"({len(escrow.ready_shards)}/{len(escrow.shard_dependencies)} ready)"
        )

        # Trigger callbacks
        for callback in self.on_expire_callbacks:
            try:
                callback(escrow)
            except Exception as e:
                logger.error(f"Error in expire callback: {e}")

        return True

    def cancel_escrow(self, escrow_id: str) -> bool:
        """
        Cancel an escrow manually.

        Args:
            escrow_id: Escrow identifier

        Returns:
            True if cancelled
        """
        escrow = self.escrows.get(escrow_id)
        if not escrow:
            return False

        if escrow.state in (EscrowState.RELEASED, EscrowState.EXPIRED):
            return False

        escrow.state = EscrowState.CANCELLED
        logger.info(f"Cancelled escrow {escrow_id}")
        return True

    def check_expirations(self, current_time_ns: Optional[int] = None) -> List[str]:
        """
        Check for expired escrows and expire them.

        Args:
            current_time_ns: Current time in nanoseconds (or None for now)

        Returns:
            List of expired escrow IDs
        """
        if current_time_ns is None:
            current_time_ns = int(datetime.utcnow().timestamp() * 1_000_000_000)

        expired = []

        for escrow_id, escrow in self.escrows.items():
            if escrow.state == EscrowState.PENDING and escrow.is_expired(
                current_time_ns
            ):
                if self.expire_escrow(escrow_id):
                    expired.append(escrow_id)

        return expired

    def get_escrow(self, escrow_id: str) -> Optional[EscrowArtifact]:
        """
        Get escrow by ID.

        Args:
            escrow_id: Escrow identifier

        Returns:
            EscrowArtifact if exists
        """
        return self.escrows.get(escrow_id)

    def get_pending_escrows(self) -> List[EscrowArtifact]:
        """
        Get all pending escrows.

        Returns:
            List of pending EscrowArtifacts
        """
        return [
            escrow
            for escrow in self.escrows.values()
            if escrow.state == EscrowState.PENDING
        ]

    def cleanup_completed(self) -> int:
        """
        Remove completed escrows (released, expired, cancelled).

        Returns:
            Number of escrows removed
        """
        completed_states = {
            EscrowState.RELEASED,
            EscrowState.EXPIRED,
            EscrowState.CANCELLED,
        }

        to_remove = [
            escrow_id
            for escrow_id, escrow in self.escrows.items()
            if escrow.state in completed_states
        ]

        for escrow_id in to_remove:
            del self.escrows[escrow_id]

        if to_remove:
            logger.debug(f"Cleaned up {len(to_remove)} completed escrows")

        return len(to_remove)

    def register_on_release(self, callback: Callable[[EscrowArtifact], None]):
        """Register callback for escrow release events."""
        self.on_release_callbacks.append(callback)

    def register_on_expire(self, callback: Callable[[EscrowArtifact], None]):
        """Register callback for escrow expiration events."""
        self.on_expire_callbacks.append(callback)

    def _transition_to_ready(self, escrow_id: str):
        """
        Transition escrow to READY state.

        Args:
            escrow_id: Escrow identifier
        """
        escrow = self.escrows.get(escrow_id)
        if not escrow:
            return

        escrow.state = EscrowState.READY

        logger.info(
            f"Escrow {escrow_id} is READY, all {len(escrow.shard_dependencies)} "
            f"dependencies satisfied"
        )
