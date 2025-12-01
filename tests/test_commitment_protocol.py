"""Tests for commit-by-reference protocol."""

import sys
import os
import pytest
from datetime import datetime
import time

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sharding.commitment import CommitmentArtifact, CommitmentProtocol


class TestCommitmentArtifact:
    """Test commitment artifact creation and hashing."""

    def test_create_commitment(self):
        """Test basic commitment creation."""
        commitment = CommitmentArtifact(
            shard_id=0,
            need_id="need-123",
            artifact_hash="hash-abc123",
            timestamp_ns=1234567890,
        )

        assert commitment.shard_id == 0
        assert commitment.need_id == "need-123"
        assert commitment.artifact_hash == "hash-abc123"
        assert commitment.timestamp_ns == 1234567890
        assert commitment.commitment_hash  # Should be auto-generated

    def test_commitment_hash_deterministic(self):
        """Test that same inputs produce same hash."""
        commitment1 = CommitmentArtifact(
            shard_id=1,
            need_id="need-456",
            artifact_hash="hash-def456",
            timestamp_ns=9876543210,
        )

        commitment2 = CommitmentArtifact(
            shard_id=1,
            need_id="need-456",
            artifact_hash="hash-def456",
            timestamp_ns=9876543210,
        )

        assert commitment1.commitment_hash == commitment2.commitment_hash

    def test_different_inputs_different_hash(self):
        """Test that different inputs produce different hashes."""
        commitment1 = CommitmentArtifact(
            shard_id=1, need_id="need-123", artifact_hash="hash-abc", timestamp_ns=1000
        )

        commitment2 = CommitmentArtifact(
            shard_id=1,
            need_id="need-123",
            artifact_hash="hash-xyz",  # Different artifact
            timestamp_ns=1000,
        )

        assert commitment1.commitment_hash != commitment2.commitment_hash

    def test_commitment_with_dependencies(self):
        """Test commitment with dependencies."""
        commitment = CommitmentArtifact(
            shard_id=2,
            need_id="need-789",
            artifact_hash="hash-ghi789",
            timestamp_ns=5555555555,
            dependencies=["dep-hash-1", "dep-hash-2"],
        )

        assert len(commitment.dependencies) == 2
        assert "dep-hash-1" in commitment.dependencies
        assert commitment.commitment_hash  # Should include dependencies in hash


class TestCommitmentProtocol:
    """Test commitment protocol operations."""

    def test_create_commitment(self):
        """Test creating a commitment."""
        protocol = CommitmentProtocol()

        commitment = protocol.create_commitment(
            shard_id=0, need_id="need-123", artifact_ref="hash-abc123"
        )

        assert commitment.shard_id == 0
        assert commitment.need_id == "need-123"
        assert commitment.artifact_hash == "hash-abc123"
        assert commitment.commitment_hash

    def test_publish_commitment(self):
        """Test publishing a commitment."""
        protocol = CommitmentProtocol()

        commitment = protocol.create_commitment(
            shard_id=0, need_id="need-123", artifact_ref="hash-abc123"
        )

        success = protocol.publish_commitment(commitment)
        assert success is True

        # Verify it's stored
        retrieved = protocol.get_commitment(0, "need-123")
        assert retrieved is not None
        assert retrieved.commitment_hash == commitment.commitment_hash

    def test_duplicate_publication_rejected(self):
        """Test that duplicate commitments are rejected."""
        protocol = CommitmentProtocol()

        commitment = protocol.create_commitment(
            shard_id=0, need_id="need-123", artifact_ref="hash-abc123"
        )

        # First publication succeeds
        assert protocol.publish_commitment(commitment) is True

        # Second publication fails (duplicate)
        assert protocol.publish_commitment(commitment) is False

    def test_conflicting_commitment_rejected(self):
        """Test that conflicting commitments are rejected."""
        protocol = CommitmentProtocol()

        commitment1 = protocol.create_commitment(
            shard_id=0, need_id="need-123", artifact_ref="hash-abc123"
        )

        commitment2 = protocol.create_commitment(
            shard_id=0,
            need_id="need-123",
            artifact_ref="hash-xyz789",  # Different artifact
        )

        # First succeeds
        assert protocol.publish_commitment(commitment1) is True

        # Second fails (conflict)
        assert protocol.publish_commitment(commitment2) is False

    def test_verify_commitment(self):
        """Test commitment verification."""
        protocol = CommitmentProtocol()

        commitment = protocol.create_commitment(
            shard_id=0, need_id="need-123", artifact_ref="hash-abc123"
        )

        # Valid commitment
        assert protocol.verify_commitment(commitment) is True

        # Tamper with commitment
        commitment.artifact_hash = "tampered-hash"
        # But don't recalculate commitment_hash

        # Should fail verification
        assert protocol.verify_commitment(commitment) is False

    def test_get_commitment_by_hash(self):
        """Test retrieving commitment by hash."""
        protocol = CommitmentProtocol()

        commitment = protocol.create_commitment(
            shard_id=0, need_id="need-123", artifact_ref="hash-abc123"
        )
        protocol.publish_commitment(commitment)

        retrieved = protocol.get_commitment_by_hash(commitment.commitment_hash)
        assert retrieved is not None
        assert retrieved.shard_id == 0
        assert retrieved.need_id == "need-123"

    def test_finalize_commitment_no_dependencies(self):
        """Test finalizing commitment with no dependencies."""
        protocol = CommitmentProtocol()

        commitment = protocol.create_commitment(
            shard_id=0, need_id="need-123", artifact_ref="hash-abc123"
        )
        protocol.publish_commitment(commitment)

        # Should be auto-finalized (no dependencies)
        assert protocol.is_finalized(commitment.commitment_hash) is True

    def test_finalize_with_dependencies(self):
        """Test finalizing commitment with dependencies."""
        protocol = CommitmentProtocol()

        # Create and publish dependency commitment first
        dep_commitment = protocol.create_commitment(
            shard_id=0, need_id="need-dep", artifact_ref="hash-dep"
        )
        protocol.publish_commitment(dep_commitment)

        # Create commitment that depends on first one
        main_commitment = protocol.create_commitment(
            shard_id=1,
            need_id="need-main",
            artifact_ref="hash-main",
            dependencies=[dep_commitment.commitment_hash],
        )
        protocol.publish_commitment(main_commitment)

        # Dependency is finalized (no deps)
        assert protocol.is_finalized(dep_commitment.commitment_hash) is True

        # Main should also be finalized (dependency satisfied)
        assert protocol.is_finalized(main_commitment.commitment_hash) is True

    def test_pending_dependencies(self):
        """Test tracking pending dependencies."""
        protocol = CommitmentProtocol()

        # Create commitment with dependency that doesn't exist yet
        commitment = protocol.create_commitment(
            shard_id=1,
            need_id="need-123",
            artifact_ref="hash-abc",
            dependencies=["nonexistent-dep-hash"],
        )
        protocol.publish_commitment(commitment)

        # Should not be finalized (dependency missing)
        assert protocol.is_finalized(commitment.commitment_hash) is False

        # Should have pending dependency
        pending = protocol.get_pending_dependencies(commitment.commitment_hash)
        assert "nonexistent-dep-hash" in pending

    def test_cascade_finalization(self):
        """Test cascade finalization when dependency arrives late."""
        protocol = CommitmentProtocol()

        # Create commitment with dependency that doesn't exist
        dep_hash = "future-dep-hash"

        # Manually create a commitment with specific hash for testing
        main_commitment = CommitmentArtifact(
            shard_id=1,
            need_id="need-main",
            artifact_hash="hash-main",
            timestamp_ns=1000,
            dependencies=[dep_hash],
        )
        protocol.publish_commitment(main_commitment)

        # Not finalized yet
        assert protocol.is_finalized(main_commitment.commitment_hash) is False

        # Now publish the dependency
        dep_commitment = CommitmentArtifact(
            shard_id=0,
            need_id="need-dep",
            artifact_hash="hash-dep",
            timestamp_ns=1000,
            commitment_hash=dep_hash,
        )
        protocol.publish_commitment(dep_commitment)

        # Dependency should be finalized
        assert protocol.is_finalized(dep_hash) is True

        # Main should cascade finalize
        assert protocol.is_finalized(main_commitment.commitment_hash) is True

    def test_get_all_commitments(self):
        """Test getting all commitments for a need."""
        protocol = CommitmentProtocol()

        # Create commitments for different shards, same need
        commitment1 = protocol.create_commitment(
            shard_id=0, need_id="need-123", artifact_ref="hash-shard0"
        )
        commitment2 = protocol.create_commitment(
            shard_id=1, need_id="need-123", artifact_ref="hash-shard1"
        )
        commitment3 = protocol.create_commitment(
            shard_id=0, need_id="need-456", artifact_ref="hash-other"  # Different need
        )

        protocol.publish_commitment(commitment1)
        protocol.publish_commitment(commitment2)
        protocol.publish_commitment(commitment3)

        # Get all for need-123
        all_commits = protocol.get_all_commitments("need-123")
        assert len(all_commits) == 2

        shard_ids = {c.shard_id for c in all_commits}
        assert shard_ids == {0, 1}

    def test_clear_need(self):
        """Test clearing commitments for a completed need."""
        protocol = CommitmentProtocol()

        # Create multiple commitments
        commitment1 = protocol.create_commitment(
            shard_id=0, need_id="need-123", artifact_ref="hash-1"
        )
        commitment2 = protocol.create_commitment(
            shard_id=1, need_id="need-123", artifact_ref="hash-2"
        )

        protocol.publish_commitment(commitment1)
        protocol.publish_commitment(commitment2)

        assert len(protocol.get_all_commitments("need-123")) == 2

        # Clear the need
        protocol.clear_need("need-123")

        assert len(protocol.get_all_commitments("need-123")) == 0
        assert protocol.get_commitment(0, "need-123") is None
        assert protocol.get_commitment(1, "need-123") is None

    def test_complex_dependency_chain(self):
        """Test complex dependency chain with multiple levels."""
        protocol = CommitmentProtocol()

        # Create chain: A -> B -> C
        # C depends on B, B depends on A

        commit_a = protocol.create_commitment(
            shard_id=0, need_id="need-a", artifact_ref="hash-a"
        )
        protocol.publish_commitment(commit_a)

        commit_b = protocol.create_commitment(
            shard_id=1,
            need_id="need-b",
            artifact_ref="hash-b",
            dependencies=[commit_a.commitment_hash],
        )
        protocol.publish_commitment(commit_b)

        commit_c = protocol.create_commitment(
            shard_id=2,
            need_id="need-c",
            artifact_ref="hash-c",
            dependencies=[commit_b.commitment_hash],
        )
        protocol.publish_commitment(commit_c)

        # All should be finalized (dependencies satisfied in order)
        assert protocol.is_finalized(commit_a.commitment_hash) is True
        assert protocol.is_finalized(commit_b.commitment_hash) is True
        assert protocol.is_finalized(commit_c.commitment_hash) is True
