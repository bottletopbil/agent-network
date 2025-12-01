"""
Payout Distribution: calculate and execute bounty payouts with challenge-aware distribution.

Supports committee-only and challenger+committee payout scenarios.
"""

from typing import List, Optional
from dataclasses import dataclass
import time

from economics.bounties import BountyManager
from economics.relationships import RelationshipDetector


@dataclass
class PayoutShare:
    """Individual payout share"""

    recipient_id: str
    amount: int
    share_type: str  # COMMITTEE, CHALLENGER, BURN


class PayoutDistributor:
    """
    Calculate and execute bounty payouts.

    Distribution rules:
    - No challenge: 100% to committee (split equally)
    - With challenge: 50% challenger, 40% honest verifiers, 10% burn

    Payout restrictions:
    - Must wait 2 × T_challenge after task completion
    - No payout if INVALIDATE occurred
    - No payout if related parties detected
    """

    # Challenge window duration (nanoseconds): 5 minutes
    T_CHALLENGE_NS = 5 * 60 * 1_000_000_000

    def __init__(
        self,
        bounty_manager: BountyManager,
        relationship_detector: Optional[RelationshipDetector] = None,
    ):
        """
        Initialize payout distributor.

        Args:
            bounty_manager: BountyManager instance
            relationship_detector: Optional RelationshipDetector for party validation
        """
        self.bounty_manager = bounty_manager
        self.relationship_detector = relationship_detector or RelationshipDetector()
        self._invalidated_tasks = set()  # Track invalidated task IDs

    def calculate_shares(
        self, bounty_amount: int, committee: List[str], challenger: Optional[str] = None
    ) -> List[PayoutShare]:
        """
        Calculate payout shares.

        Args:
            bounty_amount: Total bounty amount
            committee: List of committee member account IDs
            challenger: Optional challenger account ID

        Returns:
            List of PayoutShare objects

        Raises:
            ValueError: If committee is empty or invalid
        """
        if not committee:
            raise ValueError("Committee cannot be empty")

        if challenger and challenger in committee:
            raise ValueError("Challenger cannot be in committee")

        shares = []

        if not challenger:
            # No challenge: 100% to committee (split equally)
            committee_share = bounty_amount // len(committee)
            remainder = bounty_amount % len(committee)

            for i, member_id in enumerate(committee):
                # Give remainder to first member
                amount = committee_share + (remainder if i == 0 else 0)
                shares.append(
                    PayoutShare(recipient_id=member_id, amount=amount, share_type="COMMITTEE")
                )
        else:
            # With challenge: 50% challenger, 40% verifiers, 10% burn
            challenger_amount = int(bounty_amount * 0.50)
            verifier_total = int(bounty_amount * 0.40)
            burn_amount = bounty_amount - challenger_amount - verifier_total

            # Challenger share
            shares.append(
                PayoutShare(
                    recipient_id=challenger,
                    amount=challenger_amount,
                    share_type="CHALLENGER",
                )
            )

            # Committee shares (split verifier_total)
            verifier_share = verifier_total // len(committee)
            verifier_remainder = verifier_total % len(committee)

            for i, member_id in enumerate(committee):
                # Give remainder to first member
                amount = verifier_share + (verifier_remainder if i == 0 else 0)
                shares.append(
                    PayoutShare(recipient_id=member_id, amount=amount, share_type="COMMITTEE")
                )

            # Burn share (no recipient)
            if burn_amount > 0:
                shares.append(
                    PayoutShare(
                        recipient_id="burn",  # Special burn account
                        amount=burn_amount,
                        share_type="BURN",
                    )
                )

        return shares

    def mark_invalidated(self, task_id: str) -> None:
        """
        Mark a task as invalidated (blocks future payouts).

        Args:
            task_id: Task ID to mark as invalidated
        """
        self._invalidated_tasks.add(task_id)

    def is_invalidated(self, task_id: str) -> bool:
        """
        Check if a task has been invalidated.

        Args:
            task_id: Task ID to check

        Returns:
            True if task is invalidated, False otherwise
        """
        return task_id in self._invalidated_tasks

    def can_payout(
        self,
        task_id: str,
        task_completion_time_ns: int,
        current_time_ns: Optional[int] = None,
    ) -> tuple[bool, str]:
        """
        Check if payout can be executed for a task.

        Args:
            task_id: Task ID
            task_completion_time_ns: Task completion timestamp (nanoseconds)
            current_time_ns: Current time (defaults to now)

        Returns:
            Tuple of (can_payout: bool, reason: str)
        """
        if current_time_ns is None:
            current_time_ns = time.time_ns()

        # Check if invalidated
        if self.is_invalidated(task_id):
            return False, "Task has been invalidated"

        # Check if challenge period has elapsed (2 × T_challenge)
        elapsed = current_time_ns - task_completion_time_ns
        required_wait = 2 * self.T_CHALLENGE_NS

        if elapsed < required_wait:
            return (
                False,
                f"Challenge period not elapsed: {elapsed} < {required_wait} ns",
            )

        return True, "OK"

    def execute_payout(
        self,
        bounty_id: str,
        task_id: str,
        committee: List[str],
        task_completion_time_ns: int,
        challenger: Optional[str] = None,
        current_time_ns: Optional[int] = None,
    ) -> None:
        """
        Execute bounty payout with challenge-period and validation checks.

        Args:
            bounty_id: Bounty to pay out
            task_id: Associated task ID
            committee: List of committee member account IDs
            task_completion_time_ns: Task completion timestamp (nanoseconds)
            challenger: Optional challenger account ID
            current_time_ns: Current time (defaults to now)

        Raises:
            ValueError: If invalid parameters, bounty not found, or payout blocked
        """
        # Check if payout can proceed
        can_pay, reason = self.can_payout(task_id, task_completion_time_ns, current_time_ns)
        if not can_pay:
            raise ValueError(f"Cannot execute payout: {reason}")

        # Validate related parties (advanced)
        if not self.validate_related_parties_advanced(committee, challenger):
            raise ValueError("Related party conflict detected")

        # Get bounty
        bounty = self.bounty_manager.get_bounty(bounty_id)
        if not bounty:
            raise ValueError(f"Bounty not found: {bounty_id}")

        # Calculate shares
        shares = self.calculate_shares(bounty.amount, committee, challenger)

        # Build recipients dict (excluding burn)
        recipients = {}
        for share in shares:
            if share.share_type != "BURN":
                # Accumulate amounts if recipient appears multiple times
                recipients[share.recipient_id] = (
                    recipients.get(share.recipient_id, 0) + share.amount
                )
            # Note: burn shares are NOT included in recipients dict
            # This causes distribute_bounty to handle the burn automatically

        # Execute distribution
        self.bounty_manager.distribute_bounty(bounty_id, recipients)

    def validate_related_parties(self, committee: List[str], challenger: Optional[str]) -> bool:
        """
        Validate no conflicts between challenger and committee (basic check).

        Args:
            committee: List of committee member account IDs
            challenger: Optional challenger account ID

        Returns:
            True if valid (no conflicts), False otherwise
        """
        if challenger is None:
            return True

        return challenger not in committee

    def validate_related_parties_advanced(
        self, committee: List[str], challenger: Optional[str]
    ) -> bool:
        """
        Validate no relationships between challenger and committee (advanced).

        Uses RelationshipDetector to check for:
        - Same organization
        - Same ASN
        - Identity linkage

        Args:
            committee: List of committee member account IDs
            challenger: Optional challenger account ID

        Returns:
            True if valid (no relationships), False otherwise
        """
        if challenger is None:
            return True

        # Basic check: challenger not in committee
        if challenger in committee:
            return False

        # Advanced checks via RelationshipDetector
        if self.relationship_detector.detect_any_relationship(committee, challenger):
            return False

        return True
