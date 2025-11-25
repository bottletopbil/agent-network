"""
Reputation Tracker: manage verifier reputation with decay and boost/penalty.

Integrates with VerifierPool to update reputation scores based on attestations and challenges.
"""

import sqlite3
import time
from typing import List, Optional
from dataclasses import dataclass

from economics.pools import VerifierPool


@dataclass
class ReputationEvent:
    """Record of reputation change event"""
    event_id: str
    verifier_id: str
    event_type: str          # ATTESTATION, CHALLENGE_SUCCESS, CHALLENGE_FAIL
    delta: float             # Reputation change
    timestamp: int           # Nanosecond timestamp


class ReputationTracker:
    """
    Track and manage verifier reputation.
    
    - Initial reputation: 0.80 (set at registration)
    - Failed attestation: -0.3 penalty
    - Successful challenge: +0.1 boost
    - Decay: 5% per week without activity
    - Bounds: 0.0-1.0 (clamped)
    """
    
    # Reputation constants
    FAILED_ATTESTATION_PENALTY = -0.3
    SUCCESSFUL_CHALLENGE_BOOST = 0.1
    DECAY_RATE_PER_WEEK = 0.05
    
    def __init__(self, pool: VerifierPool):
        """
        Initialize reputation tracker.
        
        Args:
            pool: VerifierPool instance for updating reputation
        """
        self.pool = pool
        self.conn = pool.conn
        self.lock = pool.lock
        self._init_schema()
    
    def _init_schema(self):
        """Initialize reputation events table"""
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS reputation_events (
                    event_id TEXT PRIMARY KEY,
                    verifier_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    delta REAL NOT NULL,
                    timestamp_ns INTEGER NOT NULL
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_rep_verifier ON reputation_events(verifier_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_rep_timestamp ON reputation_events(timestamp_ns)")
    
    def record_attestation(self, verifier_id: str, task_id: str, verdict: bool) -> None:
        """
        Record an attestation result.
        
        Args:
            verifier_id: Verifier who made attestation
            task_id: Task that was attested
            verdict: True if attestation was correct, False if failed
        """
        if not verdict:
            # Failed attestation gets penalty
            self._apply_delta(verifier_id, "ATTESTATION_FAILED", self.FAILED_ATTESTATION_PENALTY)
        # Successful attestations don't change reputation (maintaining is expected)
    
    def record_challenge(self, verifier_id: str, upheld: bool) -> None:
        """
        Record a challenge result.
        
        Args:
            verifier_id: Verifier who issued the challenge
            upheld: True if challenge was upheld (verifier was right)
        """
        if upheld:
            # Successful challenge gets boost
            self._apply_delta(verifier_id, "CHALLENGE_SUCCESS", self.SUCCESSFUL_CHALLENGE_BOOST)
        # Failed challenges don't change reputation here (challenger gets penalized elsewhere)
    
    def _apply_delta(self, verifier_id: str, event_type: str, delta: float) -> None:
        """
        Apply reputation delta and record event.
        
        Args:
            verifier_id: Verifier to update
            event_type: Type of event
            delta: Reputation change
        """
        with self.lock:
            # Get current reputation
            verifier = self.pool.get_verifier(verifier_id)
            if not verifier:
                raise ValueError(f"Verifier not found: {verifier_id}")
            
            current_rep = verifier.metadata.reputation
            new_rep = self._clamp(current_rep + delta)
            
            with self.conn:
                # Update pool
                self.pool.update_reputation(verifier_id, new_rep)
                
                # Record event
                import uuid
                event_id = str(uuid.uuid4())
                self.conn.execute("""
                    INSERT INTO reputation_events (event_id, verifier_id, event_type, delta, timestamp_ns)
                    VALUES (?, ?, ?, ?, ?)
                """, (event_id, verifier_id, event_type, delta, time.time_ns()))
    
    def get_reputation(self, verifier_id: str) -> float:
        """
        Get current reputation with decay applied.
        
        Args:
            verifier_id: Verifier to query
        
        Returns:
            Current reputation (0.0-1.0)
        """
        verifier = self.pool.get_verifier(verifier_id)
        if not verifier:
            return 0.0
        
        # Get last activity
        cursor = self.conn.execute("""
            SELECT MAX(timestamp_ns) FROM reputation_events WHERE verifier_id = ?
        """, (verifier_id,))
        row = cursor.fetchone()
        last_activity = row[0] if row[0] else verifier.registered_at
        
        # Calculate weeks inactive
        weeks_inactive = (time.time_ns() - last_activity) / (7 * 24 * 3600 * 1e9)
        
        if weeks_inactive > 0.01:  # Only apply decay if more than ~1.5 hours inactive
            # Apply decay
            decay_factor = (1.0 - self.DECAY_RATE_PER_WEEK) ** weeks_inactive
            decayed_rep = verifier.metadata.reputation * decay_factor
            return self._clamp(decayed_rep)
        
        return verifier.metadata.reputation
    
    def apply_decay(self, verifier_id: str) -> float:
        """
        Explicitly apply decay and update stored reputation.
        
        Args:
            verifier_id: Verifier to apply decay to
        
        Returns:
            New reputation after decay
        """
        current_rep = self.get_reputation(verifier_id)
        
        # Get stored reputation
        verifier = self.pool.get_verifier(verifier_id)
        if not verifier:
            return 0.0
        
        # If different, update
        if abs(current_rep - verifier.metadata.reputation) > 0.001:
            self.pool.update_reputation(verifier_id, current_rep)
        
        return current_rep
    
    def get_reputation_history(self, verifier_id: str, limit: int = 10) -> List[ReputationEvent]:
        """
        Get reputation event history.
        
        Args:
            verifier_id: Verifier to query
            limit: Maximum events to return
        
        Returns:
            List of ReputationEvent objects (newest first)
        """
        cursor = self.conn.execute("""
            SELECT event_id, verifier_id, event_type, delta, timestamp_ns
            FROM reputation_events
            WHERE verifier_id = ?
            ORDER BY timestamp_ns DESC
            LIMIT ?
        """, (verifier_id, limit))
        
        events = []
        for row in cursor:
            events.append(ReputationEvent(
                event_id=row[0],
                verifier_id=row[1],
                event_type=row[2],
                delta=row[3],
                timestamp=row[4]
            ))
        return events
    
    def _clamp(self, value: float) -> float:
        """Clamp reputation to [0.0, 1.0]"""
        return max(0.0, min(1.0, value))
