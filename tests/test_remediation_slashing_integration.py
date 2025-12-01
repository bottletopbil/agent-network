"""
Test for slashing integration in challenge outcomes (ECON-002).

This test verifies that the slashing logic properly integrates with the challenge
outcome system to penalize dishonest verifiers and reward successful challengers.
"""

import sys
from pathlib import Path
import tempfile

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from economics.ledger import CreditLedger
from economics.stake import StakeManager
from economics.slashing import SlashingRules
from challenges.outcomes import OutcomeHandler, ChallengeOutcome


def test_slashing_integration_upheld_challenge():
    """
    Test that when a challenge is UPHELD, verifiers are actually slashed
    and the challenger receives rewards.

    Currently this test FAILS because slashing code is commented out.
    """
    # Set up persistent storage
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)
        stake_manager = StakeManager(ledger)
        SlashingRules(stake_manager)

        # Create outcome handler with stake manager
        outcome_handler = OutcomeHandler(ledger=ledger, stake_manager=stake_manager)

        # Set up verifier account with 10,000 staked credits
        ledger.create_account("verifier1", initial_balance=15000)
        stake_manager.stake("verifier1", 10000)

        # Create system account with balance for rewards
        ledger.create_account("system", initial_balance=100000)

        # Set up challenger account
        ledger.create_account("challenger", initial_balance=1000)

        # Create bond escrow for challenge
        bond_amount = 500
        ledger.escrow("challenger", bond_amount, "challenge_bond_ch123")

        # Verify initial state
        verifier_before = ledger.get_account("verifier1")
        assert verifier_before.locked == 10000  # Staked amount
        assert verifier_before.balance == 5000  # Remaining balance

        challenger_before = ledger.get_account("challenger")
        assert challenger_before.balance == 500  # 1000 - 500 escrowed
        assert challenger_before.locked == 500  # Bond in escrow

        # Process UPHELD outcome
        result = outcome_handler.process_outcome(
            challenge_id="ch123",
            outcome=ChallengeOutcome.UPHELD,
            bond_amount=bond_amount,
            challenger_id="challenger",
            verifiers=["verifier1"],
            verifier_stakes={"verifier1": 10000},
        )

        # ASSERT: Verifier's stake should be reduced by 50%
        verifier_after = ledger.get_account("verifier1")
        expected_slash = 5000  # 50% of 10,000
        assert (
            verifier_after.locked == 5000
        ), f"Expected verifier stake reduced to 5000, got {verifier_after.locked}"

        # ASSERT: Challenger should receive bond back + reward
        challenger_after = ledger.get_account("challenger")
        expected_reward = bond_amount * 2  # 2x bond as per UPHELD_REWARD_MULTIPLIER
        # Bond released (500) + reward (1000) + original balance (500) = 2000
        expected_balance = 500 + bond_amount + expected_reward
        assert (
            challenger_after.balance == expected_balance
        ), f"Expected challenger balance {expected_balance}, got {challenger_after.balance}"
        assert challenger_after.locked == 0  # Bond released

        # ASSERT: Result structure is correct
        assert result.outcome == ChallengeOutcome.UPHELD
        assert result.bond_returned == bond_amount
        assert result.verifiers_slashed == ["verifier1"]
        assert result.slash_amount_per_verifier == expected_slash


def test_slashing_multiple_verifiers():
    """
    Test slashing with multiple dishonest verifiers.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)
        stake_manager = StakeManager(ledger)

        outcome_handler = OutcomeHandler(ledger=ledger, stake_manager=stake_manager)

        # Set up 3 verifiers with different stakes
        for i, stake in enumerate([10000, 20000, 15000], start=1):
            ledger.create_account(f"verifier{i}", initial_balance=stake + 5000)
            stake_manager.stake(f"verifier{i}", stake)

        # Create system account for rewards
        ledger.create_account("system", initial_balance=100000)

        # Set up challenger
        ledger.create_account("challenger", initial_balance=1000)
        bond_amount = 300
        ledger.escrow("challenger", bond_amount, "challenge_bond_ch456")

        # Process UPHELD outcome for all 3 verifiers
        result = outcome_handler.process_outcome(
            challenge_id="ch456",
            outcome=ChallengeOutcome.UPHELD,
            bond_amount=bond_amount,
            challenger_id="challenger",
            verifiers=["verifier1", "verifier2", "verifier3"],
            verifier_stakes={
                "verifier1": 10000,
                "verifier2": 20000,
                "verifier3": 15000,
            },
        )

        # ASSERT: All verifiers slashed by 50%
        v1 = ledger.get_account("verifier1")
        v2 = ledger.get_account("verifier2")
        v3 = ledger.get_account("verifier3")

        assert v1.locked == 5000  # 50% of 10000
        assert v2.locked == 10000  # 50% of 20000
        assert v3.locked == 7500  # 50% of 15000

        assert len(result.verifiers_slashed) == 3


def test_no_slashing_when_rejected():
    """
    Test that verifiers are NOT slashed when challenge is REJECTED.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)
        stake_manager = StakeManager(ledger)

        outcome_handler = OutcomeHandler(ledger=ledger, stake_manager=stake_manager)

        # Set up verifier
        ledger.create_account("verifier1", initial_balance=15000)
        stake_manager.stake("verifier1", 10000)

        # Set up challenger
        ledger.create_account("challenger", initial_balance=1000)
        bond_amount = 500
        ledger.escrow("challenger", bond_amount, "challenge_bond_ch789")

        # Process REJECTED outcome (challenger was wrong)
        result = outcome_handler.process_outcome(
            challenge_id="ch789",
            outcome=ChallengeOutcome.REJECTED,
            bond_amount=bond_amount,
            challenger_id="challenger",
        )

        # ASSERT: Verifier stake unchanged
        verifier = ledger.get_account("verifier1")
        assert verifier.locked == 10000  # No slashing

        # ASSERT: Challenger bond slashed
        assert result.bond_slashed == bond_amount
        assert result.verifiers_slashed == []
