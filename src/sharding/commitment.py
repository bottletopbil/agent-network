"""Commit-by-reference protocol for cross-shard coordination.

This module implements the commitment protocol that allows shards to coordinate
without classical 2PC (two-phase commit). Instead, each shard publishes a 
commitment artifact that other shards can reference.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List, Set
from datetime import datetime
import hashlib
import logging

logger = logging.getLogger(__name__)


@dataclass
class CommitmentArtifact:
    """
    Represents a commitment from a shard for a specific NEED.
    
    This is published when a shard has completed its portion of work
    and is ready to commit, pending dependencies.
    """
    shard_id: int
    need_id: str
    artifact_hash: str  # Hash of the actual result artifact
    timestamp_ns: int
    commitment_hash: str = ""  # Hash of this commitment itself
    dependencies: List[str] = field(default_factory=list)  # Other commitment hashes this depends on
    
    def __post_init__(self):
        """Calculate commitment hash if not provided."""
        if not self.commitment_hash:
            self.commitment_hash = self._calculate_hash()
    
    def _calculate_hash(self) -> str:
        """Calculate deterministic hash of this commitment."""
        # Create deterministic string representation
        content = (
            f"{self.shard_id}|{self.need_id}|{self.artifact_hash}|"
            f"{self.timestamp_ns}|{','.join(sorted(self.dependencies))}"
        )
        return hashlib.sha256(content.encode('utf-8')).hexdigest()


class CommitmentProtocol:
    """
    Manages commitment artifacts for cross-shard coordination.
    
    Uses optimistic commit-by-reference:
    1. Each shard completes work and creates a commitment
    2. Commitments reference dependencies (other shard commitments)
    3. Only when all dependencies are satisfied does the commitment finalize
    """
    
    def __init__(self):
        """Initialize commitment protocol."""
        # Map: (shard_id, need_id) -> CommitmentArtifact
        self.commitments: Dict[tuple, CommitmentArtifact] = {}
        
        # Map: commitment_hash -> CommitmentArtifact (for dependency lookup)
        self.commitment_by_hash: Dict[str, CommitmentArtifact] = {}
        
        # Track which commitments are finalized
        self.finalized: Set[str] = set()
        
        # Track pending commitments waiting on dependencies
        self.pending: Dict[str, Set[str]] = {}  # commitment_hash -> set of pending dependency hashes

    def create_commitment(
        self,
        shard_id: int,
        need_id: str,
        artifact_ref: str,
        dependencies: Optional[List[str]] = None
    ) -> CommitmentArtifact:
        """
        Create a new commitment artifact.
        
        Args:
            shard_id: Shard that produced this commitment
            need_id: NEED identifier this commitment is for
            artifact_ref: Hash reference to the actual result artifact
            dependencies: Optional list of commitment hashes this depends on
            
        Returns:
            Created CommitmentArtifact
        """
        now_ns = int(datetime.utcnow().timestamp() * 1_000_000_000)
        
        commitment = CommitmentArtifact(
            shard_id=shard_id,
            need_id=need_id,
            artifact_hash=artifact_ref,
            timestamp_ns=now_ns,
            dependencies=dependencies or []
        )
        
        logger.info(
            f"Created commitment {commitment.commitment_hash[:8]} "
            f"for need {need_id} shard {shard_id}"
        )
        
        return commitment

    def publish_commitment(self, commitment: CommitmentArtifact) -> bool:
        """
        Publish a commitment to the registry.
        
        Args:
            commitment: CommitmentArtifact to publish
            
        Returns:
            True if published successfully, False if duplicate
        """
        key = (commitment.shard_id, commitment.need_id)
        
        # Check for duplicate
        if key in self.commitments:
            existing = self.commitments[key]
            if existing.commitment_hash == commitment.commitment_hash:
                logger.debug(
                    f"Commitment {commitment.commitment_hash[:8]} already published"
                )
                return False
            else:
                logger.warning(
                    f"Conflicting commitment for shard {commitment.shard_id} "
                    f"need {commitment.need_id}: "
                    f"existing {existing.commitment_hash[:8]} vs "
                    f"new {commitment.commitment_hash[:8]}"
                )
                return False
        
        # Store commitment
        self.commitments[key] = commitment
        self.commitment_by_hash[commitment.commitment_hash] = commitment
        
        # Track pending dependencies
        if commitment.dependencies:
            pending_deps = set()
            for dep_hash in commitment.dependencies:
                if dep_hash not in self.finalized:
                    pending_deps.add(dep_hash)
            
            if pending_deps:
                self.pending[commitment.commitment_hash] = pending_deps
                logger.debug(
                    f"Commitment {commitment.commitment_hash[:8]} has "
                    f"{len(pending_deps)} pending dependencies"
                )
        
        logger.info(
            f"Published commitment {commitment.commitment_hash[:8]} "
            f"for shard {commitment.shard_id} need {commitment.need_id}"
        )
        
        # Check if this can be finalized immediately
        self._try_finalize(commitment.commitment_hash)
        
        return True

    def verify_commitment(self, commitment: CommitmentArtifact) -> bool:
        """
        Verify a commitment's integrity.
        
        Args:
            commitment: Commitment to verify
            
        Returns:
            True if commitment is valid
        """
        # Recalculate hash
        expected_hash = commitment._calculate_hash()
        
        if commitment.commitment_hash != expected_hash:
            logger.error(
                f"Commitment hash mismatch: expected {expected_hash[:8]}, "
                f"got {commitment.commitment_hash[:8]}"
            )
            return False
        
        # Verify dependencies exist (if checking published commitments)
        for dep_hash in commitment.dependencies:
            if dep_hash not in self.commitment_by_hash:
                logger.warning(
                    f"Dependency {dep_hash[:8]} not found for "
                    f"commitment {commitment.commitment_hash[:8]}"
                )
                # This is not necessarily an error - dependency might not be published yet
        
        return True

    def get_commitment(
        self,
        shard_id: int,
        need_id: str
    ) -> Optional[CommitmentArtifact]:
        """
        Get commitment for a specific shard and NEED.
        
        Args:
            shard_id: Shard identifier
            need_id: NEED identifier
            
        Returns:
            CommitmentArtifact if exists, None otherwise
        """
        key = (shard_id, need_id)
        return self.commitments.get(key)

    def get_commitment_by_hash(self, commitment_hash: str) -> Optional[CommitmentArtifact]:
        """
        Get commitment by its hash.
        
        Args:
            commitment_hash: Commitment hash
            
        Returns:
            CommitmentArtifact if exists, None otherwise
        """
        return self.commitment_by_hash.get(commitment_hash)

    def is_finalized(self, commitment_hash: str) -> bool:
        """
        Check if a commitment is finalized.
        
        Args:
            commitment_hash: Commitment hash to check
            
        Returns:
            True if finalized
        """
        return commitment_hash in self.finalized

    def finalize_commitment(self, commitment_hash: str) -> bool:
        """
        Mark a commitment as finalized.
        
        This should be called when all dependencies are satisfied.
        
        Args:
            commitment_hash: Commitment to finalize
            
        Returns:
            True if successfully finalized
        """
        if commitment_hash in self.finalized:
            return False
        
        # Get commitment
        commitment = self.commitment_by_hash.get(commitment_hash)
        if not commitment:
            logger.error(f"Cannot finalize unknown commitment {commitment_hash[:8]}")
            return False
        
        # Check all dependencies are finalized
        for dep_hash in commitment.dependencies:
            if dep_hash not in self.finalized:
                logger.warning(
                    f"Cannot finalize {commitment_hash[:8]}: "
                    f"dependency {dep_hash[:8]} not finalized"
                )
                return False
        
        # Mark as finalized
        self.finalized.add(commitment_hash)
        
        # Remove from pending
        if commitment_hash in self.pending:
            del self.pending[commitment_hash]
        
        logger.info(
            f"Finalized commitment {commitment_hash[:8]} "
            f"for shard {commitment.shard_id} need {commitment.need_id}"
        )
        
        # Trigger cascade finalization
        self._cascade_finalize(commitment_hash)
        
        return True

    def _try_finalize(self, commitment_hash: str) -> None:
        """
        Try to finalize a commitment if all dependencies are satisfied.
        
        Args:
            commitment_hash: Commitment to try finalizing
        """
        if commitment_hash in self.finalized:
            return
        
        commitment = self.commitment_by_hash.get(commitment_hash)
        if not commitment:
            return
        
        # Check if all dependencies are finalized
        all_deps_finalized = all(
            dep_hash in self.finalized
            for dep_hash in commitment.dependencies
        )
        
        if all_deps_finalized:
            self.finalize_commitment(commitment_hash)

    def _cascade_finalize(self, finalized_hash: str) -> None:
        """
        Cascade finalization to commitments waiting on this one.
        
        Args:
            finalized_hash: Commitment that was just finalized
        """
        # Find all commitments waiting on this dependency
        waiting = [
            comm_hash
            for comm_hash, deps in self.pending.items()
            if finalized_hash in deps
        ]
        
        for comm_hash in waiting:
            # Remove this dependency from pending set
            self.pending[comm_hash].discard(finalized_hash)
            
            # Try to finalize if all dependencies satisfied
            self._try_finalize(comm_hash)

    def get_pending_dependencies(self, commitment_hash: str) -> Set[str]:
        """
        Get pending dependencies for a commitment.
        
        Args:
            commitment_hash: Commitment to check
            
        Returns:
            Set of pending dependency hashes
        """
        return self.pending.get(commitment_hash, set()).copy()

    def get_all_commitments(self, need_id: str) -> List[CommitmentArtifact]:
        """
        Get all commitments for a specific NEED.
        
        Args:
            need_id: NEED identifier
            
        Returns:
            List of CommitmentArtifacts
        """
        return [
            commitment
            for (shard, nid), commitment in self.commitments.items()
            if nid == need_id
        ]

    def clear_need(self, need_id: str) -> None:
        """
        Clear all commitments for a completed NEED.
        
        Args:
            need_id: NEED identifier
        """
        # Find all commitments for this need
        to_remove = [
            key for key in self.commitments.keys()
            if key[1] == need_id
        ]
        
        for key in to_remove:
            commitment = self.commitments[key]
            
            # Remove from all indexes
            del self.commitments[key]
            del self.commitment_by_hash[commitment.commitment_hash]
            self.finalized.discard(commitment.commitment_hash)
            self.pending.pop(commitment.commitment_hash, None)
        
        logger.debug(f"Cleared {len(to_remove)} commitments for need {need_id}")
