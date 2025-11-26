"""Deterministic compression for state and checkpoints.

Provides consistent compression of plan state and thread operations
using zstandard for efficient storage and network transfer.
"""

import json
import hashlib
import logging
from typing import Dict, List, Optional, Any
import zstandard as zstd

logger = logging.getLogger(__name__)


class DeterministicCompressor:
    """
    Deterministic compression for plan state and operations.
    
    Uses zstandard compression with deterministic settings to ensure
    identical compression results for the same input.
    """
    
    def __init__(self, compression_level: int = 3):
        """
        Initialize compressor.
        
        Args:
            compression_level: Zstandard compression level (1-22, default: 3)
        """
        self.compression_level = compression_level
        
        # Create compressor with deterministic settings
        self.compressor = zstd.ZstdCompressor(
            level=compression_level,
            write_content_size=True,
            write_checksum=True
        )
        
        # Create decompressor
        self.decompressor = zstd.ZstdDecompressor()
    
    def compress_state(self, plan_state: Dict) -> bytes:
        """
        Compress plan state deterministically.
        
        Args:
            plan_state: Plan state dictionary
            
        Returns:
            Compressed bytes
        """
        # Convert to canonical JSON (sorted keys, no whitespace)
        canonical_json = json.dumps(
            plan_state,
            sort_keys=True,
            separators=(',', ':')
        )
        
        # Encode to UTF-8
        data_bytes = canonical_json.encode('utf-8')
        
        # Compress
        compressed = self.compressor.compress(data_bytes)
        
        compression_ratio = len(compressed) / len(data_bytes) if data_bytes else 0
        
        logger.debug(
            f"Compressed state: {len(data_bytes)} -> {len(compressed)} bytes "
            f"({compression_ratio:.1%} ratio)"
        )
        
        return compressed
    
    def decompress_state(self, data: bytes) -> Optional[Dict]:
        """
        Decompress plan state.
        
        Args:
            data: Compressed bytes
            
        Returns:
            Decompressed plan state dictionary, or None if error
        """
        try:
            # Decompress
            decompressed_bytes = self.decompressor.decompress(data)
            
            # Decode UTF-8
            json_str = decompressed_bytes.decode('utf-8')
            
            # Parse JSON
            plan_state = json.loads(json_str)
            
            logger.debug(
                f"Decompressed state: {len(data)} -> {len(decompressed_bytes)} bytes"
            )
            
            return plan_state
            
        except Exception as e:
            logger.error(f"Failed to decompress state: {e}")
            return None
    
    def compress_thread(self, thread_ops: List[Dict]) -> Dict:
        """
        Compress thread operations into a summary.
        
        Args:
            thread_ops: List of operation dictionaries
            
        Returns:
            Compressed thread summary with metadata
        """
        # Create summary structure
        summary = {
            "op_count": len(thread_ops),
            "thread_id": thread_ops[0].get("thread_id") if thread_ops else None,
            "first_lamport": thread_ops[0].get("lamport") if thread_ops else 0,
            "last_lamport": thread_ops[-1].get("lamport") if thread_ops else 0,
        }
        
        # Convert ops to canonical JSON
        canonical_json = json.dumps(
            thread_ops,
            sort_keys=True,
            separators=(',', ':')
        )
        data_bytes = canonical_json.encode('utf-8')
        
        # Compress operations
        compressed_ops = self.compressor.compress(data_bytes)
        
        # Compute hash of original data for verification
        original_hash = hashlib.sha256(data_bytes).hexdigest()
        
        summary.update({
            "compressed_ops": compressed_ops,
            "compressed_size": len(compressed_ops),
            "original_size": len(data_bytes),
            "original_hash": original_hash,
            "compression_ratio": len(compressed_ops) / len(data_bytes)
        })
        
        logger.info(
            f"Compressed thread {summary['thread_id']}: "
            f"{len(thread_ops)} ops, "
            f"{len(data_bytes)} -> {len(compressed_ops)} bytes "
            f"({summary['compression_ratio']:.1%})"
        )
        
        return summary
    
    def decompress_thread(self, summary: Dict) -> Optional[List[Dict]]:
        """
        Decompress thread operations from summary.
        
        Args:
            summary: Compressed thread summary
            
        Returns:
            List of operation dictionaries, or None if error
        """
        try:
            compressed_ops = summary.get("compressed_ops")
            if not compressed_ops:
                logger.error("No compressed_ops in summary")
                return None
            
            # Decompress
            decompressed_bytes = self.decompressor.decompress(compressed_ops)
            
            # Parse JSON
            thread_ops = json.loads(decompressed_bytes.decode('utf-8'))
            
            logger.debug(
                f"Decompressed thread: {len(compressed_ops)} -> "
                f"{len(decompressed_bytes)} bytes, {len(thread_ops)} ops"
            )
            
            return thread_ops
            
        except Exception as e:
            logger.error(f"Failed to decompress thread: {e}")
            return None
    
    def verify_compressed(
        self,
        original: Any,
        decompressed: Any
    ) -> bool:
        """
        Verify that decompressed data matches original.
        
        Args:
            original: Original data (dict or list)
            decompressed: Decompressed data
            
        Returns:
            True if data matches
        """
        # Convert both to canonical JSON for comparison
        original_canonical = json.dumps(
            original,
            sort_keys=True,
            separators=(',', ':')
        )
        
        decompressed_canonical = json.dumps(
            decompressed,
            sort_keys=True,
            separators=(',', ':')
        )
        
        matches = original_canonical == decompressed_canonical
        
        if not matches:
            logger.warning("Verification failed: decompressed data doesn't match original")
        
        return matches
    
    def get_compression_stats(self) -> Dict:
        """
        Get compression statistics.
        
        Returns:
            Statistics dictionary
        """
        return {
            "compression_level": self.compression_level,
            "algorithm": "zstandard",
            "deterministic": True
        }
    
    def compress_batch(
        self,
        items: List[Dict],
        max_batch_size: int = 1000
    ) -> List[bytes]:
        """
        Compress a batch of items individually.
        
        Args:
            items: List of dictionaries to compress
            max_batch_size: Maximum items per batch
            
        Returns:
            List of compressed bytes
        """
        compressed_items = []
        
        for i in range(0, len(items), max_batch_size):
            batch = items[i:i + max_batch_size]
            
            for item in batch:
                canonical_json = json.dumps(
                    item,
                    sort_keys=True,
                    separators=(',', ':')
                )
                compressed = self.compressor.compress(canonical_json.encode('utf-8'))
                compressed_items.append(compressed)
        
        logger.info(
            f"Compressed batch: {len(items)} items"
        )
        
        return compressed_items
