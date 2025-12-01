"""
Tests for Phase 8.4 - Slashing and Payouts

Tests:
- Slashing on invalid results
- Payout distribution (50% challenger, 40% honest, 10% burn)
- Related party blocking
- K_result escalation
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "src"))

import pytest
import time

from economics.ledger import CreditLedger
from economics.stake import StakeManager
from economics.slashing import SlashingRules
from economics.payout import PayoutDistributor
from economics.bounties import BountyManager, TaskClass
from economics.relationships import RelationshipDetector, PartyInfo
from handlers.invalidate import calculate_k_escalation


@pytest.fixture
def db_path(tmp_path):
    """Create temporary database"""
    return tmp_path / "test_slashing_payout.db"


@pytest.fixture
def ledger(db_path):
    """Create ledger instance"""
    return CreditLedger(db_path)


@pytest.fixture
def stake_manager(ledger):
    """Create stake manager"""
    return StakeManager(ledger)


@pytest.fixture
def slashing_rules(stake_manager):
    """Create slashing rules"""
    return SlashingRules(stake_manager)


@pytest.fixture
def bounty_manager(ledger):
    """Create bounty manager"""
    return BountyManager(ledger)


@pytest.fixture
def relationship_detector():
    """Create relationship detector"""
    return RelationshipDetector()


@pytest.fixture
def payout_distributor(bounty_manager, relationship_detector):
    """Create payout distributor"""
    return PayoutDistributor(bounty_manager, relationship_detector)


class TestSlashOnInvalidResult:
    """Test slashing verifiers when challenge is upheld"""

    def test_slash_single_verifier(self, stake_manager, slashing_rules, ledger):
        """Test slashing a single verifier at 50% stake"""
        # Setup
        verifier = "verifier1"
        challenger = "challenger1"

        # Fund and stake
        ledger.create_account(verifier, 10000)
        stake_manager.stake(verifier, 10000)
        ledger.create_account(challenger, 1000)

        # Slash
        result = slashing_rules.slash_verifiers(
            verifiers=[verifier],
            challenge_evidence="evidence_hash_123",
            challenger=challenger,
            honest_verifiers=[],
        )

        # Verify slashing (50% of 10000 = 5000)
        assert result["total_slashed"] == 5000
        assert result["challenger_payout"] == 2500  # 50% of slashed
        assert result["honest_payout"] == 2000  # 40% of slashed
        assert result["burned"] == 500  # 10% of slashed

        # Verify stake reduced
        assert stake_manager.get_staked_amount(verifier) == 5000

        # Verify challenger got paid
        assert ledger.get_balance(challenger) == 1000 + 2500

    def test_slash_multiple_verifiers(self, stake_manager, slashing_rules, ledger):
        """Test slashing multiple verifiers"""
        # Setup
        verifier1 = "verifier1"
        verifier2 = "verifier2"
        challenger = "challenger1"

        # Fund and stake
        ledger.create_account(verifier1, 10000)
        ledger.create_account(verifier2, 20000)
        stake_manager.stake(verifier1, 10000)
        stake_manager.stake(verifier2, 20000)
        ledger.create_account(challenger, 1000)

        # Slash
        result = slashing_rules.slash_verifiers(
            verifiers=[verifier1, verifier2],
            challenge_evidence="evidence_hash_456",
            challenger=challenger,
            honest_verifiers=[],
        )

        # Verify slashing (50% of 10000 + 50% of 20000 = 15000 total)
        assert result["total_slashed"] == 15000
        assert result["challenger_payout"] == 7500  # 50% of 15000
        assert result["honest_payout"] == 6000  # 40% of 15000
        assert result["burned"] == 1500  # 10% of 15000

        # Verify stakes reduced
        assert stake_manager.get_staked_amount(verifier1) == 5000
        assert stake_manager.get_staked_amount(verifier2) == 10000


class TestPayoutDistribution:
    """Test payout distribution with slashed amounts"""

    def test_distribute_to_honest_verifiers(
        self, stake_manager, slashing_rules, ledger
    ):
        """Test distributing slashed amounts to honest verifiers"""
        # Setup
        verifier1 = "verifier1"  # Dishonest
        verifier2 = "verifier2"  # Dishonest
        honest1 = "honest1"
        honest2 = "honest2"
        challenger = "challenger1"

        # Fund and stake
        ledger.create_account(verifier1, 10000)
        ledger.create_account(verifier2, 10000)
        ledger.create_account(honest1, 1000)
        ledger.create_account(honest2, 1000)
        ledger.create_account(challenger, 1000)
        stake_manager.stake(verifier1, 10000)
        stake_manager.stake(verifier2, 10000)

        # Slash with honest verifiers
        result = slashing_rules.slash_verifiers(
            verifiers=[verifier1, verifier2],
            challenge_evidence="evidence_hash_789",
            challenger=challenger,
            honest_verifiers=[honest1, honest2],
        )

        # Total slashed: 5000 + 5000 = 10000
        # Challenger: 5000
        # Honest total: 4000 (split equally: 2000 each)
        # Burned: 1000

        assert result["total_slashed"] == 10000
        assert result["challenger_payout"] == 5000
        assert result["honest_payout"] == 4000
        assert result["burned"] == 1000

        # Verify payouts
        assert ledger.get_balance(challenger) == 1000 + 5000
        assert ledger.get_balance(honest1) == 1000 + 2000
        assert ledger.get_balance(honest2) == 1000 + 2000

    def test_burn_amount(self, stake_manager, slashing_rules, ledger):
        """Test that burn amount is properly calculated"""
        # Setup
        verifier = "verifier1"
        challenger = "challenger1"

        ledger.create_account(verifier, 10000)
        stake_manager.stake(verifier, 10000)
        ledger.create_account(challenger, 0)

        # Slash
        result = slashing_rules.slash_verifiers(
            verifiers=[verifier],
            challenge_evidence="evidence_burn",
            challenger=challenger,
            honest_verifiers=[],
        )

        # Verify burn amount (10% of slashed)
        assert result["burned"] == 500
        # Total should equal sum of parts
        assert result["total_slashed"] == (
            result["challenger_payout"] + result["honest_payout"] + result["burned"]
        )


class TestRelatedPartyBlocking:
    """Test related party detection blocks payouts"""

    def test_same_org_blocking(
        self, relationship_detector, payout_distributor, bounty_manager, ledger
    ):
        """Test that same organization blocks payout"""
        # Setup parties
        challenger = "challenger1"
        verifier1 = "verifier1"
        verifier2 = "verifier2"

        # Register with same org
        relationship_detector.register_party(
            PartyInfo(account_id=challenger, org_domain="acme.com")
        )
        relationship_detector.register_party(
            PartyInfo(account_id=verifier1, org_domain="acme.com")
        )
        relationship_detector.register_party(
            PartyInfo(account_id=verifier2, org_domain="other.com")
        )

        # Detect relationship
        assert (
            relationship_detector.detect_same_org([verifier1, verifier2], challenger)
            is True
        )

        # Create bounty
        ledger.create_account("depositor", 10000)
        bounty_id = bounty_manager.create_bounty(
            "task1", 100, TaskClass.COMPLEX, "depositor"
        )

        # Attempt payout should fail (related party)
        with pytest.raises(ValueError, match="Related party conflict"):
            payout_distributor.execute_payout(
                bounty_id=bounty_id,
                task_id="task1",
                committee=[verifier1, verifier2],
                task_completion_time_ns=time.time_ns()
                - (11 * 60 * 1_000_000_000),  # 11 min ago
                challenger=challenger,
            )

    def test_same_asn_blocking(
        self, relationship_detector, payout_distributor, bounty_manager, ledger
    ):
        """Test that same ASN blocks payout"""
        # Setup parties
        challenger = "challenger1"
        verifier1 = "verifier1"

        # Register with same ASN
        relationship_detector.register_party(
            PartyInfo(account_id=challenger, asn=12345)
        )
        relationship_detector.register_party(PartyInfo(account_id=verifier1, asn=12345))

        # Detect relationship
        assert relationship_detector.detect_same_asn([verifier1], challenger) is True

        # Create bounty
        ledger.create_account("depositor", 10000)
        bounty_id = bounty_manager.create_bounty(
            "task1", 100, TaskClass.COMPLEX, "depositor"
        )

        # Attempt payout should fail
        with pytest.raises(ValueError, match="Related party conflict"):
            payout_distributor.execute_payout(
                bounty_id=bounty_id,
                task_id="task2",
                committee=[verifier1],
                task_completion_time_ns=time.time_ns() - (11 * 60 * 1_000_000_000),
                challenger=challenger,
            )

    def test_identity_link_blocking(
        self, relationship_detector, payout_distributor, bounty_manager, ledger
    ):
        """Test that identity linkage blocks payout"""
        # Setup parties
        challenger = "challenger1"
        verifier1 = "verifier1"

        # Register with same identity hash
        identity_hash = "abc123def456"
        relationship_detector.register_party(
            PartyInfo(account_id=challenger, identity_hash=identity_hash)
        )
        relationship_detector.register_party(
            PartyInfo(account_id=verifier1, identity_hash=identity_hash)
        )

        # Detect relationship
        assert (
            relationship_detector.detect_identity_links([verifier1], challenger) is True
        )

        # Create bounty
        ledger.create_account("depositor", 10000)
        bounty_id = bounty_manager.create_bounty(
            "task1", 100, TaskClass.COMPLEX, "depositor"
        )

        # Attempt payout should fail
        with pytest.raises(ValueError, match="Related party conflict"):
            payout_distributor.execute_payout(
                bounty_id=bounty_id,
                task_id="task3",
                committee=[verifier1],
                task_completion_time_ns=time.time_ns() - (11 * 60 * 1_000_000_000),
                challenger=challenger,
            )


class TestKEscalation:
    """Test K_result escalation on challenges"""

    def test_single_challenge_escalation(self):
        """Test K_result += 2 for single challenge"""
        new_k = calculate_k_escalation(
            current_k=3, challenge_count=1, active_verifiers=100, upheld_challenges=1
        )
        assert new_k == 5  # 3 + 2

    def test_multiple_challenge_escalation(self):
        """Test K_result = min(active, 2×K) for multiple challenges"""
        new_k = calculate_k_escalation(
            current_k=3, challenge_count=2, active_verifiers=100, upheld_challenges=2
        )
        assert new_k == 6  # min(100, 2 × 3) = 6

    def test_escalation_capped_by_active_verifiers(self):
        """Test K_result capped by active verifiers"""
        new_k = calculate_k_escalation(
            current_k=30, challenge_count=3, active_verifiers=50, upheld_challenges=2
        )
        assert new_k == 50  # min(50, 2 × 30) = 50

    def test_no_escalation_if_no_upheld(self):
        """Test no escalation if no challenges upheld"""
        new_k = calculate_k_escalation(
            current_k=3, challenge_count=1, active_verifiers=100, upheld_challenges=0
        )
        assert new_k == 3  # No change


class TestPayoutChallengePeriod:
    """Test payout timing with challenge period"""

    def test_payout_before_challenge_period_blocked(
        self, payout_distributor, bounty_manager, ledger
    ):
        """Test payout blocked if challenge period not elapsed"""
        # Create bounty
        ledger.create_account("depositor", 10000)
        bounty_id = bounty_manager.create_bounty(
            "task1", 100, TaskClass.COMPLEX, "depositor"
        )

        # Task completed 3 minutes ago (less than 2 × T_challenge = 10 minutes)
        completion_time = time.time_ns() - (3 * 60 * 1_000_000_000)

        # Attempt payout should fail
        with pytest.raises(ValueError, match="Challenge period not elapsed"):
            payout_distributor.execute_payout(
                bounty_id=bounty_id,
                task_id="task1",
                committee=["verifier1"],
                task_completion_time_ns=completion_time,
            )

    def test_payout_after_challenge_period_allowed(
        self, payout_distributor, bounty_manager, ledger
    ):
        """Test payout allowed after challenge period"""
        # Create bounty and fund verifier
        ledger.create_account("depositor", 10000)
        bounty_id = bounty_manager.create_bounty(
            "task1", 100, TaskClass.COMPLEX, "depositor"
        )
        bounty_manager.escrow_bounty(bounty_id, "commit1")  # Escrow before payout

        # Task completed 11 minutes ago (more than 2 × T_challenge = 10 minutes)
        completion_time = time.time_ns() - (11 * 60 * 1_000_000_000)

        # Payout should succeed
        payout_distributor.execute_payout(
            bounty_id=bounty_id,
            task_id="task2",
            committee=["verifier1"],
            task_completion_time_ns=completion_time,
        )

        # Verify payout
        assert ledger.get_balance("verifier1") == 100

    def test_payout_blocked_if_invalidated(
        self, payout_distributor, bounty_manager, ledger
    ):
        """Test payout blocked if task invalidated"""
        # Create bounty
        ledger.create_account("depositor", 10000)
        bounty_id = bounty_manager.create_bounty(
            "task1", 100, TaskClass.COMPLEX, "depositor"
        )

        # Mark task as invalidated
        payout_distributor.mark_invalidated("task3")

        # Task completed long ago
        completion_time = time.time_ns() - (20 * 60 * 1_000_000_000)

        # Attempt payout should fail
        with pytest.raises(ValueError, match="Task has been invalidated"):
            payout_distributor.execute_payout(
                bounty_id=bounty_id,
                task_id="task3",
                committee=["verifier1"],
                task_completion_time_ns=completion_time,
            )
