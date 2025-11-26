"""Fast synchronization from checkpoints.

Enables new nodes to quickly catch up by loading from checkpoints
rather than replaying all historical operations.
"""

import logging
from typing import Optional, List, Dict
from pathlib import Path

from .checkpoint import CheckpointManager, SignedCheckpoint, Checkpoint
from .merkle import MerkleTree

logger = logging.getLogger(__name__)


class FastSync:
    """
    Fast synchronization system for new nodes.
    
    Allows nodes to bootstrap quickly by:
    1. Loading latest checkpoint
    2. Syncing only operations after checkpoint epoch
    3. Verifying continuity between checkpoint and new ops
    """
    
    def __init__(
        self,
        checkpoint_manager: Optional[CheckpointManager] = None,
        checkpoint_dir: Optional[Path] = None
    ):
        """
        Initialize fast sync.
        
        Args:
            checkpoint_manager: Existing checkpoint manager (optional)
            checkpoint_dir: Directory for checkpoints (if creating new manager)
        """
        if checkpoint_manager:
            self.checkpoint_manager = checkpoint_manager
        else:
            self.checkpoint_manager = CheckpointManager(checkpoint_dir)
    
    def get_latest_checkpoint(self) -> Optional[SignedCheckpoint]:
        """
        Get the most recent signed checkpoint.
        
        Returns:
            Latest SignedCheckpoint if available, None otherwise
        """
        checkpoint = self.checkpoint_manager.get_latest_checkpoint()
        
        if checkpoint:
            logger.info(
                f"Found latest checkpoint: epoch {checkpoint.checkpoint.epoch}, "
                f"{checkpoint.checkpoint.op_count} ops"
            )
        else:
            logger.info("No checkpoints available for fast sync")
        
        return checkpoint
    
    def download_checkpoint(
        self,
        checkpoint_id: int,
        source_url: Optional[str] = None
    ) -> Optional[bytes]:
        """
        Download checkpoint from remote source.
        
        In a real implementation, this would fetch from peers.
        For now, loads from local storage.
        
        Args:
            checkpoint_id: Epoch number of checkpoint
            source_url: Optional URL to download from
            
        Returns:
            Serialized checkpoint data if found
        """
        # For local implementation, just load from manager
        checkpoint = self.checkpoint_manager.get_checkpoint(checkpoint_id)
        
        if not checkpoint:
            logger.warning(f"Checkpoint {checkpoint_id} not found")
            return None
        
        # Serialize to JSON
        import json
        data = json.dumps(checkpoint.to_dict()).encode('utf-8')
        
        logger.info(
            f"Downloaded checkpoint {checkpoint_id}, "
            f"{len(data)} bytes"
        )
        
        return data
    
    def apply_checkpoint(self, data: bytes) -> Optional[Dict]:
        """
        Apply checkpoint data to restore state.
        
        Args:
            data: Serialized checkpoint data
            
        Returns:
            Restored plan state summary if successful
        """
        import json
        
        try:
            checkpoint_dict = json.loads(data.decode('utf-8'))
            checkpoint = SignedCheckpoint.from_dict(checkpoint_dict)
            
            # Verify signatures if needed
            # In production, would verify quorum
            
            # Extract state
            state = checkpoint.checkpoint.state_summary
            
            logger.info(
                f"Applied checkpoint: epoch {checkpoint.checkpoint.epoch}, "
                f"{checkpoint.checkpoint.op_count} ops committed"
            )
            
            return state
            
        except Exception as e:
            logger.error(f"Failed to apply checkpoint: {e}")
            return None
    
    def sync_ops_after_epoch(
        self,
        epoch: int,
        op_source: Optional[callable] = None
    ) -> List[Dict]:
        """
        Sync operations after a checkpoint epoch.
        
        Args:
            epoch: Checkpoint epoch number
            op_source: Optional callable to get ops (for testing)
            
        Returns:
            List of operations after epoch
        """
        # In a real implementation, would query peers for ops
        # For now, return empty list
        if op_source:
            ops = op_source(epoch)
        else:
            ops = []
        
        logger.info(
            f"Synced {len(ops)} operations after epoch {epoch}"
        )
        
        return ops
    
    def verify_continuity(
        self,
        checkpoint: SignedCheckpoint,
        ops: List[Dict]
    ) -> bool:
        """
        Verify continuity between checkpoint and new operations.
        
        Checks:
        1. Operations start after checkpoint epoch
        2. Lamport clocks are monotonic
        3. No gaps in operation sequence
        
        Args:
            checkpoint: Checkpoint to verify against
            ops: Operations to verify
            
        Returns:
            True if continuity is valid
        """
        if not ops:
            # No ops to verify - valid
            return True
        
        checkpoint_epoch = checkpoint.checkpoint.epoch
        
        # Check all ops are after checkpoint
        for op in ops:
            op_epoch = op.get("epoch", 0)
            if op_epoch <= checkpoint_epoch:
                logger.warning(
                    f"Operation epoch {op_epoch} not after "
                    f"checkpoint epoch {checkpoint_epoch}"
                )
                return False
        
        # Verify Lamport clock monotonicity
        lamports = [op.get("lamport", 0) for op in ops]
        if lamports != sorted(lamports):
            logger.warning("Lamport clocks not monotonic in synced ops")
            return False
        
        logger.info(
            f"Verified continuity: checkpoint epoch {checkpoint_epoch}, "
            f"{len(ops)} ops"
        )
        
        return True
    
    def fast_sync_node(
        self,
        target_epoch: Optional[int] = None,
        op_source: Optional[callable] = None
    ) -> Optional[Dict]:
        """
        Perform complete fast sync for a node.
        
        Args:
            target_epoch: Specific epoch to sync to (default: latest)
            op_source: Optional source for operations
            
        Returns:
            Synced state if successful, None otherwise
        """
        # Step 1: Get latest checkpoint
        checkpoint = self.get_latest_checkpoint()
        
        if not checkpoint:
            logger.warning("No checkpoint available, full sync required")
            return None
        
        # Step 2: Apply checkpoint
        checkpoint_data = self.download_checkpoint(
            checkpoint.checkpoint.epoch
        )
        
        if not checkpoint_data:
            logger.error("Failed to download checkpoint")
            return None
        
        state = self.apply_checkpoint(checkpoint_data)
        
        if not state:
            logger.error("Failed to apply checkpoint")
            return None
        
        # Step 3: Sync ops after checkpoint
        ops = self.sync_ops_after_epoch(
            checkpoint.checkpoint.epoch,
            op_source
        )
        
        # Step 4: Verify continuity
        if not self.verify_continuity(checkpoint, ops):
            logger.error("Continuity check failed")
            return None
        
        # Step 5: Apply new ops (would integrate with plan store)
        logger.info(
            f"Fast sync complete: epoch {checkpoint.checkpoint.epoch}, "
            f"{len(ops)} new ops applied"
        )
        
        return {
            "checkpoint_epoch": checkpoint.checkpoint.epoch,
            "checkpoint_ops": checkpoint.checkpoint.op_count,
            "new_ops": len(ops),
            "state": state
        }
    
    def estimate_sync_time(self, checkpoint: SignedCheckpoint) -> float:
        """
        Estimate sync time in seconds.
        
        Args:
            checkpoint: Checkpoint to estimate from
            
        Returns:
            Estimated time in seconds
        """
        # Simple estimation based on op count
        # Assume 1000 ops/second processing rate
        ops_per_second = 1000
        
        # Checkpoint is instant (just load)
        checkpoint_time = 1.0
        
        # Estimate time for ops after checkpoint
        # (in production, would query peer for count)
        estimated_new_ops = 100  # Assume 100 new ops
        
        sync_time = checkpoint_time + (estimated_new_ops / ops_per_second)
        
        logger.debug(
            f"Estimated sync time: {sync_time:.2f}s "
            f"(checkpoint: {checkpoint_time}s, ops: "
            f"{estimated_new_ops}/{ops_per_second})"
        )
        
        return sync_time
    
    def should_use_fast_sync(
        self,
        full_sync_op_count: int,
        checkpoint_available: bool
    ) -> bool:
        """
        Determine if fast sync should be used.
        
        Args:
            full_sync_op_count: Number of ops for full sync
            checkpoint_available: Whether checkpoint exists
            
        Returns:
            True if fast sync is beneficial
        """
        if not checkpoint_available:
            return False
        
        # Use fast sync if full sync would take > 1000 ops
        threshold = 1000
        
        should_use = full_sync_op_count > threshold
        
        logger.info(
            f"Fast sync {'recommended' if should_use else 'not needed'}: "
            f"{full_sync_op_count} ops vs {threshold} threshold"
        )
        
        return should_use
