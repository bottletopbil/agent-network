"""
Escalation Handler: Manage challenge escalation when verification is disputed.

Handles:
- Disagreements between verifiers
- Complex cases requiring human review
- Governance votes for contentious challenges
"""

import uuid
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class EscalationLevel(Enum):
    """Levels of escalation"""

    NONE = "NONE"  # No escalation needed
    VERIFIER_CONSENSUS = "VERIFIER_CONSENSUS"  # More verifiers needed
    HUMAN_REVIEW = "HUMAN_REVIEW"  # Requires human judgment
    GOVERNANCE_VOTE = "GOVERNANCE_VOTE"  # Community governance required


@dataclass
class VerifierVerdict:
    """A single verifier's verdict on a challenge"""

    verifier_id: str
    is_valid: bool  # True if challenge is upheld
    confidence: float  # 0.0 - 1.0
    reasoning: Optional[str] = None


@dataclass
class EscalationCase:
    """An escalated challenge case"""

    escalation_id: str
    challenge_id: str
    level: EscalationLevel
    verdicts: List[VerifierVerdict]
    reasoning: str
    created_at_ns: int
    resolved: bool = False
    resolution: Optional[Dict[str, Any]] = None


class EscalationHandler:
    """
    Handle challenge escalation when verification is disputed.

    Escalation triggers:
    - Disagreement between verifiers (>30% dissent)
    - Low confidence scores (<70% average)
    - High-value bonds (>500 credits)
    """

    # Configuration
    DISAGREEMENT_THRESHOLD = 0.3  # 30% dissent triggers escalation
    CONFIDENCE_THRESHOLD = 0.7  # <70% avg confidence = escalation
    HIGH_VALUE_BOND_THRESHOLD = 500  # Bonds >500 get extra scrutiny

    def __init__(self):
        self.escalations: Dict[str, EscalationCase] = {}

    def check_escalation_needed(
        self, challenge_id: str, verdicts: List[VerifierVerdict], bond_amount: int
    ) -> tuple[bool, Optional[EscalationLevel], Optional[str]]:
        """
        Check if a challenge needs escalation.

        Args:
            challenge_id: Challenge being checked
            verdicts: List of verifier verdicts
            bond_amount: Bond posted for challenge

        Returns:
            (needs_escalation, level, reason)
        """
        if not verdicts:
            return False, None, None

        # Check for disagreement
        upheld_count = sum(1 for v in verdicts if v.is_valid)
        total_count = len(verdicts)
        disagreement_rate = min(upheld_count, total_count - upheld_count) / total_count

        if disagreement_rate >= self.DISAGREEMENT_THRESHOLD:
            return (
                True,
                EscalationLevel.VERIFIER_CONSENSUS,
                f"Verifier disagreement: {disagreement_rate:.1%}",
            )

        # Check confidence
        avg_confidence = sum(v.confidence for v in verdicts) / total_count
        if avg_confidence < self.CONFIDENCE_THRESHOLD:
            return (
                True,
                EscalationLevel.HUMAN_REVIEW,
                f"Low confidence: {avg_confidence:.1%}",
            )

        # Check high-value bonds
        if bond_amount >= self.HIGH_VALUE_BOND_THRESHOLD:
            return (
                True,
                EscalationLevel.GOVERNANCE_VOTE,
                f"High-value bond: {bond_amount} credits",
            )

        return False, None, None

    def escalate_if_disagree(
        self, challenge_id: str, verdicts: List[VerifierVerdict], bond_amount: int = 0
    ) -> Optional[EscalationCase]:
        """
        Escalate challenge if verifiers disagree.

        Args:
            challenge_id: Challenge to potentially escalate
            verdicts: Verifier verdicts
            bond_amount: Bond amount

        Returns:
            EscalationCase if escalated, None otherwise
        """
        needs_escalation, level, reason = self.check_escalation_needed(
            challenge_id, verdicts, bond_amount
        )

        if not needs_escalation:
            return None

        escalation_id = str(uuid.uuid4())

        import time

        escalation = EscalationCase(
            escalation_id=escalation_id,
            challenge_id=challenge_id,
            level=level,
            verdicts=verdicts,
            reasoning=reason,
            created_at_ns=time.time_ns(),
        )

        self.escalations[escalation_id] = escalation

        print(f"[ESCALATION] Challenge {challenge_id} escalated to {level.value}: {reason}")

        # Take action based on level
        if level == EscalationLevel.VERIFIER_CONSENSUS:
            self._request_more_verifiers(challenge_id)
        elif level == EscalationLevel.HUMAN_REVIEW:
            self.create_human_review_task(challenge_id)
        elif level == EscalationLevel.GOVERNANCE_VOTE:
            self.governance_vote(challenge_id)

        return escalation

    def _request_more_verifiers(self, challenge_id: str):
        """Request additional verifiers for consensus"""
        print(f"[ESCALATION] Requesting additional verifiers for challenge {challenge_id}")
        # In production, would trigger verifier selection process

    def create_human_review_task(self, challenge_id: str) -> str:
        """
        Create a human review task for a challenge.

        Args:
            challenge_id: Challenge needing human review

        Returns:
            Review task ID
        """
        review_task_id = f"human_review_{challenge_id}"

        print(
            f"[ESCALATION] Created human review task {review_task_id} for challenge {challenge_id}"
        )

        # In production, would:
        # 1. Create task in review queue
        # 2. Notify human reviewers
        # 3. Set timeout for review
        # 4. Provide all challenge context and evidence

        return review_task_id

    def governance_vote(self, challenge_id: str) -> str:
        """
        Initiate governance vote for a challenge.

        Args:
            challenge_id: Challenge requiring governance decision

        Returns:
            Vote ID
        """
        vote_id = f"gov_vote_{challenge_id}"

        print(f"[ESCALATION] Initiated governance vote {vote_id} for challenge {challenge_id}")

        # In production, would:
        # 1. Create voting proposal
        # 2. Distribute to governance participants
        # 3. Set voting period (e.g. 7 days)
        # 4. Calculate quorum requirements
        # 5. Execute outcome based on vote

        return vote_id

    def resolve_escalation(self, escalation_id: str, resolution: Dict[str, Any]) -> bool:
        """
        Resolve an escalated case.

        Args:
            escalation_id: Escalation to resolve
            resolution: Resolution data (outcome, reasoning, etc.)

        Returns:
            True if resolved successfully
        """
        escalation = self.escalations.get(escalation_id)
        if not escalation:
            return False

        escalation.resolved = True
        escalation.resolution = resolution

        print(f"[ESCALATION] Resolved escalation {escalation_id}: {resolution.get('outcome')}")

        return True

    def get_escalation(self, escalation_id: str) -> Optional[EscalationCase]:
        """Get escalation case by ID"""
        return self.escalations.get(escalation_id)

    def get_pending_escalations(
        self, level: Optional[EscalationLevel] = None
    ) -> List[EscalationCase]:
        """Get all pending (unresolved) escalations"""
        escalations = [e for e in self.escalations.values() if not e.resolved]

        if level:
            escalations = [e for e in escalations if e.level == level]

        return escalations
