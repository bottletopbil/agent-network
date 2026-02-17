"""
Epoch management for partition fencing in distributed consensus.

Provides epoch-based fencing to handle network partitions and ensure
deterministic recovery when partitions heal.
"""

import time
import sqlite3
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class EpochState:
    """State information for a consensus epoch"""

    epoch_number: int
    started_at_ns: int
    coordinator_id: str


class EpochManager:
    """
    Manages epochs for partition fencing.

    Epochs provide a monotonically increasing counter that advances
    when network partitions heal. Higher epoch numbers fence out
    decisions made in lower epochs.
    
    Epoch state is persisted to SQLite to survive node restarts.
    """

    def __init__(self, db_path: str = ".state/epochs.db"):
        """
        Initialize epoch manager with persistent storage.
        
        Args:
            db_path: Path to SQLite database for epoch persistence
        """
        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema()
        
        # Load or initialize epoch state
        self._load_or_init_state()

    def _init_schema(self):
        """Create epoch state table if it doesn't exist"""
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS epoch_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    epoch_number INTEGER NOT NULL,
                    started_at_ns INTEGER NOT NULL,
                    coordinator_id TEXT NOT NULL
                )
                """
            )

    def _load_or_init_state(self):
        """Load epoch state from database or initialize if not found"""
        cursor = self.conn.execute("SELECT epoch_number, started_at_ns, coordinator_id FROM epoch_state WHERE id = 1")
        row = cursor.fetchone()
        
        if row:
            # Load existing state
            self.current_epoch = row[0]
            self.epoch_start = row[1]
            self.coordinator_id = row[2]
            print(f"[EPOCH] Loaded persisted state: epoch {self.current_epoch}")
        else:
            # Initialize new state
            self.current_epoch = 1
            self.epoch_start = time.time_ns()
            self.coordinator_id = "system"
            self._persist_state()
            print(f"[EPOCH] Initialized new epoch state: epoch {self.current_epoch}")

    def _persist_state(self):
        """Save current epoch state to database"""
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO epoch_state (id, epoch_number, started_at_ns, coordinator_id)
                VALUES (1, ?, ?, ?)
                """,
                (self.current_epoch, self.epoch_start, self.coordinator_id)
            )

    def get_current_epoch(self) -> int:
        """
        Get current epoch number.

        Returns:
            Current epoch number (starts at 1)
        """
        return self.current_epoch

    def create_fence_token(self, epoch: Optional[int] = None) -> str:
        """
        Create fencing token for an epoch.

        Fencing tokens prevent stale operations from lower epochs
        from being accepted after partition heal.

        Args:
            epoch: Epoch number (default: current epoch)

        Returns:
            Fencing token string: "epoch-{N}-{timestamp}"
        """
        if epoch is None:
            epoch = self.current_epoch
        return f"epoch-{epoch}-{self.epoch_start}"

    def validate_fence_token(self, token: str, current_epoch: int) -> bool:
        """
        Validate that a fencing token is not stale.

        Args:
            token: Fencing token to validate
            current_epoch: Current epoch number

        Returns:
            True if token is valid (epoch >= current), False if stale
        """
        try:
            parts = token.split("-")
            if len(parts) < 2:
                return False
            token_epoch = int(parts[1])
            return token_epoch >= current_epoch
        except (ValueError, IndexError):
            return False

    def advance_epoch(self, reason: str = "manual") -> int:
        """
        Advance to next epoch.

        Called when partition heals to fence out stale decisions
        from the previous epoch.

        Args:
            reason: Reason for epoch advancement (for logging)

        Returns:
            New epoch number
        """
        old_epoch = self.current_epoch
        self.current_epoch += 1
        self.epoch_start = time.time_ns()
        
        # Persist new epoch state immediately
        self._persist_state()

        print(f"[EPOCH] Advanced from epoch {old_epoch} to {self.current_epoch} (reason: {reason})")

        return self.current_epoch

    def get_epoch_state(self) -> EpochState:
        """Get current epoch state"""
        return EpochState(
            epoch_number=self.current_epoch,
            started_at_ns=self.epoch_start,
            coordinator_id=self.coordinator_id,
        )


# Global epoch manager instance
epoch_manager = EpochManager()
