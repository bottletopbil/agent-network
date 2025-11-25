"""
Challenge Outcomes: Handle challenge resolution and payouts.

Outcomes determine what happens to bonds and how participants are rewarded/penalized.
"""

from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass


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
    UPHELD_REWARD_MULTIPLIER = 2  # 2x bond as reward
    VERIFIER_SLASH_PERCENT = 50  # Slash 50% of verifier stake
    
    def __init__(self, ledger=None):
        """
        Initialize outcome handler.
        
        Args:
            ledger: Credit ledger for managing escrows and transfers
        """
        self.ledger = ledger
    
    def process_outcome(
        self,
        challenge_id: str,
        outcome: ChallengeOutcome,
        bond_amount: int,
        challenger_id: str,
        verifiers: Optional[list] = None,
        verifier_stakes: Optional[Dict[str, int]] = None
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
        
        Returns:
            OutcomeResult with details of what happened
        """
        if outcome == ChallengeOutcome.UPHELD:
            return self._process_upheld(
                challenge_id, bond_amount, challenger_id, verifiers or [], verifier_stakes or {}
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
        verifier_stakes: Dict[str, int]
    ) -> OutcomeResult:
        """
        Process UPHELD outcome: challenger was correct, verifiers were wrong.
        
        - Return bond to challenger
        - Reward challenger (2x bond amount)
        - Slash verifiers (50% of their stakes)
        """
        # Return bond
        bond_returned = bond_amount
        
        # Calculate reward (2x bond)
        reward_amount = bond_amount * self.UPHELD_REWARD_MULTIPLIER
        
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
                    
                    # In production, slash from verifier's staked amount
                    if self.ledger:
                        # self.ledger.slash_stake(ver ifier_id, slash_amount)
                        pass
        
        # In production, transfer bond + reward to challenger via ledger
        if self.ledger:
            # self.ledger.release_escrow(f"challenge_bond_{challenge_id}", challenger_id)
            # self.ledger.transfer("system", challenger_id, reward_amount)
            pass
        
        print(f"[OUTCOME] Challenge {challenge_id} UPHELD")
        print(f"[OUTCOME] Returned {bond_returned} + rewarded {reward_amount} to {challenger_id}")
        print(f"[OUTCOME] Slashed {len(verifiers_slashed)} verifiers")
        
        return OutcomeResult(
            outcome=ChallengeOutcome.UPHELD,
            bond_returned=bond_returned,
            bond_slashed=0,
            reward_amount=reward_amount,
            verifiers_slashed=verifiers_slashed,
            slash_amount_per_verifier=total_slash_per_verifier
        )
    
    def _process_rejected(
        self,
        challenge_id: str,
        bond_amount: int,
        challenger_id: str
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
            slash_amount_per_verifier=0
        )
    
    def _process_withdrawn(
        self,
        challenge_id: str,
        bond_amount: int,
        challenger_id: str
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
            slash_amount_per_verifier=0
        )
