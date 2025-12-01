"""Op-log pruning and tiered storage for bounded growth.

Provides automatic pruning of old operations and tiered storage
to move cold data to disk while keeping hot data in memory.
"""

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PruningPolicy:
    """
    Policy for pruning old operations from op-log.

    Keeps recent epochs in hot storage and prunes older ops
    after checkpoints are created.
    """

    keep_epochs: int = 10  # Number of recent epochs to keep
    min_ops_per_epoch: int = 100  # Minimum ops before pruning an epoch

    def should_prune(self, op_epoch: int, current_epoch: int) -> bool:
        """
        Determine if an operation should be pruned.

        Args:
            op_epoch: Epoch the operation belongs to
            current_epoch: Current epoch number

        Returns:
            True if operation should be pruned
        """
        # Keep operations from recent epochs
        epochs_ago = current_epoch - op_epoch

        if epochs_ago <= self.keep_epochs:
            return False

        return True

    def get_pruning_threshold(self, current_epoch: int) -> int:
        """
        Get the epoch threshold below which ops should be pruned.

        Args:
            current_epoch: Current epoch number

        Returns:
            Epoch threshold (inclusive)
        """
        return current_epoch - self.keep_epochs


class TieredStorage:
    """
    Two-tier storage: hot (memory) and cold (disk).

    Hot tier keeps recent/frequently accessed ops in memory.
    Cold tier archives old ops to disk for space efficiency.
    """

    def __init__(self, cold_storage_path: Optional[Path] = None):
        """
        Initialize tiered storage.

        Args:
            cold_storage_path: Directory for cold storage (default: ./cold_storage)
        """
        # Hot tier: in-memory cache
        self.hot_tier: Dict[str, dict] = {}

        # Cold tier: disk-based storage
        self.cold_storage_path = cold_storage_path or Path("./cold_storage")
        self.cold_storage_path.mkdir(parents=True, exist_ok=True)

        # Track which ops are in cold storage
        self.cold_index: Set[str] = set()

        # Load cold index
        self._load_cold_index()

    def add_to_hot(self, op_id: str, op_data: dict) -> None:
        """
        Add operation to hot tier.

        Args:
            op_id: Operation identifier
            op_data: Operation data
        """
        self.hot_tier[op_id] = op_data

    def get_from_hot(self, op_id: str) -> Optional[dict]:
        """
        Retrieve operation from hot tier.

        Args:
            op_id: Operation identifier

        Returns:
            Operation data if in hot tier, None otherwise
        """
        return self.hot_tier.get(op_id)

    def move_to_cold(self, ops: List[dict]) -> int:
        """
        Move operations from hot to cold tier.

        Args:
            ops: List of operations to move

        Returns:
            Number of operations moved
        """
        moved = 0

        for op in ops:
            op_id = op.get("op_id")
            if not op_id:
                continue

            # Write to cold storage
            if self._write_to_cold(op_id, op):
                # Remove from hot tier
                if op_id in self.hot_tier:
                    del self.hot_tier[op_id]

                # Add to cold index
                self.cold_index.add(op_id)
                moved += 1

        # Update cold index
        self._save_cold_index()

        logger.info(f"Moved {moved} operations to cold storage")

        return moved

    def retrieve_from_cold(self, op_ids: List[str]) -> List[dict]:
        """
        Retrieve operations from cold tier.

        Args:
            op_ids: List of operation identifiers

        Returns:
            List of operation data (may be incomplete if some ops not found)
        """
        ops = []

        for op_id in op_ids:
            if op_id in self.cold_index:
                op_data = self._read_from_cold(op_id)
                if op_data:
                    ops.append(op_data)

        logger.debug(f"Retrieved {len(ops)}/{len(op_ids)} operations from cold storage")

        return ops

    def get_op(self, op_id: str) -> Optional[dict]:
        """
        Get operation from either tier.

        Args:
            op_id: Operation identifier

        Returns:
            Operation data if found
        """
        # Try hot tier first
        op = self.get_from_hot(op_id)
        if op:
            return op

        # Try cold tier
        if op_id in self.cold_index:
            return self._read_from_cold(op_id)

        return None

    def prune_from_hot(self, op_ids: List[str]) -> int:
        """
        Remove operations from hot tier (used after moving to cold).

        Args:
            op_ids: Operation identifiers to prune

        Returns:
            Number pruned
        """
        pruned = 0

        for op_id in op_ids:
            if op_id in self.hot_tier:
                del self.hot_tier[op_id]
                pruned += 1

        return pruned

    def get_hot_tier_size(self) -> int:
        """Get number of operations in hot tier."""
        return len(self.hot_tier)

    def get_cold_tier_size(self) -> int:
        """Get number of operations in cold tier."""
        return len(self.cold_index)

    def _write_to_cold(self, op_id: str, op_data: dict) -> bool:
        """
        Write operation to cold storage.

        Args:
            op_id: Operation identifier
            op_data: Operation data

        Returns:
            True if written successfully
        """
        try:
            # Create shard directory based on first 2 chars of op_id
            shard = op_id[:2] if len(op_id) >= 2 else "00"
            shard_dir = self.cold_storage_path / shard
            shard_dir.mkdir(exist_ok=True)

            # Write as JSON
            op_file = shard_dir / f"{op_id}.json"
            with open(op_file, "w") as f:
                json.dump(op_data, f)

            return True

        except Exception as e:
            logger.error(f"Failed to write op {op_id} to cold storage: {e}")
            return False

    def _read_from_cold(self, op_id: str) -> Optional[dict]:
        """
        Read operation from cold storage.

        Args:
            op_id: Operation identifier

        Returns:
            Operation data if found
        """
        try:
            shard = op_id[:2] if len(op_id) >= 2 else "00"
            op_file = self.cold_storage_path / shard / f"{op_id}.json"

            if not op_file.exists():
                return None

            with open(op_file, "r") as f:
                return json.load(f)

        except Exception as e:
            logger.error(f"Failed to read op {op_id} from cold storage: {e}")
            return None

    def _get_index_path(self) -> Path:
        """Get path to cold storage index."""
        return self.cold_storage_path / "index.json"

    def _load_cold_index(self) -> None:
        """Load cold storage index from disk."""
        index_path = self._get_index_path()

        if not index_path.exists():
            return

        try:
            with open(index_path, "r") as f:
                data = json.load(f)
                self.cold_index = set(data.get("op_ids", []))

            logger.debug(f"Loaded cold index with {len(self.cold_index)} ops")

        except Exception as e:
            logger.error(f"Failed to load cold index: {e}")

    def _save_cold_index(self) -> None:
        """Save cold storage index to disk."""
        index_path = self._get_index_path()

        try:
            with open(index_path, "w") as f:
                json.dump({"op_ids": list(self.cold_index)}, f)

        except Exception as e:
            logger.error(f"Failed to save cold index: {e}")


class PruningManager:
    """
    Manages pruning and tiered storage for op-logs.

    Coordinates between pruning policy and tiered storage.
    """

    def __init__(
        self,
        policy: Optional[PruningPolicy] = None,
        storage: Optional[TieredStorage] = None,
    ):
        """
        Initialize pruning manager.

        Args:
            policy: Pruning policy (default: PruningPolicy())
            storage: Tiered storage (default: TieredStorage())
        """
        self.policy = policy or PruningPolicy()
        self.storage = storage or TieredStorage()

    def prune_before_epoch(
        self, ops: List[dict], current_epoch: int
    ) -> tuple[int, int]:
        """
        Prune operations before threshold epoch.

        Args:
            ops: List of all operations
            current_epoch: Current epoch number

        Returns:
            Tuple of (moved_to_cold, kept_in_hot)
        """
        threshold_epoch = self.policy.get_pruning_threshold(current_epoch)

        to_cold = []
        to_cold_ids = []
        kept = 0

        for op in ops:
            op_epoch = op.get("epoch", 0)

            if op_epoch < threshold_epoch:
                to_cold.append(op)
                to_cold_ids.append(op.get("op_id"))
            else:
                kept += 1

        # Move old ops to cold storage
        moved = self.storage.move_to_cold(to_cold)

        # Remove from hot tier the ops that were successfully moved
        if moved > 0:
            self.storage.prune_from_hot(to_cold_ids[:moved])

        logger.info(
            f"Pruned ops before epoch {threshold_epoch}: "
            f"{moved} moved to cold, {kept} kept in hot"
        )

        return (moved, kept)

    def get_stats(self) -> dict:
        """
        Get pruning and storage statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "policy": {
                "keep_epochs": self.policy.keep_epochs,
                "min_ops_per_epoch": self.policy.min_ops_per_epoch,
            },
            "storage": {
                "hot_tier_size": self.storage.get_hot_tier_size(),
                "cold_tier_size": self.storage.get_cold_tier_size(),
                "total_size": (
                    self.storage.get_hot_tier_size() + self.storage.get_cold_tier_size()
                ),
            },
        }
