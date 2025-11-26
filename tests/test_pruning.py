"""Tests for op-log pruning and tiered storage."""

import sys
import os
import pytest
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from checkpoint.pruning import (
    PruningPolicy,
    TieredStorage,
    PruningManager
)


class TestPruningPolicy:
    """Test pruning policy."""

    def test_default_policy(self):
        """Test default policy parameters."""
        policy = PruningPolicy()
        
        assert policy.keep_epochs == 10
        assert policy.min_ops_per_epoch == 100

    def test_custom_policy(self):
        """Test custom policy parameters."""
        policy = PruningPolicy(keep_epochs=5, min_ops_per_epoch=50)
        
        assert policy.keep_epochs == 5
        assert policy.min_ops_per_epoch == 50

    def test_should_prune_recent(self):
        """Test that recent ops are not pruned."""
        policy = PruningPolicy(keep_epochs=10)
        
        current_epoch = 100
        
        # Recent epoch - should not prune
        assert policy.should_prune(95, current_epoch) is False
        assert policy.should_prune(91, current_epoch) is False

    def test_should_prune_old(self):
        """Test that old ops are pruned."""
        policy = PruningPolicy(keep_epochs=10)
        
        current_epoch = 100
        
        # Old epochs - should prune
        assert policy.should_prune(89, current_epoch) is True
        assert policy.should_prune(80, current_epoch) is True
        assert policy.should_prune(50, current_epoch) is True

    def test_get_pruning_threshold(self):
        """Test pruning threshold calculation."""
        policy = PruningPolicy(keep_epochs=10)
        
        threshold = policy.get_pruning_threshold(100)
        assert threshold == 90
        
        # Everything below 90 should be pruned
        assert policy.should_prune(89, 100) is True
        assert policy.should_prune(90, 100) is False


class TestTieredStorage:
    """Test tiered storage system."""

    def test_create_storage(self):
        """Test creating tiered storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TieredStorage(Path(tmpdir))
            
            assert storage.hot_tier == {}
            assert storage.get_hot_tier_size() == 0
            assert storage.get_cold_tier_size() == 0

    def test_add_to_hot(self):
        """Test adding to hot tier."""
        storage = TieredStorage()
        
        storage.add_to_hot("op-1", {"data": "test"})
        storage.add_to_hot("op-2", {"data": "test2"})
        
        assert storage.get_hot_tier_size() == 2
        assert storage.get_from_hot("op-1") == {"data": "test"}

    def test_move_to_cold(self):
        """Test moving ops to cold storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TieredStorage(Path(tmpdir))
            
            # Add to hot
            ops = [
                {"op_id": "op-1", "data": "test1"},
                {"op_id": "op-2", "data": "test2"},
                {"op_id": "op-3", "data": "test3"}
            ]
            
            for op in ops:
                storage.add_to_hot(op["op_id"], op)
            
            assert storage.get_hot_tier_size() == 3
            
            # Move to cold
            moved = storage.move_to_cold(ops)
            
            assert moved == 3
            assert storage.get_hot_tier_size() == 0
            assert storage.get_cold_tier_size() == 3

    def test_retrieve_from_cold(self):
        """Test retrieving ops from cold storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TieredStorage(Path(tmpdir))
            
            # Add and move to cold
            ops = [
                {"op_id": "op-1", "data": "test1"},
                {"op_id": "op-2", "data": "test2"}
            ]
            
            storage.move_to_cold(ops)
            
            # Retrieve
            retrieved = storage.retrieve_from_cold(["op-1", "op-2"])
            
            assert len(retrieved) == 2
            assert any(op["op_id"] == "op-1" for op in retrieved)
            assert any(op["op_id"] == "op-2" for op in retrieved)

    def test_get_op_from_either_tier(self):
        """Test getting op from either tier."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TieredStorage(Path(tmpdir))
            
            # Add to hot
            storage.add_to_hot("op-hot", {"tier": "hot"})
            
            # Add to cold
            storage.move_to_cold([{"op_id": "op-cold", "tier": "cold"}])
            
            # Should find in hot
            hot_op = storage.get_op("op-hot")
            assert hot_op is not None
            assert hot_op["tier"] == "hot"
            
            # Should find in cold
            cold_op = storage.get_op("op-cold")
            assert cold_op is not None
            assert cold_op["tier"] == "cold"

    def test_prune_from_hot(self):
        """Test pruning from hot tier."""
        storage = TieredStorage()
        
        storage.add_to_hot("op-1", {"data": "test1"})
        storage.add_to_hot("op-2", {"data": "test2"})
        storage.add_to_hot("op-3", {"data": "test3"})
        
        assert storage.get_hot_tier_size() == 3
        
        # Prune some ops
        pruned = storage.prune_from_hot(["op-1", "op-3"])
        
        assert pruned == 2
        assert storage.get_hot_tier_size() == 1
        assert storage.get_from_hot("op-2") is not None

    def test_cold_storage_persistence(self):
        """Test that cold storage persists across instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            
            # Create and store ops
            storage1 = TieredStorage(path)
            ops = [{"op_id": "op-1", "data": "persistent"}]
            storage1.move_to_cold(ops)
            
            # Create new instance with same path
            storage2 = TieredStorage(path)
            
            # Should load index automatically
            assert storage2.get_cold_tier_size() == 1
            
            # Should be able to retrieve
            retrieved = storage2.retrieve_from_cold(["op-1"])
            assert len(retrieved) == 1
            assert retrieved[0]["data"] == "persistent"


class TestPruningManager:
    """Test pruning manager."""

    def test_create_manager(self):
        """Test creating pruning manager."""
        manager = PruningManager()
        
        assert manager.policy is not None
        assert manager.storage is not None

    def test_custom_manager(self):
        """Test manager with custom components."""
        with tempfile.TemporaryDirectory() as tmpdir:
            policy = PruningPolicy(keep_epochs=5)
            storage = TieredStorage(Path(tmpdir))
            
            manager = PruningManager(policy, storage)
            
            assert manager.policy.keep_epochs == 5

    def test_prune_before_epoch(self):
        """Test pruning ops before epoch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PruningManager(
                policy=PruningPolicy(keep_epochs=10),
                storage=TieredStorage(Path(tmpdir))
            )
            
            # Create ops from different epochs
            ops = [
                {"op_id": f"op-{i}", "epoch": epoch, "data": f"data-{i}"}
                for i, epoch in enumerate([80, 85, 90, 95, 100])
            ]
            
            # Add all to hot tier
            for op in ops:
                manager.storage.add_to_hot(op["op_id"], op)
            
            # Prune with current epoch 100 (keeps 90+)
            moved, kept = manager.prune_before_epoch(ops, current_epoch=100)
            
            # Epochs 80, 85 should be moved (below threshold 90)
            assert moved == 2
            assert kept == 3

    def test_get_stats(self):
        """Test getting statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PruningManager(
                policy=PruningPolicy(keep_epochs=15),
                storage=TieredStorage(Path(tmpdir))
            )
            
            stats = manager.get_stats()
            
            assert stats["policy"]["keep_epochs"] == 15
            assert stats["storage"]["hot_tier_size"] == 0
            assert stats["storage"]["cold_tier_size"] == 0
            assert stats["storage"]["total_size"] == 0

    def test_pruning_boundaries(self):
        """Test pruning at exact boundary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PruningManager(
                policy=PruningPolicy(keep_epochs=10),
                storage=TieredStorage(Path(tmpdir))
            )
            
            # Create ops right at boundary
            ops = [
                {"op_id": "op-89", "epoch": 89, "data": "old"},
                {"op_id": "op-90", "epoch": 90, "data": "boundary"},
                {"op_id": "op-91", "epoch": 91, "data": "new"}
            ]
            
            # Current epoch 100 means threshold is 90
            # Epoch 89 should be pruned, 90 and 91 kept
            moved, kept = manager.prune_before_epoch(ops, current_epoch=100)
            
            assert moved == 1
            assert kept == 2


class TestIntegration:
    """Integration tests for pruning and tiered storage."""

    def test_full_workflow(self):
        """Test complete pruning workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PruningManager(
                policy=PruningPolicy(keep_epochs=5),
                storage=TieredStorage(Path(tmpdir))
            )
            
            # Simulate ops from many epochs
            all_ops = []
            for epoch in range(90, 101):
                for i in range(10):
                    op = {
                        "op_id": f"op-{epoch}-{i}",
                        "epoch": epoch,
                        "data": f"data-{epoch}-{i}"
                    }
                    all_ops.append(op)
                    manager.storage.add_to_hot(op["op_id"], op)
            
            # Total: 11 epochs * 10 ops = 110 ops in hot
            assert manager.storage.get_hot_tier_size() == 110
            
            # Prune with current epoch 100 (keeps 95+)
            moved, kept = manager.prune_before_epoch(all_ops, current_epoch=100)
            
            # Epochs 90-94 (5 epochs * 10 = 50 ops) should move to cold
            assert moved == 50
            assert kept == 60
            
            # Verify cold storage has them
            assert manager.storage.get_cold_tier_size() == 50
            
            # Verify hot tier should be empty (move_to_cold removes from hot)
            # But we added 110 total, moved 50 cold, so 60 should remain
            # Actually, move_to_cold already removes from hot, but we never
            # put the "kept" ops back. The kept ops were just not moved.
            # So hot tier is 0 because move_to_cold removed all moved ops.
            # Wait - we add all 110 to hot, then move 50 to cold.
            # move_to_cold removes them from hot, so hot should have 60.
            assert manager.storage.get_hot_tier_size() == 60  # Kept ops still in hot
            
            # Verify can still retrieve old ops from cold
            old_ops = manager.storage.retrieve_from_cold(
                [f"op-90-{i}" for i in range(5)]
            )
            assert len(old_ops) == 5

    def test_stats_after_pruning(self):
        """Test statistics after pruning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PruningManager(
                policy=PruningPolicy(keep_epochs=3),
                storage=TieredStorage(Path(tmpdir))
            )
            
            # Add ops
            ops = [
                {"op_id": f"op-{i}", "epoch": epoch, "data": "test"}
                for i, epoch in enumerate([90, 95, 96, 97, 98, 99, 100])
            ]
            
            for op in ops:
                manager.storage.add_to_hot(op["op_id"], op)
            
            # Prune
            manager.prune_before_epoch(ops, current_epoch=100)
            
            stats = manager.get_stats()
            
            # Should have ops in both tiers
            assert stats["storage"]["cold_tier_size"] > 0
            assert stats["storage"]["total_size"] == 7
