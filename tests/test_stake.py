"""
Unit tests for Stake System and Slashing.

Tests staking operations, unbonding periods, and slashing execution.
"""

import sys
import os
import tempfile
from pathlib import Path
import time

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from economics.ledger import CreditLedger, InsufficientBalanceError
from economics.stake import StakeManager, InsufficientStakeError
from economics.slashing import SlashingRules, ViolationType, SlashEvent
import uuid


class TestStakeOperations:
    """Test basic staking operations"""

    def test_stake_and_unstake(self):
        """Test basic stake and unstake flow"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger, unbonding_days=7)

        # Create account
        ledger.create_account("verifier1", 10000)

        # Stake credits
        stake_mgr.stake("verifier1", 5000)

        # Verify staked
        assert stake_mgr.get_staked_amount("verifier1") == 5000
        assert ledger.get_balance("verifier1") == 5000

        # Unstake
        unbonding_id = stake_mgr.unstake("verifier1", 3000)
        assert unbonding_id is not None

        # Verify moved to unbonding
        assert stake_mgr.get_staked_amount("verifier1") == 2000
        assert stake_mgr.get_unbonding_amount("verifier1") == 3000

    def test_stake_insufficient_balance(self):
        """Test staking with insufficient balance"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)

        ledger.create_account("verifier1", 1000)

        with pytest.raises(InsufficientBalanceError):
            stake_mgr.stake("verifier1", 2000)

    def test_unstake_insufficient_stake(self):
        """Test unstaking more than staked amount"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)

        with pytest.raises(InsufficientStakeError):
            stake_mgr.unstake("verifier1", 6000)

    def test_get_staked_amount(self):
        """Test querying staked amount"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)

        ledger.create_account("verifier1", 10000)

        # Initially zero
        assert stake_mgr.get_staked_amount("verifier1") == 0

        # After staking
        stake_mgr.stake("verifier1", 3000)
        assert stake_mgr.get_staked_amount("verifier1") == 3000

        # After unstaking
        stake_mgr.unstake("verifier1", 1000)
        assert stake_mgr.get_staked_amount("verifier1") == 2000

    def test_multiple_stakes(self):
        """Test cumulative staking"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)

        ledger.create_account("verifier1", 10000)

        # Stake in multiple operations
        stake_mgr.stake("verifier1", 2000)
        stake_mgr.stake("verifier1", 3000)
        stake_mgr.stake("verifier1", 1000)

        # Should accumulate
        assert stake_mgr.get_staked_amount("verifier1") == 6000
        assert ledger.get_balance("verifier1") == 4000


class TestUnbondingPeriod:
    """Test unbonding period enforcement"""

    def test_unbonding_period(self):
        """Test credits are locked during unbonding period"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        # Use very short unbonding period for testing (0.0001 days ≈ 8.6 seconds)
        stake_mgr = StakeManager(ledger, unbonding_days=0.0001)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        stake_mgr.unstake("verifier1", 5000)

        # Should be in unbonding
        assert stake_mgr.get_unbonding_amount("verifier1") == 5000
        assert ledger.get_balance("verifier1") == 5000

        # Try to complete immediately (should not release)
        released = stake_mgr.complete_unbonding("verifier1")
        assert released == 0
        assert stake_mgr.get_unbonding_amount("verifier1") == 5000

    def test_complete_unbonding_before_period(self):
        """Test cannot complete unbonding before period elapses"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger, unbonding_days=1)  # 1 day

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        stake_mgr.unstake("verifier1", 5000)

        # Try to complete immediately
        released = stake_mgr.complete_unbonding("verifier1")
        assert released == 0

    def test_complete_unbonding_after_period(self):
        """Test can complete unbonding after period elapses"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        # Very short period for testing
        stake_mgr = StakeManager(ledger, unbonding_days=0.00001)  # ~0.86 seconds

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        stake_mgr.unstake("verifier1", 5000)

        # Wait for unbonding period
        time.sleep(1.5)

        # Should be able to complete
        released = stake_mgr.complete_unbonding("verifier1")
        assert released == 5000
        assert stake_mgr.get_unbonding_amount("verifier1") == 0
        assert ledger.get_balance("verifier1") == 10000

    def test_multiple_unbonding_records(self):
        """Test multiple concurrent unbonding periods"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        # Use longer period so records don't auto-complete
        stake_mgr = StakeManager(ledger, unbonding_days=1)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 9000)

        # Create multiple unbonding records
        stake_mgr.unstake("verifier1", 3000)
        stake_mgr.unstake("verifier1", 2000)
        stake_mgr.unstake("verifier1", 1000)

        # Should have 3 unbonding records
        records = stake_mgr.get_unbonding_records("verifier1")
        assert len(records) == 3
        assert stake_mgr.get_unbonding_amount("verifier1") == 6000

        # Cannot complete yet (still in unbonding period)
        released = stake_mgr.complete_unbonding("verifier1")
        assert released == 0

        # Verify all records are tracked
        assert all(not r.completed for r in records)
        assert stake_mgr.get_staked_amount("verifier1") == 3000  # Remaining stake

    def test_get_unbonding_amount(self):
        """Test querying unbonding amount"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)

        ledger.create_account("verifier1", 10000)

        # Initially zero
        assert stake_mgr.get_unbonding_amount("verifier1") == 0

        # After unstaking
        stake_mgr.stake("verifier1", 5000)
        stake_mgr.unstake("verifier1", 3000)
        assert stake_mgr.get_unbonding_amount("verifier1") == 3000


class TestSlashing:
    """Test slashing execution and calculations"""

    def test_slashing_execution(self):
        """Test executing a slash reduces stake"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        slashing = SlashingRules(stake_mgr)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)

        # Create slash event
        event = SlashEvent(
            event_id=str(uuid.uuid4()),
            account_id="verifier1",
            reason=ViolationType.FAILED_CHALLENGE,
            amount=2500,  # 50% of 5000
            evidence_hash="evidence123",
            severity=5,
            timestamp=time.time_ns(),
        )

        # Execute slash
        slashing.execute_slash(event)

        # Verify stake reduced
        assert stake_mgr.get_staked_amount("verifier1") == 2500

    def test_slash_failed_challenge(self):
        """Test failed challenge slashes 50% of stake"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        slashing = SlashingRules(stake_mgr)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 6000)

        # Calculate slash amount
        slash_amount = slashing.calculate_slash_amount(
            "verifier1", ViolationType.FAILED_CHALLENGE, severity=5
        )

        # Should be 50%
        assert slash_amount == 3000

    def test_slash_missed_heartbeat(self):
        """Test missed heartbeat slashes 1% per miss"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        slashing = SlashingRules(stake_mgr)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)

        # 3 missed heartbeats = 3% slash
        slash_amount = slashing.calculate_slash_amount(
            "verifier1", ViolationType.MISSED_HEARTBEAT, severity=3
        )

        assert slash_amount == 150  # 5000 * 0.03

        # 10 missed heartbeats = 10% (max)
        slash_amount = slashing.calculate_slash_amount(
            "verifier1", ViolationType.MISSED_HEARTBEAT, severity=10
        )

        assert slash_amount == 500  # 5000 * 0.10

    def test_slash_policy_violation(self):
        """Test policy violation slashes 10% with escalation"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        slashing = SlashingRules(stake_mgr)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 10000)

        # Base severity (5) = 10% × (1 + 0.5) = 15%
        slash_amount = slashing.calculate_slash_amount(
            "verifier1", ViolationType.POLICY_VIOLATION, severity=5
        )
        assert slash_amount == 1500  # 10000 * 0.15

        # High severity (10) = 10% × (1 + 1.0) = 20%
        slash_amount = slashing.calculate_slash_amount(
            "verifier1", ViolationType.POLICY_VIOLATION, severity=10
        )
        assert slash_amount == 2000  # 10000 * 0.20

        # Low severity (0) = 10% × (1 + 0) = 10%
        slash_amount = slashing.calculate_slash_amount(
            "verifier1", ViolationType.POLICY_VIOLATION, severity=0
        )
        assert slash_amount == 1000  # 10000 * 0.10

    def test_slash_insufficient_stake(self):
        """Test slashing handles insufficient stake gracefully"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        slashing = SlashingRules(stake_mgr)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 1000)

        # Try to slash more than staked
        event = SlashEvent(
            event_id=str(uuid.uuid4()),
            account_id="verifier1",
            reason=ViolationType.FAILED_CHALLENGE,
            amount=5000,  # More than staked
            evidence_hash="evidence123",
            severity=5,
            timestamp=time.time_ns(),
        )

        # Should slash all available stake
        slashing.execute_slash(event)
        assert stake_mgr.get_staked_amount("verifier1") == 0

    def test_slash_history(self):
        """Test slash history tracking"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        slashing = SlashingRules(stake_mgr)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)

        # Create multiple slash events
        event1 = SlashEvent(
            event_id=str(uuid.uuid4()),
            account_id="verifier1",
            reason=ViolationType.MISSED_HEARTBEAT,
            amount=50,
            evidence_hash="evidence1",
            severity=1,
            timestamp=time.time_ns(),
        )

        event2 = SlashEvent(
            event_id=str(uuid.uuid4()),
            account_id="verifier1",
            reason=ViolationType.POLICY_VIOLATION,
            amount=500,
            evidence_hash="evidence2",
            severity=5,
            timestamp=time.time_ns(),
        )

        slashing.execute_slash(event1)
        slashing.execute_slash(event2)

        # Get history
        history = slashing.get_slash_history("verifier1")
        assert len(history) == 2
        assert history[0].reason == ViolationType.POLICY_VIOLATION  # Newest first
        assert history[1].reason == ViolationType.MISSED_HEARTBEAT


class TestStakeRequirements:
    """Test stake requirement checks"""

    def test_stake_requirements_met(self):
        """Test checking if stake requirements are met"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)

        # Check minimum stake requirement
        min_stake = 1000
        assert stake_mgr.get_staked_amount("verifier1") >= min_stake

    def test_stake_after_slash(self):
        """Test stake is reduced after slashing"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        slashing = SlashingRules(stake_mgr)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)

        initial_stake = stake_mgr.get_staked_amount("verifier1")

        # Slash
        event = SlashEvent(
            event_id=str(uuid.uuid4()),
            account_id="verifier1",
            reason=ViolationType.MISSED_HEARTBEAT,
            amount=500,
            evidence_hash="evidence123",
            severity=10,
            timestamp=time.time_ns(),
        )
        slashing.execute_slash(event)

        # Stake should be reduced
        assert stake_mgr.get_staked_amount("verifier1") < initial_stake
        assert stake_mgr.get_staked_amount("verifier1") == 4500

    def test_unbonding_not_counted_in_stake(self):
        """Test unbonding credits are not counted as staked"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 8000)

        # Unstake half
        stake_mgr.unstake("verifier1", 4000)

        # Only remaining locked amount counts as staked
        assert stake_mgr.get_staked_amount("verifier1") == 4000
        assert stake_mgr.get_unbonding_amount("verifier1") == 4000

        # Total locked + unbonding = original stake
        account = ledger.get_account("verifier1")
        assert account.locked + account.unbonding == 8000

    def test_zero_stake_for_nonexistent_account(self):
        """Test querying stake for nonexistent account returns zero"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)

        assert stake_mgr.get_staked_amount("nonexistent") == 0
        assert stake_mgr.get_unbonding_amount("nonexistent") == 0


class TestIntegration:
    """Integration tests for complete workflows"""

    def test_complete_stake_lifecycle(self):
        """Test complete lifecycle: stake → slash → unstake → complete"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger, unbonding_days=0.00001)
        slashing = SlashingRules(stake_mgr)

        # Setup
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 6000)
        assert stake_mgr.get_staked_amount("verifier1") == 6000

        # Slash for violation
        event = SlashEvent(
            event_id=str(uuid.uuid4()),
            account_id="verifier1",
            reason=ViolationType.MISSED_HEARTBEAT,
            amount=300,  # 5% of 6000
            evidence_hash="evidence123",
            severity=5,
            timestamp=time.time_ns(),
        )
        slashing.execute_slash(event)
        assert stake_mgr.get_staked_amount("verifier1") == 5700

        # Unstake remaining
        stake_mgr.unstake("verifier1", 5700)
        assert stake_mgr.get_unbonding_amount("verifier1") == 5700

        # Wait and complete
        time.sleep(1)
        released = stake_mgr.complete_unbonding("verifier1")
        assert released == 5700

        # Final balance: 10000 original - 300 slashed = 9700
        assert ledger.get_balance("verifier1") == 9700
