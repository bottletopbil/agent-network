"""
Test for proportional challenge reward scaling (ECON-009).

Validates that challenge rewards scale with slashed amount.
"""

import sys
from pathlib import Path
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_reward_scales_with_slashed_amount():
    """
    Test that challenging larger violations yields proportionally larger rewards.
    """
    from challenges.outcomes import ChallengeOutcomes
    from economics.ledger import CreditLedger
    
    ledger = CreditLedger()
    outcomes = ChallengeOutcomes(ledger)
    
    # Scenario 1: Challenge 1 verifier with 10k stake → 5k slashed
    ledger.create_account("challenger1", 1000)  # Bond
    ledger.create_account("verifier1", 10000)
    
    result1 = outcomes.process_outcome(
        challenge_id="challenge1",
        challenger_id="challenger1",
        dishonest_verifiers=["verifier1"],
        honest_verifiers=[],
        total_slashed=5000
    )
    
    reward1 = result1.get("challenger_reward", 0)
    
    # Scenario 2: Challenge 10 verifiers with 10k each → 50k slashed
    ledger.create_account("challenger2", 1000)  # Bond
    for i in range(10):
        ledger.create_account(f"verifier{i+10}", 10000)
    
    result2 = outcomes.process_outcome(
        challenge_id="challenge2",
        challenger_id="challenger2",
        dishonest_verifiers=[f"verifier{i+10}" for i in range(10)],
        honest_verifiers=[],
        total_slashed=50000
    )
    
    reward2 = result2.get("challenger_reward", 0)
    
    # Reward should scale proportionally (~10x)
    ratio = reward2 / reward1 if reward1 > 0 else 0
    
    print(f"Scenario 1 reward: {reward1} (5k slashed)")
    print(f"Scenario 2 reward: {reward2} (50k slashed)")
    print(f"Ratio: {ratio}x")
    
    # Should be approximately 10x (50k / 5k)
    assert ratio >= 9.0, f"Reward should scale ~10x, got {ratio}x"
    assert ratio <= 11.0, f"Reward should scale ~10x, got {ratio}x"


def test_reward_is_20_percent_of_slashed():
    """
    Test that reward is 20% of total slashed amount.
    """
    from challenges.outcomes import ChallengeOutcomes
    from economics.ledger import CreditLedger
    
    ledger = CreditLedger()
    outcomes = ChallengeOutcomes(ledger)
    
    ledger.create_account("challenger", 1000)
    ledger.create_account("verifier", 20000)
    
    total_slashed = 10000
    
    result = outcomes.process_outcome(
        challenge_id="challenge1",
        challenger_id="challenger",
        dishonest_verifiers=["verifier"],
        honest_verifiers=[],
        total_slashed=total_slashed
    )
    
    reward = result.get("challenger_reward", 0)
    expected_reward = int(total_slashed * 0.20)
    
    print(f"Total slashed: {total_slashed}")
    print(f"Reward: {reward}")
    print(f"Expected (20%): {expected_reward}")
    
    # Should be 20% of slashed amount
    assert reward == expected_reward, f"Reward should be {expected_reward}, got {reward}"


def test_small_slash_gives_small_reward():
    """
    Test that small slashed amounts give small rewards.
    """
    from challenges.outcomes import ChallengeOutcomes
    from economics.ledger import CreditLedger
    
    ledger = CreditLedger()
    outcomes = ChallengeOutcomes(ledger)
    
    ledger.create_account("challenger", 100)
    ledger.create_account("verifier", 1000)
    
    # Small slash
    total_slashed = 500
    
    result = outcomes.process_outcome(
        challenge_id="challenge1",
        challenger_id="challenger",
        dishonest_verifiers=["verifier"],
        honest_verifiers=[],
        total_slashed=total_slashed
    )
    
    reward = result.get("challenger_reward", 0)
    
    # Should be proportional (20% of 500 = 100)
    assert reward == 100, f"Small slash should give small reward, got {reward}"


def test_bond_returned_plus_reward():
    """
    Test that challenger gets bond back + proportional reward.
    """
    from challenges.outcomes import ChallengeOutcomes
    from economics.ledger import CreditLedger
    
    ledger = CreditLedger()
    outcomes = ChallengeOutcomes(ledger)
    
    bond_amount = 1000
    ledger.create_account("challenger", bond_amount)
    ledger.create_account("verifier", 10000)
    
    initial_balance = ledger.get_balance("challenger")
    
    total_slashed = 5000
    expected_reward = int(total_slashed * 0.20)  # 1000
    
    result = outcomes.process_outcome(
        challenge_id="challenge1",
        challenger_id="challenger",
        dishonest_verifiers=["verifier"],
        honest_verifiers=[],
        total_slashed=total_slashed
    )
    
    final_balance = ledger.get_balance("challenger")
    
    # Should get bond back (1000) + reward (1000) = net +1000
    gain = final_balance - initial_balance
    
    print(f"Initial: {initial_balance}, Final: {final_balance}, Gain: {gain}")
    
    assert gain == expected_reward, f"Should gain {expected_reward}, got {gain}"
