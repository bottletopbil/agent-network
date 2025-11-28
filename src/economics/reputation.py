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
    did: str                 # DID of the verifier/agent (portable identity)
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
                    did TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    delta REAL NOT NULL,
                    timestamp_ns INTEGER NOT NULL,
                    verifier_id TEXT  -- Deprecated, kept for backward compatibility
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_rep_did ON reputation_events(did)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_rep_verifier ON reputation_events(verifier_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_rep_timestamp ON reputation_events(timestamp_ns)")
    
    def record_attestation(self, did: str, task_id: str, verdict: bool) -> None:
        """
        Record an attestation result.
        
        Args:
            did: DID of verifier who made attestation
            task_id: Task that was attested
            verdict: True if attestation was correct, False if failed
        """
        if not verdict:
            # Failed attestation gets penalty
            self._apply_delta(did, "ATTESTATION_FAILED", self.FAILED_ATTESTATION_PENALTY)
        # Successful attestations don't change reputation (maintaining is expected)
    
    def record_challenge(self, did: str, upheld: bool) -> None:
        """
        Record a challenge result.
        
        Args:
            did: DID of verifier who issued the challenge
            upheld: True if challenge was upheld (verifier was right)
        """
        if upheld:
            # Successful challenge gets boost
            self._apply_delta(did, "CHALLENGE_SUCCESS", self.SUCCESSFUL_CHALLENGE_BOOST)
        # Failed challenges don't change reputation here (challenger gets penalized elsewhere)
    
    def _apply_delta(self, did: str, event_type: str, delta: float) -> None:
        """
        Apply reputation delta and record event.
        
        Args:
            did: DID to update reputation for
            event_type: Type of event
            delta: Reputation change
        """
        with self.lock:
            # Get current reputation from pool (DIDs mapped to verifiers)
            # For now, we look up by DID as verifier_id for compatibility
            verifier = self.pool.get_verifier(did)
            if not verifier:
                raise ValueError(f"Verifier not found for DID: {did}")
            
            current_rep = verifier.metadata.reputation
            new_rep = self._clamp(current_rep + delta)
            
            with self.conn:
                # Update pool
                self.pool.update_reputation(did, new_rep)
                
                # Record event
                import uuid
                event_id = str(uuid.uuid4())
                self.conn.execute("""
                    INSERT INTO reputation_events (event_id, did, event_type, delta, timestamp_ns, verifier_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (event_id, did, event_type, delta, time.time_ns(), did))
    
    def get_reputation(self, did: str) -> float:
        """
        Get current reputation with decay applied.
        
        Args:
            did: DID to query reputation for
        
        Returns:
            Current reputation (0.0-1.0)
        """
        verifier = self.pool.get_verifier(did)
        if not verifier:
            return 0.0
        
        # Get last activity (check both did and verifier_id for compatibility)
        cursor = self.conn.execute("""
            SELECT MAX(timestamp_ns) FROM reputation_events 
            WHERE did = ? OR verifier_id = ?
        """, (did, did))
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
    
    def apply_decay(self, did: str) -> float:
        """
        Explicitly apply decay and update stored reputation.
        
        Args:
            did: DID to apply decay to
        
        Returns:
            New reputation after decay
        """
        current_rep = self.get_reputation(did)
        
        # Get stored reputation
        verifier = self.pool.get_verifier(did)
        if not verifier:
            return 0.0
        
        # If different, update
        if abs(current_rep - verifier.metadata.reputation) > 0.001:
            self.pool.update_reputation(did, current_rep)
        
        return current_rep
    
    def get_reputation_history(self, did: str, limit: int = 10) -> List[ReputationEvent]:
        """
        Get reputation event history.
        
        Args:
            did: DID to query reputation history for
            limit: Maximum events to return
        
        Returns:
            List of ReputationEvent objects (newest first)
        """
        cursor = self.conn.execute("""
            SELECT event_id, did, event_type, delta, timestamp_ns
            FROM reputation_events
            WHERE did = ? OR verifier_id = ?
            ORDER BY timestamp_ns DESC
            LIMIT ?
        """, (did, did, limit))
        
        events = []
        for row in cursor:
            events.append(ReputationEvent(
                event_id=row[0],
                did=row[1],
                event_type=row[2],
                delta=row[3],
                timestamp=row[4]
            ))
        return events
    
    def _clamp(self, value: float) -> float:
        """Clamp reputation to [0.0, 1.0]"""
        return max(0.0, min(1.0, value))
