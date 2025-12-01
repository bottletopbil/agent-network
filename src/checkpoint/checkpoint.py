"""Checkpoint management for epoch-based state snapshots.

Provides creation, signing, storage, and loading of checkpoints with
Merkle tree commitments to plan state.
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from pathlib import Path
import logging

from .merkle import MerkleTree

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """
    Epoch checkpoint with cryptographic commitment to state.

    Contains Merkle root of all plan ops, state summary, and metadata.
    """

    epoch: int
    merkle_root: str
    state_summary: Dict
    timestamp_ns: int
    op_count: int
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "Checkpoint":
        """Create from dictionary."""
        return cls(**data)

    def compute_hash(self) -> str:
        """
        Compute deterministic hash of checkpoint.

        Returns:
            Hex-encoded SHA256 hash
        """
        # Create canonical representation
        canonical = {
            "epoch": self.epoch,
            "merkle_root": self.merkle_root,
            "op_count": self.op_count,
            "timestamp_ns": self.timestamp_ns,
            "state_summary": self.state_summary,
        }

        # Sort keys for determinism
        canonical_json = json.dumps(canonical, sort_keys=True)

        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


@dataclass
class SignedCheckpoint:
    """Checkpoint with verifier signatures."""

    checkpoint: Checkpoint
    signatures: List[Dict] = field(default_factory=list)  # [{verifier_id, signature}]

    def add_signature(self, verifier_id: str, signature: str):
        """Add a verifier signature."""
        self.signatures.append({"verifier_id": verifier_id, "signature": signature})

    def verify_quorum(self, required_count: int) -> bool:
        """
        Verify that checkpoint has enough signatures.

        Args:
            required_count: Minimum number of signatures required

        Returns:
            True if quorum reached
        """
        return len(self.signatures) >= required_count

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {"checkpoint": self.checkpoint.to_dict(), "signatures": self.signatures}

    @classmethod
    def from_dict(cls, data: Dict) -> "SignedCheckpoint":
        """Create from dictionary."""
        return cls(
            checkpoint=Checkpoint.from_dict(data["checkpoint"]),
            signatures=data.get("signatures", []),
        )


class CheckpointManager:
    """
    Manages epoch checkpoints with Merkle commitments.

    Provides creation, signing, persistence, and loading of checkpoints
    with optional compression.
    """

    def __init__(
        self,
        checkpoint_dir: Optional[Path] = None,
        enable_compression: bool = True,
        compression_level: int = 3,
    ):
        """
        Initialize checkpoint manager.

        Args:
            checkpoint_dir: Directory to store checkpoints (default: ./checkpoints)
            enable_compression: Enable state compression (default: True)
            compression_level: Zstandard compression level 1-22 (default: 3)
        """
        self.checkpoint_dir = checkpoint_dir or Path("./checkpoints")
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Cache of loaded checkpoints
        self.checkpoints: Dict[int, SignedCheckpoint] = {}

        # Compression settings
        self.enable_compression = enable_compression
        self.compressor = None

        if enable_compression:
            from .compression import DeterministicCompressor

            self.compressor = DeterministicCompressor(compression_level)

    def create_checkpoint(self, epoch: int, plan_state: Dict, op_hashes: List[str]) -> Checkpoint:
        """
        Create a new checkpoint from current state.

        Args:
            epoch: Epoch number
            plan_state: Summary of plan state
            op_hashes: List of operation hashes to commit to

        Returns:
            Created Checkpoint
        """
        import time

        # Build Merkle tree from operation hashes
        merkle = MerkleTree()
        root = merkle.build_tree(op_hashes)

        checkpoint = Checkpoint(
            epoch=epoch,
            merkle_root=root,
            state_summary=plan_state,
            timestamp_ns=int(time.time() * 1_000_000_000),
            op_count=len(op_hashes),
        )

        logger.info(
            f"Created checkpoint for epoch {epoch}, " f"{len(op_hashes)} ops, root: {root[:8]}..."
        )

        return checkpoint

    def sign_checkpoint(
        self, checkpoint: Checkpoint, verifier_signatures: List[Dict]
    ) -> SignedCheckpoint:
        """
        Create signed checkpoint with verifier signatures.

        Args:
            checkpoint: Checkpoint to sign
            verifier_signatures: List of {verifier_id, signature} dicts

        Returns:
            SignedCheckpoint
        """
        signed = SignedCheckpoint(checkpoint=checkpoint, signatures=verifier_signatures)

        logger.info(
            f"Signed checkpoint epoch {checkpoint.epoch} "
            f"with {len(verifier_signatures)} signatures"
        )

        return signed

    def store_checkpoint(self, checkpoint: SignedCheckpoint, path: Optional[Path] = None) -> Path:
        """
        Store checkpoint to disk with optional compression.

        Args:
            checkpoint: SignedCheckpoint to store
            path: Optional custom path (default: managed path)

        Returns:
            Path where checkpoint was stored
        """
        if path is None:
            path = self._get_checkpoint_path(checkpoint.checkpoint.epoch)

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict
        checkpoint_dict = checkpoint.to_dict()

        # Compress if enabled
        if self.enable_compression and self.compressor:
            # Compress the state_summary
            state = checkpoint.checkpoint.state_summary
            compressed_state = self.compressor.compress_state(state)

            # Store compressed data and mark as compressed
            checkpoint_dict["checkpoint"]["state_summary"] = {
                "_compressed": True,
                "_data": compressed_state.hex(),
            }

        # Write as JSON
        with open(path, "w") as f:
            json.dump(checkpoint_dict, f, indent=2)

        logger.info(f"Stored checkpoint epoch {checkpoint.checkpoint.epoch} to {path}")

        # Cache it
        self.checkpoints[checkpoint.checkpoint.epoch] = checkpoint

        return path

    def load_checkpoint(self, path: Path) -> Optional[SignedCheckpoint]:
        """
        Load checkpoint from disk with decompression if needed.

        Args:
            path: Path to checkpoint file

        Returns:
            SignedCheckpoint if successful, None otherwise
        """
        try:
            with open(path, "r") as f:
                data = json.load(f)

            # Check if state is compressed
            state = data["checkpoint"]["state_summary"]
            if isinstance(state, dict) and state.get("_compressed"):
                # Decompress state
                if self.compressor:
                    compressed_bytes = bytes.fromhex(state["_data"])
                    decompressed_state = self.compressor.decompress_state(compressed_bytes)
                    if decompressed_state:
                        data["checkpoint"]["state_summary"] = decompressed_state
                else:
                    logger.warning("Checkpoint is compressed but no compressor available")

            checkpoint = SignedCheckpoint.from_dict(data)

            logger.info(f"Loaded checkpoint epoch {checkpoint.checkpoint.epoch} from {path}")

            # Cache it
            self.checkpoints[checkpoint.checkpoint.epoch] = checkpoint

            return checkpoint

        except Exception as e:
            logger.error(f"Failed to load checkpoint from {path}: {e}")
            return None

    def get_checkpoint(self, epoch: int) -> Optional[SignedCheckpoint]:
        """
        Get checkpoint for an epoch.

        Loads from disk if not cached.

        Args:
            epoch: Epoch number

        Returns:
            SignedCheckpoint if exists
        """
        # Check cache
        if epoch in self.checkpoints:
            return self.checkpoints[epoch]

        # Try to load from disk
        path = self._get_checkpoint_path(epoch)
        if path.exists():
            return self.load_checkpoint(path)

        return None

    def get_latest_checkpoint(self) -> Optional[SignedCheckpoint]:
        """
        Get the most recent checkpoint.

        Returns:
            Latest SignedCheckpoint if any exist
        """
        # Find all checkpoint files
        checkpoint_files = sorted(self.checkpoint_dir.glob("checkpoint_epoch_*.json"), reverse=True)

        if not checkpoint_files:
            return None

        # Load the latest
        return self.load_checkpoint(checkpoint_files[0])

    def list_checkpoints(self) -> List[int]:
        """
        List all available checkpoint epochs.

        Returns:
            Sorted list of epoch numbers
        """
        epochs = []

        for path in self.checkpoint_dir.glob("checkpoint_epoch_*.json"):
            try:
                # Extract epoch from filename
                epoch_str = path.stem.split("_")[-1]
                epochs.append(int(epoch_str))
            except (ValueError, IndexError):
                logger.warning(f"Invalid checkpoint filename: {path}")

        return sorted(epochs)

    def delete_checkpoint(self, epoch: int) -> bool:
        """
        Delete a checkpoint.

        Args:
            epoch: Epoch number

        Returns:
            True if deleted successfully
        """
        path = self._get_checkpoint_path(epoch)

        if not path.exists():
            return False

        try:
            path.unlink()

            # Remove from cache
            if epoch in self.checkpoints:
                del self.checkpoints[epoch]

            logger.info(f"Deleted checkpoint epoch {epoch}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete checkpoint epoch {epoch}: {e}")
            return False

    def _get_checkpoint_path(self, epoch: int) -> Path:
        """
        Get standard path for a checkpoint.

        Args:
            epoch: Epoch number

        Returns:
            Path to checkpoint file
        """
        return self.checkpoint_dir / f"checkpoint_epoch_{epoch}.json"
