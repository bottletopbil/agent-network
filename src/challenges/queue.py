"""
Challenge Queue: Priority queue for challenge verification.

Higher bonds = higher priority for faster verification.
"""

import time
import sqlite3
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class QueuedChallenge:
    """A challenge in the verification queue"""

    challenge_id: str
    task_id: str
    commit_id: str
    challenger_id: str
    proof_data: Dict[str, Any]
    bond_amount: int
    queued_at_ns: int
    priority_score: float
    status: str  # 'queued', 'verifying', 'verified', 'failed'


class ChallengeQueue:
    """
    Priority queue for challenge verification.

    Prioritizes challenges by:
    1. Bond amount (higher = faster)
    2. Age (older = higher priority if equal bonds)
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.lock = threading.Lock()
        self._init_schema()

    def _init_schema(self):
        """Initialize queue database schema"""
        with self.lock:
            with self.conn:
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS challenge_queue (
                        challenge_id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        commit_id TEXT NOT NULL,
                        challenger_id TEXT NOT NULL,
                        proof_data_json TEXT NOT NULL,
                        bond_amount INTEGER NOT NULL,
                        queued_at_ns INTEGER NOT NULL,
                        priority_score REAL NOT NULL,
                        status TEXT NOT NULL,
                        verified_at_ns INTEGER,
                        verification_result_json TEXT
                    )
                """
                )
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_queue_priority ON challenge_queue(priority_score DESC, queued_at_ns ASC)"
                )
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_queue_status ON challenge_queue(status)"
                )

    def add_challenge(
        self,
        challenge_id: str,
        task_id: str,
        commit_id: str,
        challenger_id: str,
        proof_data: Dict[str, Any],
        bond_amount: int,
    ) -> QueuedChallenge:
        """
        Add a challenge to the verification queue.

        Args:
            challenge_id: Unique challenge identifier
            task_id: Task being challenged
            commit_id: Commit being challenged
            challenger_id: Who submitted the challenge
            proof_data: Proof evidence data
            bond_amount: Bond posted

        Returns:
            QueuedChallenge object
        """
        queued_at_ns = time.time_ns()
        priority_score = self._calculate_priority(bond_amount, queued_at_ns)

        import json

        proof_json = json.dumps(proof_data)

        with self.lock:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO challenge_queue
                    (challenge_id, task_id, commit_id, challenger_id, proof_data_json, 
                     bond_amount, queued_at_ns, priority_score, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued')
                """,
                    (
                        challenge_id,
                        task_id,
                        commit_id,
                        challenger_id,
                        proof_json,
                        bond_amount,
                        queued_at_ns,
                        priority_score,
                    ),
                )

        print(
            f"[QUEUE] Added challenge {challenge_id}, bond={bond_amount}, priority={priority_score:.2f}"
        )

        return QueuedChallenge(
            challenge_id=challenge_id,
            task_id=task_id,
            commit_id=commit_id,
            challenger_id=challenger_id,
            proof_data=proof_data,
            bond_amount=bond_amount,
            queued_at_ns=queued_at_ns,
            priority_score=priority_score,
            status="queued",
        )

    def get_next_challenge(self) -> Optional[QueuedChallenge]:
        """
        Get the next challenge for verification (highest priority).

        Returns:
            QueuedChallenge or None if queue is empty
        """
        import json

        with self.lock:
            cursor = self.conn.execute(
                """
                SELECT challenge_id, task_id, commit_id, challenger_id, proof_data_json,
                       bond_amount, queued_at_ns, priority_score, status
                FROM challenge_queue
                WHERE status = 'queued'
                ORDER BY priority_score DESC, queued_at_ns ASC
                LIMIT 1
            """
            )

            row = cursor.fetchone()
            if not row:
                return None

            return QueuedChallenge(
                challenge_id=row[0],
                task_id=row[1],
                commit_id=row[2],
                challenger_id=row[3],
                proof_data=json.loads(row[4]),
                bond_amount=row[5],
                queued_at_ns=row[6],
                priority_score=row[7],
                status=row[8],
            )

    def mark_verifying(self, challenge_id: str) -> bool:
        """Mark challenge as currently being verified"""
        with self.lock:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    UPDATE challenge_queue
                    SET status = 'verifying'
                    WHERE challenge_id = ? AND status = 'queued'
                """,
                    (challenge_id,),
                )

                return cursor.rowcount > 0

    def mark_verified(self, challenge_id: str, result: Dict[str, Any]) -> bool:
        """
        Mark challenge as verified with result.

        Args:
            challenge_id: Challenge identifier
            result: Verification result data

        Returns:
            True if marked successfully
        """
        import json

        result_json = json.dumps(result)
        verified_at_ns = time.time_ns()

        with self.lock:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    UPDATE challenge_queue
                    SET status = 'verified',
                        verified_at_ns = ?,
                        verification_result_json = ?
                    WHERE challenge_id = ?
                """,
                    (verified_at_ns, result_json, challenge_id),
                )

                success = cursor.rowcount > 0

                if success:
                    print(f"[QUEUE] Marked challenge {challenge_id} as verified")

                return success

    def mark_failed(self, challenge_id: str, error: str) -> bool:
        """Mark challenge verification as failed"""
        import json

        result_json = json.dumps({"error": error})
        verified_at_ns = time.time_ns()

        with self.lock:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    UPDATE challenge_queue
                    SET status = 'failed',
                        verified_at_ns = ?,
                        verification_result_json = ?
                    WHERE challenge_id = ?
                """,
                    (verified_at_ns, result_json, challenge_id),
                )

                return cursor.rowcount > 0

    def prioritize_by_bond(self) -> List[QueuedChallenge]:
        """
        Get all queued challenges sorted by bond amount (highest first).

        Returns:
            List of QueuedChallenge objects
        """
        import json

        with self.lock:
            cursor = self.conn.execute(
                """
                SELECT challenge_id, task_id, commit_id, challenger_id, proof_data_json,
                       bond_amount, queued_at_ns, priority_score, status
                FROM challenge_queue
                WHERE status = 'queued'
                ORDER BY bond_amount DESC, queued_at_ns ASC
            """
            )

            challenges = []
            for row in cursor:
                challenges.append(
                    QueuedChallenge(
                        challenge_id=row[0],
                        task_id=row[1],
                        commit_id=row[2],
                        challenger_id=row[3],
                        proof_data=json.loads(row[4]),
                        bond_amount=row[5],
                        queued_at_ns=row[6],
                        priority_score=row[7],
                        status=row[8],
                    )
                )

            return challenges

    def get_queue_size(self, status: Optional[str] = None) -> int:
        """Get number of challenges in queue"""
        with self.lock:
            if status:
                cursor = self.conn.execute(
                    "SELECT COUNT(*) FROM challenge_queue WHERE status = ?", (status,)
                )
            else:
                cursor = self.conn.execute("SELECT COUNT(*) FROM challenge_queue")

            return cursor.fetchone()[0]

    def _calculate_priority(self, bond_amount: int, queued_at_ns: int) -> float:
        """
        Calculate priority score for a challenge.

        Higher bond = higher priority
        Older challenges get slight boost

        Formula: bond_amount + (age_in_hours * 10)
        """
        current_time_ns = time.time_ns()
        age_hours = (current_time_ns - queued_at_ns) / (3600 * 1e9)

        # Priority = bond + age bonus
        priority = bond_amount + (age_hours * 10)

        return priority
