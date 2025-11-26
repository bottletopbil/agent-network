"""Tests for checkpointing system."""

import sys
import os
import pytest
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from checkpoint import (
    MerkleTree,
    MerkleProof,
    CheckpointManager,
    Checkpoint,
    SignedCheckpoint
)


class TestMerkleTree:
    """Test Merkle tree operations."""

    def test_build_empty_tree(self):
        """Test building tree with no leaves."""
        tree = MerkleTree()
        root = tree.build_tree([])
        
        assert root is not None
        assert tree.get_root() == root
        assert tree.get_leaf_count() == 0

    def test_build_single_leaf(self):
        """Test building tree with single leaf."""
        tree = MerkleTree()
        leaves = ["hash-1"]
        
        root = tree.build_tree(leaves)
        
        assert root == leaves[0]  # Single leaf is the root
        assert tree.get_leaf_count() == 1

    def test_build_two_leaves(self):
        """Test building tree with two leaves."""
        tree = MerkleTree()
        leaves = ["hash-1", "hash-2"]
        
        root = tree.build_tree(leaves)
        
        assert root is not None
        assert root != leaves[0]
        assert root != leaves[1]
        assert tree.get_leaf_count() == 2

    def test_build_many_leaves(self):
        """Test building tree with many leaves."""
        tree = MerkleTree()
        leaves = [f"hash-{i}" for i in range(10)]
        
        root = tree.build_tree(leaves)
        
        assert root is not None
        assert tree.get_leaf_count() == 10

    def test_get_proof(self):
        """Test generating Merkle proof."""
        tree = MerkleTree()
        leaves = ["hash-1", "hash-2", "hash-3", "hash-4"]
        root = tree.build_tree(leaves)
        
        # Get proof for first leaf
        proof = tree.get_proof(0)
        
        assert proof is not None
        assert proof.leaf_index == 0
        assert proof.leaf_hash == "hash-1"
        assert proof.root_hash == root
        assert len(proof.siblings) > 0

    def test_verify_proof_valid(self):
        """Test verifying a valid proof."""
        tree = MerkleTree()
        leaves = ["hash-1", "hash-2", "hash-3", "hash-4"]
        root = tree.build_tree(leaves)
        
        # Get and verify proof
        proof = tree.get_proof(2)
        
        is_valid = tree.verify_proof("hash-3", proof, root)
        assert is_valid is True

    def test_verify_proof_invalid_leaf(self):
        """Test verifying proof with wrong leaf."""
        tree = MerkleTree()
        leaves = ["hash-1", "hash-2", "hash-3", "hash-4"]
        root = tree.build_tree(leaves)
        
        proof = tree.get_proof(0)
        
        # Try to verify with wrong leaf
        is_valid = tree.verify_proof("wrong-hash", proof, root)
        assert is_valid is False

    def test_verify_proof_invalid_root(self):
        """Test verifying proof with wrong root."""
        tree = MerkleTree()
        leaves = ["hash-1", "hash-2", "hash-3", "hash-4"]
        root = tree.build_tree(leaves)
        
        proof = tree.get_proof(0)
        
        # Try to verify with wrong root
        is_valid = tree.verify_proof("hash-1", proof, "wrong-root")
        assert is_valid is False

    def test_proof_all_leaves(self):
        """Test generating and verifying proofs for all leaves."""
        tree = MerkleTree()
        leaves = [f"hash-{i}" for i in range(8)]
        root = tree.build_tree(leaves)
        
        # Verify proof for each leaf
        for i, leaf in enumerate(leaves):
            proof = tree.get_proof(i)
            assert proof is not None
            
            is_valid = tree.verify_proof(leaf, proof, root)
            assert is_valid is True

    def test_odd_number_leaves(self):
        """Test tree with odd number of leaves."""
        tree = MerkleTree()
        leaves = ["hash-1", "hash-2", "hash-3"]
        root = tree.build_tree(leaves)
        
        # Should handle odd number gracefully
        assert root is not None
        
        # Verify all proofs still work
        for i in range(3):
            proof = tree.get_proof(i)
            is_valid = tree.verify_proof(leaves[i], proof, root)
            assert is_valid is True


class TestCheckpoint:
    """Test checkpoint dataclass."""

    def test_create_checkpoint(self):
        """Test creating a checkpoint."""
        checkpoint = Checkpoint(
            epoch=1,
            merkle_root="root-hash-123",
            state_summary={"tasks": 10, "completed": 5},
            timestamp_ns=1234567890,
            op_count=100
        )
        
        assert checkpoint.epoch == 1
        assert checkpoint.merkle_root == "root-hash-123"
        assert checkpoint.op_count == 100

    def test_checkpoint_to_dict(self):
        """Test converting checkpoint to dictionary."""
        checkpoint = Checkpoint(
            epoch=1,
            merkle_root="root-hash",
            state_summary={},
            timestamp_ns=1000,
            op_count=50
        )
        
        data = checkpoint.to_dict()
        
        assert data["epoch"] == 1
        assert data["merkle_root"] == "root-hash"
        assert data["op_count"] == 50

    def test_checkpoint_from_dict(self):
        """Test creating checkpoint from dictionary."""
        data = {
            "epoch": 2,
            "merkle_root": "root-abc",
            "state_summary": {"test": "data"},
            "timestamp_ns": 2000,
            "op_count": 75,
            "metadata": {}
        }
        
        checkpoint = Checkpoint.from_dict(data)
        
        assert checkpoint.epoch == 2
        assert checkpoint.merkle_root == "root-abc"
        assert checkpoint.op_count == 75

    def test_compute_hash_deterministic(self):
        """Test checkpoint hash is deterministic."""
        checkpoint1 = Checkpoint(
            epoch=1,
            merkle_root="root-hash",
            state_summary={"a": 1, "b": 2},
            timestamp_ns=1000,
            op_count=10
        )
        
        checkpoint2 = Checkpoint(
            epoch=1,
            merkle_root="root-hash",
            state_summary={"b": 2, "a": 1},  # Different order
            timestamp_ns=1000,
            op_count=10
        )
        
        # Should produce same hash (deterministic)
        assert checkpoint1.compute_hash() == checkpoint2.compute_hash()


class TestSignedCheckpoint:
    """Test signed checkpoint."""

    def test_create_signed_checkpoint(self):
        """Test creating signed checkpoint."""
        checkpoint = Checkpoint(
            epoch=1,
            merkle_root="root",
            state_summary={},
            timestamp_ns=1000,
            op_count=10
        )
        
        signed = SignedCheckpoint(checkpoint=checkpoint)
        
        assert signed.checkpoint == checkpoint
        assert len(signed.signatures) == 0

    def test_add_signature(self):
        """Test adding signatures."""
        checkpoint = Checkpoint(
            epoch=1,
            merkle_root="root",
            state_summary={},
            timestamp_ns=1000,
            op_count=10
        )
        
        signed = SignedCheckpoint(checkpoint=checkpoint)
        
        signed.add_signature("verifier-1", "sig-1")
        signed.add_signature("verifier-2", "sig-2")
        
        assert len(signed.signatures) == 2
        assert signed.signatures[0]["verifier_id"] == "verifier-1"

    def test_verify_quorum(self):
        """Test quorum verification."""
        checkpoint = Checkpoint(
            epoch=1,
            merkle_root="root",
            state_summary={},
            timestamp_ns=1000,
            op_count=10
        )
        
        signed = SignedCheckpoint(checkpoint=checkpoint)
        
        # Not enough signatures
        assert signed.verify_quorum(3) is False
        
        # Add signatures
        signed.add_signature("v1", "sig1")
        signed.add_signature("v2", "sig2")
        signed.add_signature("v3", "sig3")
        
        # Now sufficient
        assert signed.verify_quorum(3) is True
        assert signed.verify_quorum(2) is True


class TestCheckpointManager:
    """Test checkpoint manager."""

    def test_create_checkpoint(self):
        """Test creating a checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))
            
            checkpoint = manager.create_checkpoint(
                epoch=1,
                plan_state={"tasks": 5},
                op_hashes=["hash-1", "hash-2", "hash-3"]
            )
            
            assert checkpoint.epoch == 1
            assert checkpoint.op_count == 3
            assert checkpoint.merkle_root is not None

    def test_sign_checkpoint(self):
        """Test signing a checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))
            
            checkpoint = manager.create_checkpoint(
                epoch=1,
                plan_state={},
                op_hashes=["hash-1"]
            )
            
            signatures = [
                {"verifier_id": "v1", "signature": "sig1"},
                {"verifier_id": "v2", "signature": "sig2"}
            ]
            
            signed = manager.sign_checkpoint(checkpoint, signatures)
            
            assert len(signed.signatures) == 2

    def test_store_and_load_checkpoint(self):
        """Test storing and loading checkpoints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))
            
            # Create and sign checkpoint
            checkpoint = manager.create_checkpoint(
                epoch=1,
                plan_state={"test": "data"},
                op_hashes=["hash-1", "hash-2"]
            )
            
            signed = manager.sign_checkpoint(
                checkpoint,
                [{"verifier_id": "v1", "signature": "sig1"}]
            )
            
            # Store
            path = manager.store_checkpoint(signed)
            assert path.exists()
            
            # Load
            loaded = manager.load_checkpoint(path)
            assert loaded is not None
            assert loaded.checkpoint.epoch == 1
            assert loaded.checkpoint.op_count == 2
            assert len(loaded.signatures) == 1

    def test_get_checkpoint(self):
        """Test getting checkpoint by epoch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))
            
            # Create and store
            checkpoint = manager.create_checkpoint(1, {}, ["hash-1"])
            signed = manager.sign_checkpoint(checkpoint, [])
            manager.store_checkpoint(signed)
            
            # Get by epoch
            retrieved = manager.get_checkpoint(1)
            assert retrieved is not None
            assert retrieved.checkpoint.epoch == 1

    def test_list_checkpoints(self):
        """Test listing checkpoints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))
            
            # Create multiple checkpoints
            for epoch in [1, 3, 5]:
                checkpoint = manager.create_checkpoint(epoch, {}, ["hash"])
                signed = manager.sign_checkpoint(checkpoint, [])
                manager.store_checkpoint(signed)
            
            epochs = manager.list_checkpoints()
            assert epochs == [1, 3, 5]

    def test_get_latest_checkpoint(self):
        """Test getting latest checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))
            
            # Create multiple
            for epoch in [1, 2, 3]:
                checkpoint = manager.create_checkpoint(epoch, {}, ["hash"])
                signed = manager.sign_checkpoint(checkpoint, [])
                manager.store_checkpoint(signed)
            
            latest = manager.get_latest_checkpoint()
            assert latest is not None
            assert latest.checkpoint.epoch == 3

    def test_delete_checkpoint(self):
        """Test deleting a checkpoint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CheckpointManager(Path(tmpdir))
            
            # Create and store
            checkpoint = manager.create_checkpoint(1, {}, ["hash"])
            signed = manager.sign_checkpoint(checkpoint, [])
            manager.store_checkpoint(signed)
            
            # Verify exists
            assert manager.get_checkpoint(1) is not None
            
            # Delete
            success = manager.delete_checkpoint(1)
            assert success is True
            
            # Verify deleted
            assert manager.get_checkpoint(1) is None
