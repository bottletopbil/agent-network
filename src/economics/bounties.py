"""
Bounty System: manage task bounties with escrow and lifecycle tracking.

Integrates with CreditLedger for escrow management.
"""

import uuid
import time
from typing import Optional, Dict
from dataclasses import dataclass
from enum import Enum

from economics.ledger import CreditLedger


class TaskClass(Enum):
    """Task classification for bounty caps"""

    SIMPLE = "SIMPLE"
    COMPLEX = "COMPLEX"
    CRITICAL = "CRITICAL"


# Bounty caps by task class
BOUNTY_CAPS = {TaskClass.SIMPLE: 10, TaskClass.COMPLEX: 100, TaskClass.CRITICAL: 1000}


@dataclass
class BountyRecord:
    """Complete bounty record"""

    bounty_id: str
    task_id: str
    amount: int
    task_class: TaskClass
    creator_id: str
    escrow_id: Optional[str]
    created_at: int
    escrowed_at: Optional[int]
    distributed_at: Optional[int]
    status: str  # CREATED, ESCROWED, DISTRIBUTED, CANCELLED


class BountyManager:
    """
    Manage bounty lifecycle from creation to distribution.

    Integrates with CreditLedger for escrow.
    Default escrow duration: 2 × T_challenge (48 hours).
    """

    def __init__(self, ledger: CreditLedger, challenge_window_hours: int = 48):
        """
        Initialize bounty manager.

        Args:
            ledger: CreditLedger instance for escrow
            challenge_window_hours: Challenge window duration (default 48)
        """
        self.ledger = ledger
        self.challenge_window_hours = challenge_window_hours
        self.escrow_duration_hours = 2 * challenge_window_hours

        self.conn = ledger.conn
        self.lock = ledger.lock
        self._init_schema()

    def _init_schema(self):
        """Initialize bounty tracking table"""
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bounties (
                    bounty_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    task_class TEXT NOT NULL,
                    creator_id TEXT NOT NULL,
                    escrow_id TEXT,
                    created_at INTEGER NOT NULL,
                    escrowed_at INTEGER,
                    distributed_at INTEGER,
                    status TEXT NOT NULL
                )
            """
            )
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_bounty_task ON bounties(task_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_bounty_status ON bounties(status)")

    def create_bounty(
        self, task_id: str, amount: int, task_class: TaskClass, creator_id: str
    ) -> str:
        """
        Create a new bounty.

        Args:
            task_id: Task identifier
            amount: Bounty amount in credits
            task_class: Task classification
            creator_id: Account creating the bounty

        Returns:
            bounty_id

        Raises:
            ValueError: If amount exceeds task_class cap
        """
        # Validate against cap
        cap = BOUNTY_CAPS[task_class]
        if amount > cap:
            raise ValueError(f"Bounty amount {amount} exceeds {task_class.value} cap of {cap}")

        if amount <= 0:
            raise ValueError(f"Bounty amount must be positive: {amount}")

        bounty_id = str(uuid.uuid4())

        with self.lock:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO bounties 
                    (bounty_id, task_id, amount, task_class, creator_id, escrow_id, 
                     created_at, escrowed_at, distributed_at, status)
                    VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, NULL, 'CREATED')
                """,
                    (
                        bounty_id,
                        task_id,
                        amount,
                        task_class.value,
                        creator_id,
                        time.time_ns(),
                    ),
                )

        return bounty_id

    def escrow_bounty(self, bounty_id: str, commit_id: str) -> str:
        """
        Escrow bounty funds in the ledger.

        Args:
            bounty_id: Bounty to escrow
            commit_id: Associated commit ID (for metadata)

        Returns:
            escrow_id from ledger

        Raises:
            ValueError: If bounty not found or already escrowed
        """
        with self.lock:
            # Get bounty
            cursor = self.conn.execute(
                """
                SELECT bounty_id, task_id, amount, task_class, creator_id, status
                FROM bounties WHERE bounty_id = ?
            """,
                (bounty_id,),
            )
            row = cursor.fetchone()

            if not row:
                raise ValueError(f"Bounty not found: {bounty_id}")

            _, task_id, amount, task_class, creator_id, status = row

            if status != "CREATED":
                raise ValueError(f"Bounty already {status}: {bounty_id}")

            # Create escrow in ledger
            escrow_id = self.ledger.escrow(creator_id, amount, bounty_id)

            with self.conn:
                # Update bounty status
                self.conn.execute(
                    """
                    UPDATE bounties 
                    SET escrow_id = ?, escrowed_at = ?, status = 'ESCROWED'
                    WHERE bounty_id = ?
                """,
                    (escrow_id, time.time_ns(), bounty_id),
                )

        return escrow_id

    def distribute_bounty(self, bounty_id: str, recipients: Dict[str, int]) -> None:
        """
        Distribute bounty to recipients.

        Args:
            bounty_id: Bounty to distribute
            recipients: Dict of {account_id: amount}

        Raises:
            ValueError: If bounty not found or not escrowed
        """
        with self.lock:
            # Get bounty
            cursor = self.conn.execute(
                """
                SELECT bounty_id, amount, escrow_id, status
                FROM bounties WHERE bounty_id = ?
            """,
                (bounty_id,),
            )
            row = cursor.fetchone()

            if not row:
                raise ValueError(f"Bounty not found: {bounty_id}")

            _, amount, escrow_id, status = row

            if status != "ESCROWED":
                raise ValueError(f"Bounty not escrowed (status={status}): {bounty_id}")

            # Validate total doesn't exceed bounty (allow for burn)
            total_distributed = sum(recipients.values())
            if total_distributed > amount:
                raise ValueError(f"Distribution total {total_distributed} exceeds bounty {amount}")

            # Release escrow to first recipient, then transfer to others
            if not recipients:
                # Cancel escrow if no recipients (shouldn't happen)
                self.ledger.cancel_escrow(escrow_id)
            else:
                # Release to first recipient
                first_recipient = list(recipients.keys())[0]
                recipients[first_recipient]

                self.ledger.release_escrow(escrow_id, first_recipient)

                # Transfer remaining amounts
                remaining_recipients = {k: v for k, v in recipients.items() if k != first_recipient}
                for recipient_id, recipient_amount in remaining_recipients.items():
                    self.ledger.transfer(first_recipient, recipient_id, recipient_amount)

                # Handle burn (amount not distributed)
                burn_amount = amount - total_distributed
                if burn_amount > 0:
                    # Burn by transferring to a null account that isn't registered
                    # Or just leave it with the first recipient (effectively a bonus)
                    # For proper burning, we'd need to reduce total supply
                    # For now, we'll create a "burn" account
                    try:
                        self.ledger.get_account("burn")
                    except:
                        self.ledger.create_account("burn", 0)

                    self.ledger.transfer(first_recipient, "burn", burn_amount)

            with self.conn:
                # Update bounty status
                self.conn.execute(
                    """
                    UPDATE bounties 
                    SET distributed_at = ?, status = 'DISTRIBUTED'
                    WHERE bounty_id = ?
                """,
                    (time.time_ns(), bounty_id),
                )

    def cancel_bounty(self, bounty_id: str) -> None:
        """
        Cancel a bounty and return escrowed funds.

        Args:
            bounty_id: Bounty to cancel

        Raises:
            ValueError: If bounty not found
        """
        with self.lock:
            # Get bounty
            cursor = self.conn.execute(
                """
                SELECT bounty_id, escrow_id, status
                FROM bounties WHERE bounty_id = ?
            """,
                (bounty_id,),
            )
            row = cursor.fetchone()

            if not row:
                raise ValueError(f"Bounty not found: {bounty_id}")

            _, escrow_id, status = row

            # Cancel escrow if it exists
            if status == "ESCROWED" and escrow_id:
                self.ledger.cancel_escrow(escrow_id)

            with self.conn:
                # Update status
                self.conn.execute(
                    """
                    UPDATE bounties 
                    SET status = 'CANCELLED'
                    WHERE bounty_id = ?
                """,
                    (bounty_id,),
                )

    def get_bounty(self, bounty_id: str) -> Optional[BountyRecord]:
        """
        Get bounty details.

        Args:
            bounty_id: Bounty to query

        Returns:
            BountyRecord or None if not found
        """
        cursor = self.conn.execute(
            """
            SELECT bounty_id, task_id, amount, task_class, creator_id, escrow_id,
                   created_at, escrowed_at, distributed_at, status
            FROM bounties WHERE bounty_id = ?
        """,
            (bounty_id,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        return BountyRecord(
            bounty_id=row[0],
            task_id=row[1],
            amount=row[2],
            task_class=TaskClass(row[3]),
            creator_id=row[4],
            escrow_id=row[5],
            created_at=row[6],
            escrowed_at=row[7],
            distributed_at=row[8],
            status=row[9],
        )

    def get_task_bounty(self, task_id: str) -> Optional[BountyRecord]:
        """
        Get bounty for a task.

        Args:
            task_id: Task to query

        Returns:
            BountyRecord or None if not found
        """
        cursor = self.conn.execute(
            """
            SELECT bounty_id, task_id, amount, task_class, creator_id, escrow_id,
                   created_at, escrowed_at, distributed_at, status
            FROM bounties WHERE task_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """,
            (task_id,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        return BountyRecord(
            bounty_id=row[0],
            task_id=row[1],
            amount=row[2],
            task_class=TaskClass(row[3]),
            creator_id=row[4],
            escrow_id=row[5],
            created_at=row[6],
            escrowed_at=row[7],
            distributed_at=row[8],
            status=row[9],
        )
