"""Tests for deterministic compression."""

import sys
import os
import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from checkpoint.compression import DeterministicCompressor


class TestDeterministicCompressor:
    """Test deterministic compression."""

    def test_create_compressor(self):
        """Test creating compressor."""
        compressor = DeterministicCompressor()

        assert compressor.compression_level == 3

    def test_custom_compression_level(self):
        """Test custom compression level."""
        compressor = DeterministicCompressor(compression_level=10)

        assert compressor.compression_level == 10

    def test_compress_state(self):
        """Test compressing state."""
        compressor = DeterministicCompressor()

        state = {"tasks": 10, "completed": 5, "data": "test"}
        compressed = compressor.compress_state(state)

        assert isinstance(compressed, bytes)
        assert len(compressed) > 0
        # Note: Small data may compress to larger size due to overhead
        # Just verify it's compressible

    def test_compress_decompress_state(self):
        """Test compress and decompress cycle."""
        compressor = DeterministicCompressor()

        original_state = {
            "tasks": 100,
            "completed": 75,
            "pending": 25,
            "metadata": {"version": 1, "epoch": 5},
        }

        # Compress
        compressed = compressor.compress_state(original_state)

        # Decompress
        decompressed_state = compressor.decompress_state(compressed)

        assert decompressed_state == original_state

    def test_compress_empty_state(self):
        """Test compressing empty state."""
        compressor = DeterministicCompressor()

        state = {}
        compressed = compressor.compress_state(state)
        decompressed = compressor.decompress_state(compressed)

        assert decompressed == state

    def test_compress_large_state(self):
        """Test compressing large state."""
        compressor = DeterministicCompressor()

        # Create large state
        state = {
            "tasks": [
                {"id": f"task-{i}", "status": "completed", "data": "x" * 100}
                for i in range(100)
            ]
        }

        compressed = compressor.compress_state(state)
        decompressed = compressor.decompress_state(compressed)

        assert decompressed == state

        # Should achieve good compression
        import json

        original_size = len(json.dumps(state).encode("utf-8"))
        compression_ratio = len(compressed) / original_size
        assert compression_ratio < 0.5  # At least 50% compression

    def test_decompress_invalid_data(self):
        """Test decompressing invalid data."""
        compressor = DeterministicCompressor()

        result = compressor.decompress_state(b"invalid compressed data")
        assert result is None

    def test_deterministic_compression(self):
        """Test that compression is deterministic."""
        compressor1 = DeterministicCompressor()
        compressor2 = DeterministicCompressor()

        state = {"test": "data", "number": 42, "list": [1, 2, 3]}

        # Compress same state with different instances
        compressed1 = compressor1.compress_state(state)
        compressed2 = compressor2.compress_state(state)

        # Should produce identical results
        assert compressed1 == compressed2

    def test_compress_thread(self):
        """Test compressing thread operations."""
        compressor = DeterministicCompressor()

        thread_ops = [
            {"op_id": "op-1", "thread_id": "thread-1", "lamport": 1, "data": "test1"},
            {"op_id": "op-2", "thread_id": "thread-1", "lamport": 2, "data": "test2"},
            {"op_id": "op-3", "thread_id": "thread-1", "lamport": 3, "data": "test3"},
        ]

        summary = compressor.compress_thread(thread_ops)

        assert summary["op_count"] == 3
        assert summary["thread_id"] == "thread-1"
        assert summary["first_lamport"] == 1
        assert summary["last_lamport"] == 3
        assert "compressed_ops" in summary
        assert "original_hash" in summary
        assert summary["compression_ratio"] <= 1.0

    def test_compress_decompress_thread(self):
        """Test compress and decompress thread cycle."""
        compressor = DeterministicCompressor()

        original_ops = [
            {"op_id": f"op-{i}", "thread_id": "thread-1", "lamport": i}
            for i in range(10)
        ]

        # Compress
        summary = compressor.compress_thread(original_ops)

        # Decompress
        decompressed_ops = compressor.decompress_thread(summary)

        assert decompressed_ops == original_ops

    def test_verify_compressed_valid(self):
        """Test verifying valid compressed data."""
        compressor = DeterministicCompressor()

        original = {"test": "data", "number": 42}

        compressed = compressor.compress_state(original)
        decompressed = compressor.decompress_state(compressed)

        is_valid = compressor.verify_compressed(original, decompressed)
        assert is_valid is True

    def test_verify_compressed_invalid(self):
        """Test verifying invalid compressed data."""
        compressor = DeterministicCompressor()

        original = {"test": "data"}
        modified = {"test": "modified"}

        is_valid = compressor.verify_compressed(original, modified)
        assert is_valid is False

    def test_get_compression_stats(self):
        """Test getting compression stats."""
        compressor = DeterministicCompressor(compression_level=5)

        stats = compressor.get_compression_stats()

        assert stats["compression_level"] == 5
        assert stats["algorithm"] == "zstandard"
        assert stats["deterministic"] is True

    def test_compress_batch(self):
        """Test batch compression."""
        compressor = DeterministicCompressor()

        items = [{"id": f"item-{i}", "data": f"data-{i}"} for i in range(100)]

        compressed_items = compressor.compress_batch(items)

        assert len(compressed_items) == 100
        assert all(isinstance(item, bytes) for item in compressed_items)

    def test_compress_batch_with_max_size(self):
        """Test batch compression with max size."""
        compressor = DeterministicCompressor()

        items = [{"id": i} for i in range(250)]

        compressed_items = compressor.compress_batch(items, max_batch_size=100)

        # Should still compress all items
        assert len(compressed_items) == 250

    def test_different_compression_levels(self):
        """Test different compression levels."""
        state = {"data": "x" * 1000}

        # Test different levels
        compressor_low = DeterministicCompressor(compression_level=1)
        compressor_high = DeterministicCompressor(compression_level=10)

        compressed_low = compressor_low.compress_state(state)
        compressed_high = compressor_high.compress_state(state)

        # Higher compression should produce smaller result
        assert len(compressed_high) <= len(compressed_low)

        # Both should decompress correctly
        decompressed_low = compressor_low.decompress_state(compressed_low)
        decompressed_high = compressor_high.decompress_state(compressed_high)

        assert decompressed_low == state
        assert decompressed_high == state

    def test_canonical_json_ordering(self):
        """Test that key ordering doesn't affect compression."""
        compressor = DeterministicCompressor()

        # Same data, different key order
        state1 = {"b": 2, "a": 1, "c": 3}
        state2 = {"a": 1, "c": 3, "b": 2}

        compressed1 = compressor.compress_state(state1)
        compressed2 = compressor.compress_state(state2)

        # Should produce identical compressed data
        assert compressed1 == compressed2


class TestIntegration:
    """Integration tests for compression."""

    def test_checkpoint_compression_integration(self):
        """Test compression with checkpoint manager."""
        import tempfile
        from pathlib import Path
        from checkpoint import CheckpointManager

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create manager with compression enabled
            manager = CheckpointManager(
                Path(tmpdir), enable_compression=True, compression_level=3
            )

            # Create large state
            large_state = {"tasks": [{"id": i, "data": "x" * 100} for i in range(100)]}

            # Create checkpoint
            checkpoint = manager.create_checkpoint(
                epoch=1, plan_state=large_state, op_hashes=["hash-1"]
            )

            # Sign and store
            signed = manager.sign_checkpoint(checkpoint, [])
            path = manager.store_checkpoint(signed)

            # Load it back
            loaded = manager.load_checkpoint(path)

            # Should match original
            assert loaded is not None
            assert loaded.checkpoint.state_summary == large_state

    def test_compression_space_savings(self):
        """Test that compression actually saves space."""
        import tempfile
        from pathlib import Path
        from checkpoint import CheckpointManager

        with tempfile.TemporaryDirectory() as tmpdir:
            large_state = {
                "tasks": [
                    {"id": i, "status": "completed", "result": "success" * 10}
                    for i in range(500)
                ]
            }

            # Store without compression
            manager_uncompressed = CheckpointManager(
                Path(tmpdir) / "uncompressed", enable_compression=False
            )
            cp = manager_uncompressed.create_checkpoint(1, large_state, ["hash"])
            signed = manager_uncompressed.sign_checkpoint(cp, [])
            path_uncompressed = manager_uncompressed.store_checkpoint(signed)

            # Store with compression
            manager_compressed = CheckpointManager(
                Path(tmpdir) / "compressed", enable_compression=True
            )
            cp = manager_compressed.create_checkpoint(1, large_state, ["hash"])
            signed = manager_compressed.sign_checkpoint(cp, [])
            path_compressed = manager_compressed.store_checkpoint(signed)

            # Compressed should be smaller
            size_uncompressed = path_uncompressed.stat().st_size
            size_compressed = path_compressed.stat().st_size

            assert size_compressed < size_uncompressed

            # Should achieve at least 30% compression
            ratio = size_compressed / size_uncompressed
            assert ratio < 0.7
