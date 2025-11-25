"""
Lease Manager: Centralized lease lifecycle management with persistence.
"""

import sqlite3
import time
import threading
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class LeaseRecord:
    """Single lease record"""
    lease_id: str
    task_id: str
    worker_id: str
    ttl: int  # Time-to-live in seconds
    created_at: int  # Nanosecond timestamp
    last_heartbeat: int  # Nanosecond timestamp
    heartbeat_interval: int  # Expected interval in seconds


class LeaseManager:
    """
    Manage lease lifecycle with SQLite persistence.
    
    Provides:
    - Lease creation and renewal
    - Heartbeat tracking
    - Expiry detection
    - Worker lease queries
    """
    
    def __init__(self, db_path: Path):
        """
        Initialize lease manager.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.lock = threading.Lock()
        self._init_schema()
    
    def _init_schema(self):
        """Initialize leases table"""
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS leases (
                    lease_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    ttl INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    last_heartbeat INTEGER NOT NULL,
                    heartbeat_interval INTEGER NOT NULL
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_leases_worker ON leases(worker_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_leases_task ON leases(task_id)")
    
    def create_lease(
        self,
        task_id: str,
        worker_id: str,
        ttl: int,
        heartbeat_interval: int
    ) -> str:
        """
        Create a new lease.
        
        Args:
            task_id: Task being leased
            worker_id: Worker claiming the lease
            ttl: Time-to-live in seconds
            heartbeat_interval: Expected heartbeat interval in seconds
        
        Returns:
            lease_id: Generated lease identifier
        """
        import uuid
        
        lease_id = str(uuid.uuid4())
        current_time = time.time_ns()
        
        with self.lock:
            with self.conn:
                self.conn.execute("""
                    INSERT INTO leases 
                    (lease_id, task_id, worker_id, ttl, created_at, last_heartbeat, heartbeat_interval)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (lease_id, task_id, worker_id, ttl, current_time, current_time, heartbeat_interval))
        
        return lease_id
    
    def renew_lease(self, lease_id: str) -> bool:
        """
        Renew a lease by resetting its created_at timestamp.
        
        Args:
            lease_id: Lease to renew
        
        Returns:
            True if renewed, False if lease not found
        """
        current_time = time.time_ns()
        
        with self.lock:
            cursor = self.conn.execute(
                "SELECT lease_id FROM leases WHERE lease_id = ?",
                (lease_id,)
            )
            if not cursor.fetchone():
                return False
            
            with self.conn:
                self.conn.execute("""
                    UPDATE leases 
                    SET created_at = ?, last_heartbeat = ?
                    WHERE lease_id = ?
                """, (current_time, current_time, lease_id))
        
        return True
    
    def heartbeat(self, lease_id: str) -> bool:
        """
        Update lease heartbeat timestamp.
        
        Args:
            lease_id: Lease receiving heartbeat
        
        Returns:
            True if updated, False if lease not found
        """
        current_time = time.time_ns()
        
        with self.lock:
            cursor = self.conn.execute(
                "SELECT lease_id FROM leases WHERE lease_id = ?",
                (lease_id,)
            )
            if not cursor.fetchone():
                return False
            
            with self.conn:
                self.conn.execute("""
                    UPDATE leases 
                    SET last_heartbeat = ?
                    WHERE lease_id = ?
                """, (current_time, lease_id))
        
        return True
    
    def check_expiry(self) -> List[str]:
        """
        Check for expired leases.
        
        A lease is expired if: current_time > created_at + ttl
        
        Returns:
            List of expired lease_ids
        """
        current_time = time.time_ns()
        
        cursor = self.conn.execute("""
            SELECT lease_id, created_at, ttl
            FROM leases
        """)
        
        expired = []
        for row in cursor:
            lease_id = row[0]
            created_at = row[1]
            ttl_ns = row[2] * 1_000_000_000  # Convert seconds to nanoseconds
            
            if current_time > (created_at + ttl_ns):
                expired.append(lease_id)
        
        return expired
    
    def get_lease(self, lease_id: str) -> Optional[LeaseRecord]:
        """
        Get lease by ID.
        
        Args:
            lease_id: Lease identifier
        
        Returns:
            LeaseRecord or None if not found
        """
        cursor = self.conn.execute("""
            SELECT lease_id, task_id, worker_id, ttl, created_at, last_heartbeat, heartbeat_interval
            FROM leases
            WHERE lease_id = ?
        """, (lease_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        return LeaseRecord(
            lease_id=row[0],
            task_id=row[1],
            worker_id=row[2],
            ttl=row[3],
            created_at=row[4],
            last_heartbeat=row[5],
            heartbeat_interval=row[6]
        )
    
    def get_leases_for_worker(self, worker_id: str) -> List[LeaseRecord]:
        """
        Get all leases for a worker.
        
        Args:
            worker_id: Worker identifier
        
        Returns:
            List of LeaseRecords
        """
        cursor = self.conn.execute("""
            SELECT lease_id, task_id, worker_id, ttl, created_at, last_heartbeat, heartbeat_interval
            FROM leases
            WHERE worker_id = ?
            ORDER BY created_at DESC
        """, (worker_id,))
        
        leases = []
        for row in cursor:
            leases.append(LeaseRecord(
                lease_id=row[0],
                task_id=row[1],
                worker_id=row[2],
                ttl=row[3],
                created_at=row[4],
                last_heartbeat=row[5],
                heartbeat_interval=row[6]
            ))
        
        return leases
    
    def scavenge_expired(self) -> List[str]:
        """
        Check for expired leases and delete them atomically.
        
        Combines check_expiry() with deletion for daemon use.
        
        Returns:
            List of scavenged lease_ids
        """
        expired = self.check_expiry()
        
        for lease_id in expired:
            self.delete_lease(lease_id)
        
        return expired
    
    def delete_lease(self, lease_id: str) -> bool:
        """
        Delete a lease (for cleanup/testing).
        
        Args:
            lease_id: Lease to delete
        
        Returns:
            True if deleted, False if not found
        """
        with self.lock:
            cursor = self.conn.execute(
                "SELECT lease_id FROM leases WHERE lease_id = ?",
                (lease_id,)
            )
            if not cursor.fetchone():
                return False
            
            with self.conn:
                self.conn.execute("DELETE FROM leases WHERE lease_id = ?", (lease_id,))
        
        return True
