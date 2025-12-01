"""
Unit tests for Bounty System and Payout Distribution.

Tests bounty creation, escrow, caps, and payout scenarios.
"""

import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from economics.ledger import CreditLedger
from economics.bounties import BountyManager, TaskClass
from economics.payout import PayoutDistributor


class TestBountyCreation:
    """Test bounty creation and caps"""

    def test_bounty_creation(self):
        """Test basic bounty creation"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)

        bounty_id = bounty_mgr.create_bounty(
            task_id="task-1",
            amount=50,
            task_class=TaskClass.COMPLEX,
            creator_id="creator1",
        )

        assert bounty_id is not None

        bounty = bounty_mgr.get_bounty(bounty_id)
        assert bounty.task_id == "task-1"
        assert bounty.amount == 50
        assert bounty.task_class == TaskClass.COMPLEX
        assert bounty.status == "CREATED"

    def test_bounty_caps_simple(self):
        """Test SIMPLE task cap (10 credits)"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)

        # Within cap
        bounty_id = bounty_mgr.create_bounty("task-1", 10, TaskClass.SIMPLE, "creator1")
        assert bounty_id is not None

        # Exceeds cap
        with pytest.raises(ValueError, match="exceeds SIMPLE cap"):
            bounty_mgr.create_bounty("task-2", 11, TaskClass.SIMPLE, "creator1")

    def test_bounty_caps_complex(self):
        """Test COMPLEX task cap (100 credits)"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)

        # Within cap
        bounty_id = bounty_mgr.create_bounty(
            "task-1", 100, TaskClass.COMPLEX, "creator1"
        )
        assert bounty_id is not None

        # Exceeds cap
        with pytest.raises(ValueError, match="exceeds COMPLEX cap"):
            bounty_mgr.create_bounty("task-2", 101, TaskClass.COMPLEX, "creator1")

    def test_bounty_caps_critical(self):
        """Test CRITICAL task cap (1000 credits)"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)

        # Within cap
        bounty_id = bounty_mgr.create_bounty(
            "task-1", 1000, TaskClass.CRITICAL, "creator1"
        )
        assert bounty_id is not None

        # Exceeds cap
        with pytest.raises(ValueError, match="exceeds CRITICAL cap"):
            bounty_mgr.create_bounty("task-2", 1001, TaskClass.CRITICAL, "creator1")

    def test_bounty_cap_exceeded(self):
        """Test error when exceeding cap"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)

        with pytest.raises(ValueError, match="exceeds"):
            bounty_mgr.create_bounty("task-1", 500, TaskClass.SIMPLE, "creator1")


class TestBountyEscrow:
    """Test bounty escrow operations"""

    def test_escrow_bounty(self):
        """Test escrowing a bounty"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)

        # Create account and bounty
        ledger.create_account("creator1", 1000)
        bounty_id = bounty_mgr.create_bounty(
            "task-1", 100, TaskClass.COMPLEX, "creator1"
        )

        # Escrow
        escrow_id = bounty_mgr.escrow_bounty(bounty_id, "commit-1")
        assert escrow_id is not None

        # Verify escrow
        bounty = bounty_mgr.get_bounty(bounty_id)
        assert bounty.status == "ESCROWED"
        assert bounty.escrow_id == escrow_id

        # Verify creator balance reduced
        assert ledger.get_balance("creator1") == 900

    def test_escrow_insufficient_balance(self):
        """Test error on insufficient balance for escrow"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)

        # Create account with insufficient funds
        ledger.create_account("creator1", 50)
        bounty_id = bounty_mgr.create_bounty(
            "task-1", 100, TaskClass.COMPLEX, "creator1"
        )

        # Try to escrow
        with pytest.raises(Exception):  # InsufficientBalanceError from ledger
            bounty_mgr.escrow_bounty(bounty_id, "commit-1")

    def test_escrow_already_escrowed(self):
        """Test error on double escrow"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)

        ledger.create_account("creator1", 1000)
        bounty_id = bounty_mgr.create_bounty(
            "task-1", 100, TaskClass.COMPLEX, "creator1"
        )

        # First escrow
        bounty_mgr.escrow_bounty(bounty_id, "commit-1")

        # Second escrow should fail
        with pytest.raises(ValueError, match="already"):
            bounty_mgr.escrow_bounty(bounty_id, "commit-2")

    def test_cancel_escrowed_bounty(self):
        """Test canceling returns escrowed funds"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)

        ledger.create_account("creator1", 1000)
        bounty_id = bounty_mgr.create_bounty(
            "task-1", 100, TaskClass.COMPLEX, "creator1"
        )
        bounty_mgr.escrow_bounty(bounty_id, "commit-1")

        # Cancel
        bounty_mgr.cancel_bounty(bounty_id)

        # Verify funds returned
        assert ledger.get_balance("creator1") == 1000

        # Verify status
        bounty = bounty_mgr.get_bounty(bounty_id)
        assert bounty.status == "CANCELLED"


class TestPayoutDistribution:
    """Test payout distribution calculations"""

    def test_payout_no_challenge(self):
        """Test 100% to committee payout"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)
        payout = PayoutDistributor(bounty_mgr)

        # Create accounts
        ledger.create_account("creator1", 1000)
        ledger.create_account("verifier1", 0)
        ledger.create_account("verifier2", 0)
        ledger.create_account("verifier3", 0)

        # Create and escrow bounty
        bounty_id = bounty_mgr.create_bounty(
            "task-1", 100, TaskClass.COMPLEX, "creator1"
        )
        bounty_mgr.escrow_bounty(bounty_id, "commit-1")

        # Execute payout (no challenger)
        committee = ["verifier1", "verifier2", "verifier3"]
        payout.execute_payout(bounty_id, committee)

        # Verify distribution (100 / 3 = 33 each, +1 for first)
        assert ledger.get_balance("verifier1") == 34  # 33 + remainder
        assert ledger.get_balance("verifier2") == 33
        assert ledger.get_balance("verifier3") == 33

    def test_payout_with_challenge(self):
        """Test 50/40/10 split with challenger"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)
        payout = PayoutDistributor(bounty_mgr)

        # Create accounts
        ledger.create_account("creator1", 1000)
        ledger.create_account("verifier1", 0)
        ledger.create_account("verifier2", 0)
        ledger.create_account("challenger1", 0)

        # Create and escrow bounty
        bounty_id = bounty_mgr.create_bounty(
            "task-1", 100, TaskClass.COMPLEX, "creator1"
        )
        bounty_mgr.escrow_bounty(bounty_id, "commit-1")

        # Execute payout with challenger
        committee = ["verifier1", "verifier2"]
        payout.execute_payout(bounty_id, committee, challenger="challenger1")

        # Verify distribution
        assert ledger.get_balance("challenger1") == 50  # 50%
        assert ledger.get_balance("verifier1") == 20  # 40% / 2
        assert ledger.get_balance("verifier2") == 20  # 40% / 2
        # 10% burned (10 credits to burn account)
        assert ledger.get_balance("burn") == 10

    def test_payout_single_verifier(self):
        """Test payout with single verifier committee"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)
        payout = PayoutDistributor(bounty_mgr)

        ledger.create_account("creator1", 1000)
        ledger.create_account("verifier1", 0)

        bounty_id = bounty_mgr.create_bounty(
            "task-1", 100, TaskClass.COMPLEX, "creator1"
        )
        bounty_mgr.escrow_bounty(bounty_id, "commit-1")

        # Single verifier gets everything (no challenge)
        payout.execute_payout(bounty_id, ["verifier1"])
        assert ledger.get_balance("verifier1") == 100

    def test_burn_amount(self):
        """Test 10% burn calculated correctly"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)
        payout = PayoutDistributor(bounty_mgr)

        # Calculate shares without executing
        shares = payout.calculate_shares(
            bounty_amount=100, committee=["v1", "v2"], challenger="c1"
        )

        # Find burn share
        burn_shares = [s for s in shares if s.share_type == "BURN"]
        assert len(burn_shares) == 1
        assert burn_shares[0].amount == 10  # 10% of 100


class TestRelatedParties:
    """Test related party validation"""

    def test_related_party_check(self):
        """Test challenger not in committee validation"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)
        payout = PayoutDistributor(bounty_mgr)

        committee = ["verifier1", "verifier2", "verifier3"]
        challenger = "challenger1"

        # Valid: challenger not in committee
        assert payout.validate_related_parties(committee, challenger) is True

        # Invalid: challenger in committee
        assert payout.validate_related_parties(committee, "verifier2") is False

    def test_related_party_violation(self):
        """Test error when challenger in committee"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)
        payout = PayoutDistributor(bounty_mgr)

        ledger.create_account("creator1", 1000)
        ledger.create_account("verifier1", 0)
        ledger.create_account("verifier2", 0)

        bounty_id = bounty_mgr.create_bounty(
            "task-1", 100, TaskClass.COMPLEX, "creator1"
        )
        bounty_mgr.escrow_bounty(bounty_id, "commit-1")

        # Try to execute with challenger in committee
        with pytest.raises(ValueError, match="Related party conflict"):
            payout.execute_payout(
                bounty_id,
                committee=["verifier1", "verifier2"],
                challenger="verifier1",  # Conflict!
            )


class TestIntegration:
    """Integration tests for complete workflows"""

    def test_complete_bounty_lifecycle(self):
        """Test complete lifecycle: create → escrow → distribute"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)
        payout = PayoutDistributor(bounty_mgr)

        # Setup accounts
        ledger.create_account("creator1", 1000)
        ledger.create_account("verifier1", 0)
        ledger.create_account("verifier2", 0)

        # Create bounty
        bounty_id = bounty_mgr.create_bounty(
            "task-1", 100, TaskClass.COMPLEX, "creator1"
        )
        assert bounty_mgr.get_bounty(bounty_id).status == "CREATED"

        # Escrow
        bounty_mgr.escrow_bounty(bounty_id, "commit-1")
        assert bounty_mgr.get_bounty(bounty_id).status == "ESCROWED"
        assert ledger.get_balance("creator1") == 900

        # Distribute
        payout.execute_payout(bounty_id, ["verifier1", "verifier2"])
        assert bounty_mgr.get_bounty(bounty_id).status == "DISTRIBUTED"
        assert ledger.get_balance("verifier1") == 50
        assert ledger.get_balance("verifier2") == 50

    def test_bounty_with_challenge_flow(self):
        """Test full challenge scenario"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)
        payout = PayoutDistributor(bounty_mgr)

        # Setup
        ledger.create_account("creator1", 1000)
        ledger.create_account("verifier1", 0)
        ledger.create_account("verifier2", 0)
        ledger.create_account("verifier3", 0)
        ledger.create_account("challenger1", 0)

        # Create and escrow bounty
        bounty_id = bounty_mgr.create_bounty(
            "task-1", 100, TaskClass.COMPLEX, "creator1"
        )
        bounty_mgr.escrow_bounty(bounty_id, "commit-1")

        # Challenge occurred, distribute accordingly
        committee = ["verifier1", "verifier2", "verifier3"]
        payout.execute_payout(bounty_id, committee, challenger="challenger1")

        # Verify distribution
        assert ledger.get_balance("challenger1") == 50  # 50%
        # 40% split among 3 verifiers = 13 each (40/3 = 13.33)
        assert ledger.get_balance("verifier1") == 14  # 13 + remainder
        assert ledger.get_balance("verifier2") == 13
        assert ledger.get_balance("verifier3") == 13
        # 10% burned
        assert ledger.get_balance("burn") == 10

    def test_get_task_bounty(self):
        """Test retrieving bounty by task ID"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        bounty_mgr = BountyManager(ledger)

        bounty_id = bounty_mgr.create_bounty(
            "task-1", 50, TaskClass.COMPLEX, "creator1"
        )

        # Retrieve by task ID
        bounty = bounty_mgr.get_task_bounty("task-1")
        assert bounty is not None
        assert bounty.bounty_id == bounty_id
        assert bounty.task_id == "task-1"

        # Nonexistent task
        assert bounty_mgr.get_task_bounty("task-999") is None
