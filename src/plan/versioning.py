"""
Plan Versioning: Track plan state over time with merkle roots for integrity.

Maintains a history of plan versions with:
- Lamport clock timestamps
- Merkle root hashes for state verification
- Ability to retrieve and compare versions
"""

import sqlite3
import json
import hashlib
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import time


@dataclass
class PlanVersion:
    """
    A snapshot of plan state at a specific lamport timestamp.
    """

    version_id: str
    lamport: int
    merkle_root: str  # SHA256 hash of plan state
    timestamp_ns: int
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "version_id": self.version_id,
            "lamport": self.lamport,
            "merkle_root": self.merkle_root,
            "timestamp_ns": self.timestamp_ns,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "PlanVersion":
        """Create PlanVersion from dictionary"""
        return PlanVersion(
            version_id=data["version_id"],
            lamport=data["lamport"],
            merkle_root=data["merkle_root"],
            timestamp_ns=data["timestamp_ns"],
            metadata=data.get("metadata", {}),
        )


class VersionTracker:
    """
    Tracks plan versions over time with SQLite persistence.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.lock = threading.Lock()
        self._init_schema()

    def _init_schema(self):
        """Initialize version tracking tables"""
        with self.lock:
            with self.conn:
                # Version snapshots
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS plan_versions (
                        version_id TEXT PRIMARY KEY,
                        lamport INTEGER NOT NULL,
                        merkle_root TEXT NOT NULL,
                        timestamp_ns INTEGER NOT NULL,
                        metadata_json TEXT,
                        UNIQUE(lamport)
                    )
                """
                )
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_version_lamport ON plan_versions(lamport)"
                )
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_version_merkle ON plan_versions(merkle_root)"
                )

                # State snapshots (for diff computation)
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS plan_snapshots (
                        version_id TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        task_state TEXT NOT NULL,
                        task_data_json TEXT,
                        PRIMARY KEY (version_id, task_id),
                        FOREIGN KEY (version_id) REFERENCES plan_versions(version_id)
                    )
                """
                )
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_snapshot_version ON plan_snapshots(version_id)"
                )

    def _compute_merkle_root(self, plan_state: Dict[str, Any]) -> str:
        """
        Compute merkle root hash of plan state.

        Args:
            plan_state: Dictionary of task_id -> task_data

        Returns:
            SHA256 hash as hex string
        """
        # Sort by task_id for deterministic ordering
        sorted_items = sorted(plan_state.items())

        # Create canonical JSON representation
        canonical = json.dumps(sorted_items, sort_keys=True, separators=(",", ":"))

        # Hash with SHA256
        return hashlib.sha256(canonical.encode()).hexdigest()

    def record_version(
        self,
        plan_state: Dict[str, Any],
        lamport: int,
        version_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PlanVersion:
        """
        Record a snapshot of plan state.

        Args:
            plan_state: Dictionary mapping task_id to task data
            lamport: Lamport timestamp for this version
            version_id: Optional version identifier (generated if not provided)
            metadata: Optional metadata to store with version

        Returns:
            PlanVersion object
        """
        import uuid

        if version_id is None:
            version_id = str(uuid.uuid4())

        if metadata is None:
            metadata = {}

        merkle_root = self._compute_merkle_root(plan_state)
        timestamp_ns = time.time_ns()

        version = PlanVersion(
            version_id=version_id,
            lamport=lamport,
            merkle_root=merkle_root,
            timestamp_ns=timestamp_ns,
            metadata=metadata,
        )

        with self.lock:
            with self.conn:
                # Insert version record
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO plan_versions
                    (version_id, lamport, merkle_root, timestamp_ns, metadata_json)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (
                        version_id,
                        lamport,
                        merkle_root,
                        timestamp_ns,
                        json.dumps(metadata),
                    ),
                )

                # Store snapshot data
                for task_id, task_data in plan_state.items():
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO plan_snapshots
                        (version_id, task_id, task_state, task_data_json)
                        VALUES (?, ?, ?, ?)
                    """,
                        (
                            version_id,
                            task_id,
                            task_data.get("state", "DRAFT"),
                            json.dumps(task_data),
                        ),
                    )

        return version

    def get_version_at_lamport(self, lamport: int) -> Optional[PlanVersion]:
        """
        Retrieve version at or before the specified lamport.

        Args:
            lamport: Lamport timestamp

        Returns:
            PlanVersion or None if not found
        """
        with self.lock:
            cursor = self.conn.execute(
                """
                SELECT version_id, lamport, merkle_root, timestamp_ns, metadata_json
                FROM plan_versions
                WHERE lamport <= ?
                ORDER BY lamport DESC
                LIMIT 1
            """,
                (lamport,),
            )

            row = cursor.fetchone()
            if not row:
                return None

            metadata = json.loads(row[4]) if row[4] else {}

            return PlanVersion(
                version_id=row[0],
                lamport=row[1],
                merkle_root=row[2],
                timestamp_ns=row[3],
                metadata=metadata,
            )

    def get_version_by_id(self, version_id: str) -> Optional[PlanVersion]:
        """
        Retrieve version by ID.

        Args:
            version_id: Version identifier

        Returns:
            PlanVersion or None if not found
        """
        with self.lock:
            cursor = self.conn.execute(
                """
                SELECT version_id, lamport, merkle_root, timestamp_ns, metadata_json
                FROM plan_versions
                WHERE version_id = ?
            """,
                (version_id,),
            )

            row = cursor.fetchone()
            if not row:
                return None

            metadata = json.loads(row[4]) if row[4] else {}

            return PlanVersion(
                version_id=row[0],
                lamport=row[1],
                merkle_root=row[2],
                timestamp_ns=row[3],
                metadata=metadata,
            )

    def get_snapshot_data(self, version_id: str) -> Dict[str, Any]:
        """
        Get the full plan state snapshot for a version.

        Args:
            version_id: Version identifier

        Returns:
            Dictionary mapping task_id to task data
        """
        with self.lock:
            cursor = self.conn.execute(
                """
                SELECT task_id, task_data_json
                FROM plan_snapshots
                WHERE version_id = ?
            """,
                (version_id,),
            )

            snapshot = {}
            for row in cursor:
                task_id = row[0]
                task_data = json.loads(row[1])
                snapshot[task_id] = task_data

            return snapshot

    def compute_diff(self, version_a_id: str, version_b_id: str) -> Dict[str, Any]:
        """
        Compute difference between two versions.

        Args:
            version_a_id: First version ID
            version_b_id: Second version ID

        Returns:
            Dictionary with 'added', 'removed', 'modified' task lists
        """
        snapshot_a = self.get_snapshot_data(version_a_id)
        snapshot_b = self.get_snapshot_data(version_b_id)

        tasks_a = set(snapshot_a.keys())
        tasks_b = set(snapshot_b.keys())

        added = []
        removed = []
        modified = []

        # Find added tasks
        for task_id in tasks_b - tasks_a:
            added.append({"task_id": task_id, "data": snapshot_b[task_id]})

        # Find removed tasks
        for task_id in tasks_a - tasks_b:
            removed.append({"task_id": task_id, "data": snapshot_a[task_id]})

        # Find modified tasks
        for task_id in tasks_a & tasks_b:
            if snapshot_a[task_id] != snapshot_b[task_id]:
                modified.append(
                    {
                        "task_id": task_id,
                        "old_data": snapshot_a[task_id],
                        "new_data": snapshot_b[task_id],
                    }
                )

        return {"added": added, "removed": removed, "modified": modified}

    def get_all_versions(self, limit: int = 100) -> List[PlanVersion]:
        """
        Get all versions, newest first.

        Args:
            limit: Maximum number of versions to return

        Returns:
            List of PlanVersion objects
        """
        with self.lock:
            cursor = self.conn.execute(
                """
                SELECT version_id, lamport, merkle_root, timestamp_ns, metadata_json
                FROM plan_versions
                ORDER BY lamport DESC
                LIMIT ?
            """,
                (limit,),
            )

            versions = []
            for row in cursor:
                metadata = json.loads(row[4]) if row[4] else {}
                versions.append(
                    PlanVersion(
                        version_id=row[0],
                        lamport=row[1],
                        merkle_root=row[2],
                        timestamp_ns=row[3],
                        metadata=metadata,
                    )
                )

            return versions
