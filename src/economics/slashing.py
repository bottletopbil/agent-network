"""
Slashing System: calculate and execute penalties for violations.

Supports different violation types with configurable severity levels.
"""

import uuid
import time
from enum import Enum
from dataclasses import dataclass
from typing import List

from economics.stake import StakeManager


class ViolationType(Enum):
    """Types of slashable violations"""

    FAILED_CHALLENGE = "FAILED_CHALLENGE"  # Failed attestation challenge
    MISSED_HEARTBEAT = "MISSED_HEARTBEAT"  # Missing heartbeat signals
    POLICY_VIOLATION = "POLICY_VIOLATION"  # Policy breach


@dataclass
class SlashEvent:
    """Record of a slashing event"""

    event_id: str
    account_id: str
    reason: ViolationType
    amount: int  # Credits slashed
    evidence_hash: str  # CAS hash of evidence
    severity: int  # 0-10 scale for escalation
    timestamp: int  # Nanosecond timestamp


class SlashingRules:
    """
    Calculate and execute slashing penalties.

    Slashing percentages:
    - FAILED_CHALLENGE: 50% of stake
    - MISSED_HEARTBEAT: 1% per miss (severity 1-10)
    - POLICY_VIOLATION: 10% × (1 + severity/10) for escalation
    """

    def __init__(self, stake_manager: StakeManager):
        """
        Initialize slashing rules.

        Args:
            stake_manager: StakeManager instance to query/modify stakes
        """
        self.stake_manager = stake_manager
        self.ledger = stake_manager.ledger
        self.conn = stake_manager.conn
        self.lock = stake_manager.lock
        self._init_schema()

    def _init_schema(self):
        """Initialize slash events table"""
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS slash_events (
                    event_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    evidence_hash TEXT NOT NULL,
                    severity INTEGER NOT NULL,
                    timestamp_ns INTEGER NOT NULL
                )
            """
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_slash_account ON slash_events(account_id)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_slash_timestamp ON slash_events(timestamp_ns)"
            )

    def calculate_slash_amount(
        self, account_id: str, violation_type: ViolationType, severity: int = 5
    ) -> int:
        """
        Calculate slash amount based on violation type and severity.

        Args:
            account_id: Account to slash
            violation_type: Type of violation
            severity: Severity level (0-10, default 5)

        Returns:
            Amount to slash (in credits)
        """
        if severity < 0 or severity > 10:
            raise ValueError(f"Severity must be 0-10, got {severity}")

        staked = self.stake_manager.get_staked_amount(account_id)

        if violation_type == ViolationType.FAILED_CHALLENGE:
            # 50% of stake
            return int(staked * 0.5)

        elif violation_type == ViolationType.MISSED_HEARTBEAT:
            # 1% per severity level (max 10%)
            percentage = min(severity, 10) * 0.01
            return int(staked * percentage)

        elif violation_type == ViolationType.POLICY_VIOLATION:
            # 10% base, escalating with severity: 10% × (1 + severity/10)
            multiplier = 1.0 + (severity / 10.0)
            percentage = 0.10 * multiplier
            return int(staked * percentage)

        else:
            raise ValueError(f"Unknown violation type: {violation_type}")

    def execute_slash(self, event: SlashEvent) -> None:
        """
        Execute a slash event (reduce staked amount).

        Credits are burned (not transferred), directly reducing locked amount.

        Args:
            event: SlashEvent with details

        Raises:
            InsufficientStakeError: If account has less stake than slash amount
        """
        with self.lock:
            staked = self.stake_manager.get_staked_amount(event.account_id)

            # Allow partial slashing if stake < slash amount
            actual_slash = min(staked, event.amount)

            if actual_slash == 0:
                # No stake to slash, still record the event
                pass

            with self.conn:
                if actual_slash > 0:
                    # Reduce locked amount (burn credits)
                    self.conn.execute(
                        "UPDATE accounts SET locked = locked - ? WHERE account_id = ?",
                        (actual_slash, event.account_id),
                    )

                    # Record in operations audit trail
                    self.conn.execute(
                        """
                        INSERT INTO operations (op_id, account_id, op_type, amount, timestamp_ns, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        (
                            str(uuid.uuid4()),
                            event.account_id,
                            "SLASH",
                            actual_slash,
                            event.timestamp,
                            f'{{"event_id": "{event.event_id}", "reason": "{event.reason.value}", "severity": {event.severity}, "evidence_hash": "{event.evidence_hash}"}}',
                        ),
                    )

                # Store slash event
                self.conn.execute(
                    """
                    INSERT INTO slash_events (event_id, account_id, reason, amount, evidence_hash, severity, timestamp_ns)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        event.event_id,
                        event.account_id,
                        event.reason.value,
                        actual_slash,  # Store actual amount slashed
                        event.evidence_hash,
                        event.severity,
                        event.timestamp,
                    ),
                )

    def get_slash_history(self, account_id: str, limit: int = 10) -> List[SlashEvent]:
        """
        Get slash history for an account.

        Args:
            account_id: Account to query
            limit: Maximum number of events to return

        Returns:
            List of SlashEvent objects, newest first
        """
        cursor = self.conn.execute(
            """
            SELECT event_id, account_id, reason, amount, evidence_hash, severity, timestamp_ns
            FROM slash_events
            WHERE account_id = ?
            ORDER BY timestamp_ns DESC
            LIMIT ?
        """,
            (account_id, limit),
        )

        events = []
        for row in cursor:
            events.append(
                SlashEvent(
                    event_id=row[0],
                    account_id=row[1],
                    reason=ViolationType(row[2]),
                    amount=row[3],
                    evidence_hash=row[4],
                    severity=row[5],
                    timestamp=row[6],
                )
            )
        return events

    def slash_verifiers(
        self,
        verifiers: List[str],
        challenge_evidence: str,
        challenger: str,
        honest_verifiers: List[str] = None,
        timestamp_ns: int = None,
        attestation_log: List[dict] = None,
    ) -> dict:
        """
        Slash multiple verifiers and distribute slashed amounts.

        Distribution:
        - 50% to challenger
        - 40% to honest verifiers (split equally)
        - 10% burned

        Args:
            verifiers: List of verifier account IDs to slash
            challenge_evidence: CAS hash of challenge evidence
            challenger: Account ID of challenger
            honest_verifiers: Optional list of claimed honest verifier account IDs
            timestamp_ns: Optional timestamp (defaults to current time)
            attestation_log: Optional list of ATTEST records to verify honest_verifiers

        Returns:
            dict with:
                - total_slashed: Total amount slashed
                - challenger_payout: Amount sent to challenger
                - honest_payout: Total amount sent to honest verifiers
                - burned: Amount burned
                - events: List of SlashEvent objects
                - honest_rewards: Dict mapping verifier_id to reward amount
        """
        if timestamp_ns is None:
            timestamp_ns = time.time_ns()

        if not verifiers:
            return {
                "total_slashed": 0,
                "challenger_payout": 0,
                "honest_payout": 0,
                "burned": 0,
                "events": [],
                "honest_rewards": {},
            }

        honest_verifiers = honest_verifiers or []
        attestation_log = attestation_log or []

        # Verify honest_verifiers actually attested
        if honest_verifiers and attestation_log:
            # Extract set of verifiers who actually attested
            actual_attestors = {
                record["verifier_id"]
                for record in attestation_log
                if "verifier_id" in record
            }

            # Filter honest_verifiers to only include verified attestors
            verified_honest = [v for v in honest_verifiers if v in actual_attestors]

            # Log warning if claimed honest contains non-attestors
            non_attestors = set(honest_verifiers) - actual_attestors
            if non_attestors:
                logger.warning(
                    f"Honest verifier list contains {len(non_attestors)} non-attestors "
                    f"(free-riders): {non_attestors}. These will not receive rewards."
                )

            # Use only verified honest verifiers
            honest_verifiers = verified_honest
        elif honest_verifiers and not attestation_log:
            # No attestation log provided - log warning but allow for backward compatibility
            logger.warning(
                f"No attestation log provided for {len(honest_verifiers)} claimed honest verifiers. "
                "Cannot verify attestations - they will receive rewards without verification."
            )

        # Calculate slashes (50% of each verifier's stake)
        events = []
        total_slashed = 0

        for verifier_id in verifiers:
            slash_amount = self.calculate_slash_amount(
                verifier_id,
                ViolationType.FAILED_CHALLENGE,
                severity=10,  # Max severity for failed challenge
            )

            event = SlashEvent(
                event_id=str(uuid.uuid4()),
                account_id=verifier_id,
                reason=ViolationType.FAILED_CHALLENGE,
                amount=slash_amount,
                evidence_hash=challenge_evidence,
                severity=10,
                timestamp=timestamp_ns,
            )

            self.execute_slash(event)
            events.append(event)
            total_slashed += slash_amount

        # Distribute slashed amounts using INTEGER arithmetic to avoid precision loss
        # 50% to challenger, 40% to honest verifiers, 10% + remainder burned
        challenger_payout = (total_slashed * 50) // 100
        honest_total = (total_slashed * 40) // 100
        burned = (
            total_slashed - challenger_payout - honest_total
        )  # Remainder goes to burned

        # Verify exact distribution (no precision loss)
        assert (
            challenger_payout + honest_total + burned == total_slashed
        ), "Distribution must sum to total_slashed exactly"

        with self.lock:
            with self.conn:
                # Pay challenger
                if challenger_payout > 0:
                    self.conn.execute(
                        "UPDATE accounts SET balance = balance + ? WHERE account_id = ?",
                        (challenger_payout, challenger),
                    )
                    self.conn.execute(
                        """
                        INSERT INTO operations (op_id, account_id, op_type, amount, timestamp_ns, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """,
                        (
                            str(uuid.uuid4()),
                            challenger,
                            "SLASH_REWARD",
                            challenger_payout,
                            timestamp_ns,
                            f'{{"reason": "challenge_upheld", "evidence_hash": "{challenge_evidence}"}}',
                        ),
                    )

                # Pay honest verifiers
                if honest_total > 0 and honest_verifiers:
                    honest_share = honest_total // len(honest_verifiers)
                    honest_remainder = honest_total % len(honest_verifiers)

                    for i, verifier_id in enumerate(honest_verifiers):
                        # Give remainder to first verifier
                        payout = honest_share + (honest_remainder if i == 0 else 0)

                        self.conn.execute(
                            "UPDATE accounts SET balance = balance + ? WHERE account_id = ?",
                            (payout, verifier_id),
                        )
                        self.conn.execute(
                            """
                            INSERT INTO operations (op_id, account_id, op_type, amount, timestamp_ns, metadata_json)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """,
                            (
                                str(uuid.uuid4()),
                                verifier_id,
                                "SLASH_REWARD",
                                payout,
                                timestamp_ns,
                                f'{{"reason": "honest_verifier", "evidence_hash": "{challenge_evidence}"}}',
                            ),
                        )

                # Burn amount (no action needed, just not paid out)

        return {
            "total_slashed": total_slashed,
            "challenger_payout": challenger_payout,
            "honest_payout": honest_total,
            "burned": burned,
            "events": events,
        }
