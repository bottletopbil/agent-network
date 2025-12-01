"""
Verifier Pool: registration, deregistration, and pool management.

Integrates with StakeManager to enforce stake requirements and filter active verifiers.
"""

import sqlite3
import json
import time
from typing import List, Optional
from dataclasses import dataclass, asdict

from economics.stake import StakeManager


@dataclass
class VerifierMetadata:
    """Metadata for diversity-aware committee selection"""

    org_id: str  # Organization identifier
    asn: str  # Autonomous System Number
    region: str  # Geographic region
    reputation: float  # 0.0-1.0 reputation score
    tee_verified: bool = False  # TEE attestation verified


@dataclass
class VerifierRecord:
    """Complete verifier record"""

    verifier_id: str
    stake: int  # Stake at registration (for reference)
    capabilities: List[str]  # e.g., ["code_review", "testing"]
    metadata: VerifierMetadata
    registered_at: int  # Nanosecond timestamp
    active: bool


class VerifierPool:
    """
    Manage verifier pool registration with stake requirements.

    Integrates with StakeManager for live stake queries.
    """

    def __init__(self, stake_manager: StakeManager):
        """
        Initialize verifier pool.

        Args:
            stake_manager: StakeManager instance for stake validation
        """
        self.stake_manager = stake_manager
        self.ledger = stake_manager.ledger
        self.conn = stake_manager.conn
        self.lock = stake_manager.lock
        self._init_schema()

    def _init_schema(self):
        """Initialize verifier pool table"""
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS verifiers (
                    verifier_id TEXT PRIMARY KEY,
                    stake INTEGER NOT NULL,
                    capabilities_json TEXT NOT NULL,
                    org_id TEXT NOT NULL,
                    asn TEXT NOT NULL,
                    region TEXT NOT NULL,
                    reputation REAL NOT NULL,
                    registered_at INTEGER NOT NULL,
                    active BOOLEAN NOT NULL DEFAULT 1,
                    tee_verified BOOLEAN NOT NULL DEFAULT 0
                )
            """
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_verifiers_active ON verifiers(active)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_verifiers_org ON verifiers(org_id)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_verifiers_region ON verifiers(region)"
            )

    def register(
        self,
        verifier_id: str,
        stake: int,
        capabilities: List[str],
        metadata: VerifierMetadata,
    ) -> None:
        """
        Register a verifier in the pool.

        Args:
            verifier_id: Account ID of verifier
            stake: Current staked amount (for reference)
            capabilities: List of capability tags
            metadata: Verifier metadata for diversity

        Raises:
            ValueError: If verifier has insufficient stake
        """
        if metadata.reputation < 0.0 or metadata.reputation > 1.0:
            raise ValueError(f"Reputation must be 0.0-1.0, got {metadata.reputation}")

        # Validate verifier has sufficient stake
        current_stake = self.stake_manager.get_staked_amount(verifier_id)
        if current_stake < stake:
            raise ValueError(
                f"Verifier stake mismatch: claimed {stake}, actual {current_stake}"
            )

        with self.lock:
            with self.conn:
                # Insert or replace (allows re-registration)
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO verifiers 
                    (verifier_id, stake, capabilities_json, org_id, asn, region, reputation, registered_at, active, tee_verified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                    (
                        verifier_id,
                        stake,
                        json.dumps(capabilities),
                        metadata.org_id,
                        metadata.asn,
                        metadata.region,
                        metadata.reputation,
                        time.time_ns(),
                        metadata.tee_verified,
                    ),
                )

    def deregister(self, verifier_id: str) -> None:
        """
        Deregister a verifier from the pool (soft delete).

        Args:
            verifier_id: Account ID of verifier

        Raises:
            ValueError: If verifier not found
        """
        with self.lock:
            cursor = self.conn.execute(
                "SELECT verifier_id FROM verifiers WHERE verifier_id = ?",
                (verifier_id,),
            )
            if not cursor.fetchone():
                raise ValueError(f"Verifier not found: {verifier_id}")

            with self.conn:
                self.conn.execute(
                    "UPDATE verifiers SET active = 0 WHERE verifier_id = ?",
                    (verifier_id,),
                )

    def get_pool_members(self, active_only: bool = True) -> List[VerifierRecord]:
        """
        Get all pool members.

        Args:
            active_only: If True, only return active verifiers

        Returns:
            List of VerifierRecord objects
        """
        if active_only:
            cursor = self.conn.execute(
                """
                SELECT verifier_id, stake, capabilities_json, org_id, asn, region, reputation, registered_at, active, tee_verified
                FROM verifiers
                WHERE active = 1
                ORDER BY registered_at DESC
            """
            )
        else:
            cursor = self.conn.execute(
                """
                SELECT verifier_id, stake, capabilities_json, org_id, asn, region, reputation, registered_at, active, tee_verified
                FROM verifiers
                ORDER BY registered_at DESC
            """
            )

        records = []
        for row in cursor:
            records.append(
                VerifierRecord(
                    verifier_id=row[0],
                    stake=row[1],
                    capabilities=json.loads(row[2]),
                    metadata=VerifierMetadata(
                        org_id=row[3],
                        asn=row[4],
                        region=row[5],
                        reputation=row[6],
                        tee_verified=bool(row[9]),
                    ),
                    registered_at=row[7],
                    active=bool(row[8]),
                )
            )
        return records

    def get_active_verifiers(self, min_stake: int = 0) -> List[VerifierRecord]:
        """
        Get active verifiers with sufficient stake.

        Queries live stake from StakeManager and filters.

        Args:
            min_stake: Minimum required stake

        Returns:
            List of VerifierRecord objects with stake >= min_stake
        """
        # Get all active verifiers
        all_active = self.get_pool_members(active_only=True)

        # Filter by current stake from StakeManager
        result = []
        for verifier in all_active:
            current_stake = self.stake_manager.get_staked_amount(verifier.verifier_id)
            if current_stake >= min_stake:
                # Update stake to current value
                verifier.stake = current_stake
                result.append(verifier)

        return result

    def get_verifier(self, verifier_id: str) -> Optional[VerifierRecord]:
        """
        Get specific verifier details.

        Args:
            verifier_id: Account ID of verifier

        Returns:
            VerifierRecord or None if not found
        """
        cursor = self.conn.execute(
            """
            SELECT verifier_id, stake, capabilities_json, org_id, asn, region, reputation, registered_at, active, tee_verified
            FROM verifiers
            WHERE verifier_id = ?
        """,
            (verifier_id,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        return VerifierRecord(
            verifier_id=row[0],
            stake=row[1],
            capabilities=json.loads(row[2]),
            metadata=VerifierMetadata(
                org_id=row[3],
                asn=row[4],
                region=row[5],
                reputation=row[6],
                tee_verified=bool(row[9]),
            ),
            registered_at=row[7],
            active=bool(row[8]),
        )

    def update_capabilities(self, verifier_id: str, capabilities: List[str]) -> None:
        """
        Update verifier capabilities.

        Args:
            verifier_id: Account ID of verifier
            capabilities: New capability list

        Raises:
            ValueError: If verifier not found
        """
        with self.lock:
            cursor = self.conn.execute(
                "SELECT verifier_id FROM verifiers WHERE verifier_id = ?",
                (verifier_id,),
            )
            if not cursor.fetchone():
                raise ValueError(f"Verifier not found: {verifier_id}")

            with self.conn:
                self.conn.execute(
                    "UPDATE verifiers SET capabilities_json = ? WHERE verifier_id = ?",
                    (json.dumps(capabilities), verifier_id),
                )

    def update_reputation(self, verifier_id: str, reputation: float) -> None:
        """
        Update verifier reputation score.

        Args:
            verifier_id: Account ID of verifier
            reputation: New reputation score (0.0-1.0)

        Raises:
            ValueError: If verifier not found or invalid reputation
        """
        if reputation < 0.0 or reputation > 1.0:
            raise ValueError(f"Reputation must be 0.0-1.0, got {reputation}")

        with self.lock:
            cursor = self.conn.execute(
                "SELECT verifier_id FROM verifiers WHERE verifier_id = ?",
                (verifier_id,),
            )
            if not cursor.fetchone():
                raise ValueError(f"Verifier not found: {verifier_id}")

            with self.conn:
                self.conn.execute(
                    "UPDATE verifiers SET reputation = ? WHERE verifier_id = ?",
                    (reputation, verifier_id),
                )
