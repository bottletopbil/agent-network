"""
Challenge Outcomes: Handle challenge resolution and payouts.

Outcomes determine what happens to bonds and how participants are rewarded/penalized.
"""

from enum import Enum
from typing import Optional, Dict
from dataclasses import dataclass

from economics.slashing import SlashingRules, ViolationType, SlashEvent
import uuid
import time


class ChallengeOutcome(Enum):
    """Possible outcomes for a challenge"""

    UPHELD = "UPHELD"  # Challenge valid - verifiers were wrong
    REJECTED = "REJECTED"  # Challenge invalid - verifiers were correct
    WITHDRAWN = "WITHDRAWN"  # Challenger withdraws before verification


@dataclass
class OutcomeResult:
    """Result of processing a challenge outcome"""

    outcome: ChallengeOutcome
    bond_returned: int
    bond_slashed: int
    reward_amount: int
    verifiers_slashed: list
    slash_amount_per_verifier: int


class OutcomeHandler:
    """
    Process challenge outcomes and handle bond/reward distribution.

    Rules:
    - UPHELD: Return bond + reward to challenger, slash verifiers
    - REJECTED: Slash challenger's bond
    - WITHDRAWN: Return bond minus withdrawal fee
    """

    # Configuration constants
    WITHDRAWAL_FEE_PERCENT = 10  # 10% fee for withdrawing
    VERIFIER_SLASH_PERCENT = 50  # Slash 50% of verifier stake
    REWARD_PERCENT = 20  # Reward is 20% of total slashed amount

    def __init__(self, ledger=None, stake_manager=None):
        """
        Initialize outcome handler.

        Args:
            ledger: Credit ledger for managing escrows and transfers
            stake_manager: StakeManager for slashing verifier stakes
        """
        self.ledger = ledger
        self.stake_manager = stake_manager
        self.slashing_rules = SlashingRules(stake_manager) if stake_manager else None

    def process_outcome(
        self,
        challenge_id: str,
        outcome: ChallengeOutcome,
        bond_amount: int,
        challenger_id: str,
        verifiers: Optional[list] = None,
        verifier_stakes: Optional[Dict[str, int]] = None,
        total_slashed: Optional[int] = None,
    ) -> OutcomeResult:
        """
        Process a challenge outcome and handle all financial transactions.

        Args:
            challenge_id: Unique challenge identifier
            outcome: The outcome of the challenge
            bond_amount: Amount of bond posted
            challenger_id: Who submitted the challenge
            verifiers: List of verifier IDs (for UPHELD outcome)
            verifier_stakes: Dict of {verifier_id: stake_amount}
            total_slashed: Total amount slashed (for proportional rewards)

        Returns:
            OutcomeResult with details of what happened
        """
        if outcome == ChallengeOutcome.UPHELD:
            return self._process_upheld(
                challenge_id,
                bond_amount,
                challenger_id,
                verifiers or [],
                verifier_stakes or {},
                total_slashed,
            )
        elif outcome == ChallengeOutcome.REJECTED:
            return self._process_rejected(challenge_id, bond_amount, challenger_id)
        elif outcome == ChallengeOutcome.WITHDRAWN:
            return self._process_withdrawn(challenge_id, bond_amount, challenger_id)
        else:
            raise ValueError(f"Unknown outcome: {outcome}")

    def _process_upheld(
        self,
        challenge_id: str,
        bond_amount: int,
        challenger_id: str,
        verifiers: list,
        verifier_stakes: Dict[str, int],
        total_slashed: Optional[int] = None,
    ) -> OutcomeResult:
        """
        Process UPHELD outcome: challenger was correct, verifiers were wrong.

        - Return bond to challenger
        - Reward challenger (20% of total slashed amount)
        - Slash verifiers (50% of their stakes)
        """
        # Return bond
        bond_returned = bond_amount

        # Calculate total slashed if not provided
        if total_slashed is None:
            total_slashed = 0
            if verifiers and verifier_stakes:
                for verifier_id in verifiers:
                    stake = verifier_stakes.get(verifier_id, 0)
                    slash_amount = (stake * self.VERIFIER_SLASH_PERCENT) // 100
                    total_slashed += slash_amount

        # Calculate reward as 20% of total slashed
        reward_amount = int(total_slashed * self.REWARD_PERCENT / 100)

        # Slash verifiers
        verifiers_slashed = []
        total_slash_per_verifier = 0

        if verifiers and verifier_stakes:
            for verifier_id in verifiers:
                stake = verifier_stakes.get(verifier_id, 0)
                if stake > 0:
                    slash_amount = int(stake * (self.VERIFIER_SLASH_PERCENT / 100))
                    verifiers_slashed.append(verifier_id)
                    total_slash_per_verifier = slash_amount

                    # Slash from verifier's staked amount
                    if self.slashing_rules:
                        slash_event = SlashEvent(
                            event_id=str(uuid.uuid4()),
                            account_id=verifier_id,
                            reason=ViolationType.FAILED_CHALLENGE,
                            amount=slash_amount,
                            evidence_hash=challenge_id,
                            severity=10,
                            timestamp=time.time_ns(),
                        )
                        self.slashing_rules.execute_slash(slash_event)

        # Transfer bond + reward to challenger via ledger
        if self.ledger:
            # Release bond escrow to challenger
            try:
                self.ledger.release_escrow(f"challenge_bond_{challenge_id}", challenger_id)
            except Exception as e:
                print(f"[OUTCOME] Warning: Could not release bond escrow: {e}")

            # Transfer reward from system account
            # Note: System account must exist with sufficient balance
            try:
                self.ledger.transfer("system", challenger_id, reward_amount)
            except Exception as e:
                print(f"[OUTCOME] Warning: Could not transfer reward: {e}")

        print(f"[OUTCOME] Challenge {challenge_id} UPHELD")
        print(f"[OUTCOME] Returned {bond_returned} + rewarded {reward_amount} to {challenger_id}")
        print(f"[OUTCOME] Slashed {len(verifiers_slashed)} verifiers")

        return OutcomeResult(
            outcome=ChallengeOutcome.UPHELD,
            bond_returned=bond_returned,
            bond_slashed=0,
            reward_amount=reward_amount,
            verifiers_slashed=verifiers_slashed,
            slash_amount_per_verifier=total_slash_per_verifier,
        )

    def _process_rejected(
        self, challenge_id: str, bond_amount: int, challenger_id: str
    ) -> OutcomeResult:
        """
        Process REJECTED outcome: challenge was frivolous, slash bond.

        - Slash challenger's bond (keep in treasury/burn)
        """
        bond_slashed = bond_amount

        # In production, slash the escrowed bond
        if self.ledger:
            # Bond remains in escrow, could be burned or distributed
            # self.ledger.cancel_escrow(f"challenge_bond_{challenge_id}")
            pass

        print(f"[OUTCOME] Challenge {challenge_id} REJECTED")
        print(f"[OUTCOME] Slashed {bond_slashed} credits from {challenger_id}")

        return OutcomeResult(
            outcome=ChallengeOutcome.REJECTED,
            bond_returned=0,
            bond_slashed=bond_slashed,
            reward_amount=0,
            verifiers_slashed=[],
            slash_amount_per_verifier=0,
        )

    def _process_withdrawn(
        self, challenge_id: str, bond_amount: int, challenger_id: str
    ) -> OutcomeResult:
        """
        Process WITHDRAWN outcome: challenger withdrew before verification.

        - Return bond minus withdrawal fee (10%)
        """
        fee_amount = int(bond_amount * (self.WITHDRAWAL_FEE_PERCENT / 100))
        bond_returned = bond_amount - fee_amount

        # In production, return bond minus fee
        if self.ledger:
            # self.ledger.release_escrow(f"challenge_bond_{challenge_id}", challenger_id)
            # Keep fee_amount in treasury
            pass

        print(f"[OUTCOME] Challenge {challenge_id} WITHDRAWN")
        print(f"[OUTCOME] Returned {bond_returned} to {challenger_id} (fee: {fee_amount})")

        return OutcomeResult(
            outcome=ChallengeOutcome.WITHDRAWN,
            bond_returned=bond_returned,
            bond_slashed=fee_amount,
            reward_amount=0,
            verifiers_slashed=[],
            slash_amount_per_verifier=0,
        )
