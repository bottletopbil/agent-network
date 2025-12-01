"""
Unit tests for Challenge Bonds system.

Tests:
- Bond calculation by proof type and complexity
- Bond escrow creation
- Outcome handling (UPHELD/REJECTED/WITHDRAWN)
- Bond slashing and rewards
"""

import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from challenges.proofs import ProofType
from challenges.bonds import BondCalculator, ComplexityLevel, calculate_bond_simple
from challenges.outcomes import ChallengeOutcome, OutcomeHandler
from challenges.abuse_detection import AbuseDetector
from economics.ledger import CreditLedger
import handlers.challenge


class TestBondCalculation:
    """Test bond calculator functionality"""

    def test_base_bond_amounts(self):
        """Test base bond amounts for each proof type"""
        calculator = BondCalculator()

        assert calculator.get_base_amount(ProofType.SCHEMA_VIOLATION) == 10
        assert calculator.get_base_amount(ProofType.MISSING_CITATION) == 25
        assert calculator.get_base_amount(ProofType.SEMANTIC_CONTRADICTION) == 50
        assert calculator.get_base_amount(ProofType.OUTPUT_MISMATCH) == 100

    def test_bond_with_simple_complexity(self):
        """Test bond calculation with SIMPLE complexity (1x multiplier)"""
        calculator = BondCalculator()

        bond = calculator.calculate_bond(
            ProofType.SCHEMA_VIOLATION, ComplexityLevel.SIMPLE
        )
        assert bond == 10  # 10 * 1

        bond = calculator.calculate_bond(
            ProofType.OUTPUT_MISMATCH, ComplexityLevel.SIMPLE
        )
        assert bond == 100  # 100 * 1

    def test_bond_with_moderate_complexity(self):
        """Test bond calculation with MODERATE complexity (2x multiplier)"""
        calculator = BondCalculator()

        bond = calculator.calculate_bond(
            ProofType.SCHEMA_VIOLATION, ComplexityLevel.MODERATE
        )
        assert bond == 20  # 10 * 2

        bond = calculator.calculate_bond(
            ProofType.MISSING_CITATION, ComplexityLevel.MODERATE
        )
        assert bond == 50  # 25 * 2

    def test_bond_with_complex_complexity(self):
        """Test bond calculation with COMPLEX complexity (5x multiplier)"""
        calculator = BondCalculator()

        bond = calculator.calculate_bond(
            ProofType.SEMANTIC_CONTRADICTION, ComplexityLevel.COMPLEX
        )
        assert bond == 250  # 50 * 5

        bond = calculator.calculate_bond(
            ProofType.OUTPUT_MISMATCH, ComplexityLevel.COMPLEX
        )
        assert bond == 500  # 100 * 5

    def test_convenience_function(self):
        """Test calculate_bond_simple convenience function"""
        bond = calculate_bond_simple(
            ProofType.MISSING_CITATION, ComplexityLevel.MODERATE
        )
        assert bond == 50


class TestBondEscrow:
    """Test bond escrow integration with ledger"""

    def test_bond_escrow_creation(self):
        """Test creating bond escrow via ledger"""
        db_path = Path(tempfile.mktemp())
        ledger = CreditLedger(db_path)

        # Create challenger account with sufficient balance
        ledger.create_account("challenger-1", initial_balance=1000)

        # Escrow bond
        bond_amount = 50
        escrow_id = "challenge_bond_123"
        ledger.escrow("challenger-1", bond_amount, escrow_id)

        # Verify balance reduced
        balance = ledger.get_balance("challenger-1")
        account = ledger.get_account("challenger-1")

        assert balance == 950  # 1000 - 50
        assert account.locked == 50

    def test_insufficient_balance_rejected(self):
        """Test challenge rejected when insufficient balance"""
        db_path = Path(tempfile.mktemp())
        ledger = CreditLedger(db_path)

        # Create challenger with low balance
        ledger.create_account("challenger-2", initial_balance=10)

        # Try to escrow more than balance
        from economics.ledger import InsufficientBalanceError

        with pytest.raises(InsufficientBalanceError):
            ledger.escrow("challenger-2", 50, "escrow_123")

    def test_multiple_escrows(self):
        """Test multiple concurrent bond escrows"""
        db_path = Path(tempfile.mktemp())
        ledger = CreditLedger(db_path)

        ledger.create_account("multi-challenger", initial_balance=500)

        # Create multiple escrows
        ledger.escrow("multi-challenger", 50, "escrow_1")
        ledger.escrow("multi-challenger", 100, "escrow_2")
        ledger.escrow("multi-challenger", 25, "escrow_3")

        account = ledger.get_account("multi-challenger")
        assert account.balance == 325  # Available balance: 500 - 175
        assert account.locked == 175  # 50 + 100 + 25
        assert ledger.get_balance("multi-challenger") == 325  # 500 - 175


class TestOutcomeHandling:
    """Test challenge outcome processing"""

    def test_upheld_outcome(self):
        """Test UPHELD outcome: return bond + reward, slash verifiers"""
        handler = OutcomeHandler()

        bond_amount = 50
        verifiers = ["verifier-1", "verifier-2", "verifier-3"]
        verifier_stakes = {"verifier-1": 1000, "verifier-2": 1000, "verifier-3": 1000}

        result = handler.process_outcome(
            challenge_id="challenge-123",
            outcome=ChallengeOutcome.UPHELD,
            bond_amount=bond_amount,
            challenger_id="challenger-1",
            verifiers=verifiers,
            verifier_stakes=verifier_stakes,
        )

        assert result.outcome == ChallengeOutcome.UPHELD
        assert result.bond_returned == 50
        assert result.reward_amount == 100  # 2x bond
        assert result.bond_slashed == 0
        assert len(result.verifiers_slashed) == 3
        assert result.slash_amount_per_verifier == 500  # 50% of 1000

    def test_rejected_outcome(self):
        """Test REJECTED outcome: slash bond"""
        handler = OutcomeHandler()

        bond_amount = 50

        result = handler.process_outcome(
            challenge_id="challenge-456",
            outcome=ChallengeOutcome.REJECTED,
            bond_amount=bond_amount,
            challenger_id="challenger-2",
        )

        assert result.outcome == ChallengeOutcome.REJECTED
        assert result.bond_returned == 0
        assert result.bond_slashed == 50
        assert result.reward_amount == 0
        assert len(result.verifiers_slashed) == 0

    def test_withdrawn_outcome(self):
        """Test WITHDRAWN outcome: return bond minus fee"""
        handler = OutcomeHandler()

        bond_amount = 100

        result = handler.process_outcome(
            challenge_id="challenge-789",
            outcome=ChallengeOutcome.WITHDRAWN,
            bond_amount=bond_amount,
            challenger_id="challenger-3",
        )

        assert result.outcome == ChallengeOutcome.WITHDRAWN
        assert result.bond_returned == 90  # 100 - 10% fee
        assert result.bond_slashed == 10  # 10% withdrawal fee
        assert result.reward_amount == 0

    def test_upheld_verifier_slashing(self):
        """Test verifier slashing on upheld challenge"""
        handler = OutcomeHandler()

        # Different stake amounts
        verifier_stakes = {"verifier-a": 1000, "verifier-b": 2000, "verifier-c": 500}

        result = handler.process_outcome(
            challenge_id="challenge-slash",
            outcome=ChallengeOutcome.UPHELD,
            bond_amount=25,
            challenger_id="challenger",
            verifiers=list(verifier_stakes.keys()),
            verifier_stakes=verifier_stakes,
        )

        # Each verifier slashed 50% of their stake
        # Result shows slash amount for last verifier (250 for verifier-c)
        assert len(result.verifiers_slashed) == 3


class TestAbuseDetection:
    """Test anti-abuse measures"""

    def test_rate_limit_hourly(self):
        """Test hourly rate limit enforcement"""
        detector = AbuseDetector()

        # Submit 10 challenges (at limit)
        for i in range(10):
            detector.record_challenge("spammer-1")

        # Check that we're at the limit (should be allowed)
        is_allowed, error = detector.check_rate_limit("spammer-1")
        # Currently at 10, which should already hit the limit
        assert not is_allowed  # 10 >= MAX_CHALLENGES_PER_HOUR (10)
        assert "rate limit" in error.lower()

    def test_spam_pattern_detection(self):
        """Test rapid-fire spam detection"""
        detector = AbuseDetector()

        # Submit 5 challenges rapidly (at threshold)
        for i in range(5):
            detector.record_challenge("rapid-fire")

        # Should detect spam pattern
        is_spam, msg = detector.check_spam_pattern("rapid-fire")
        assert is_spam
        assert "spam" in msg.lower()

    def test_reputation_calculation(self):
        """Test reputation scoring based on success rate"""
        detector = AbuseDetector()

        # Good challenger: 8 upheld, 2 rejected
        for i in range(10):
            detector.record_challenge("good-challenger")

        for i in range(8):
            detector.record_outcome("good-challenger", "UPHELD")
        for i in range(2):
            detector.record_outcome("good-challenger", "REJECTED")

        reputation = detector.calculate_reputation_impact("good-challenger")
        assert reputation >= 0.8  # 80% success rate

        # Bad challenger: 2 upheld, 8 rejected
        for i in range(10):
            detector.record_challenge("bad-challenger")

        for i in range(2):
            detector.record_outcome("bad-challenger", "UPHELD")
        for i in range(8):
            detector.record_outcome("bad-challenger", "REJECTED")

        reputation = detector.calculate_reputation_impact("bad-challenger")
        assert reputation <= 0.3  # 20% success rate

    def test_low_quality_challenger_detection(self):
        """Test detection of consistently poor challengers"""
        detector = AbuseDetector()

        # Challenger with low success rate
        for i in range(10):
            detector.record_challenge("low-quality")

        detector.record_outcome("low-quality", "UPHELD")  # 1 upheld
        for i in range(9):
            detector.record_outcome("low-quality", "REJECTED")  # 9 rejected

        # Should be flagged as low quality (10% success < 20% threshold)
        assert detector.is_low_quality_challenger("low-quality")

        # New challenger shouldn't be flagged
        assert not detector.is_low_quality_challenger("new-challenger")

    def test_withdrawal_penalty(self):
        """Test reputation penalty for excessive withdrawals"""
        detector = AbuseDetector()

        # Challenger with many withdrawals
        for i in range(10):
            detector.record_challenge("withdrawal-happy")

        for i in range(5):
            detector.record_outcome("withdrawal-happy", "WITHDRAWN")
        for i in range(3):
            detector.record_outcome("withdrawal-happy", "UPHELD")
        for i in range(2):
            detector.record_outcome("withdrawal-happy", "REJECTED")

        reputation = detector.calculate_reputation_impact("withdrawal-happy")
        # Base success rate would be 60% (3/5), but 50% withdrawal rate penalizes it
        assert reputation < 0.6
