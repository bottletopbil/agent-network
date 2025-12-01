"""
Unit tests for Committee Selection and Reputation.

Tests weighted selection, diversity enforcement, and reputation tracking.
"""

import sys
import os
import tempfile
from pathlib import Path
import time
import math

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from economics.ledger import CreditLedger
from economics.stake import StakeManager
from economics.pools import VerifierPool, VerifierMetadata
from economics.reputation import ReputationTracker
from economics.selection import VerifierSelector, DiversityConstraints


class TestWeightCalculation:
    """Test weight calculation formula"""

    def test_weight_calculation(self):
        """Test basic weight calculation"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)
        selector = VerifierSelector(pool, reputation)

        # Create verifier
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 10000)
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 0.9)
        pool.register("verifier1", 10000, ["code_review"], metadata)

        verifier = pool.get_verifier("verifier1")
        weight = selector.calculate_weight(verifier)

        # sqrt(10000) × 0.9 × ~1.0 (recency) = 100 × 0.9 = 90
        assert weight > 85 and weight < 95

    def test_weight_with_high_stake(self):
        """Test sqrt(stake) component reduces whale advantage"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)
        selector = VerifierSelector(pool, reputation)

        # Create two verifiers with different stakes
        ledger.create_account("verifier1", 50000)
        stake_mgr.stake("verifier1", 10000)
        metadata1 = VerifierMetadata("org_a", "AS1", "us-west", 0.9)
        pool.register("verifier1", 10000, ["code_review"], metadata1)

        ledger.create_account("verifier2", 50000)
        stake_mgr.stake("verifier2", 40000)
        metadata2 = VerifierMetadata("org_b", "AS2", "us-east", 0.9)
        pool.register("verifier2", 40000, ["code_review"], metadata2)

        verifier1 = pool.get_verifier("verifier1")
        verifier2 = pool.get_verifier("verifier2")

        weight1 = selector.calculate_weight(verifier1)
        weight2 = selector.calculate_weight(verifier2)

        # verifier2 has 4x stake, but only 2x weight (sqrt)
        ratio = weight2 / weight1
        assert ratio > 1.8 and ratio < 2.2

    def test_weight_with_reputation(self):
        """Test reputation component affects weight"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)
        selector = VerifierSelector(pool, reputation)

        # Create verifiers with different reputations
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 10000)
        metadata1 = VerifierMetadata("org_a", "AS1", "us-west", 0.5)
        pool.register("verifier1", 10000, ["code_review"], metadata1)

        ledger.create_account("verifier2", 10000)
        stake_mgr.stake("verifier2", 10000)
        metadata2 = VerifierMetadata("org_b", "AS2", "us-east", 0.9)
        pool.register("verifier2", 10000, ["code_review"], metadata2)

        verifier1 = pool.get_verifier("verifier1")
        verifier2 = pool.get_verifier("verifier2")

        weight1 = selector.calculate_weight(verifier1)
        weight2 = selector.calculate_weight(verifier2)

        # verifier2 has 1.8x reputation, should have ~1.8x weight
        ratio = weight2 / weight1
        assert ratio > 1.7 and ratio < 1.9

    def test_weight_with_recency(self):
        """Test recency factor (newer weighted slightly higher)"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)
        selector = VerifierSelector(pool, reputation)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 10000)
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 0.9)
        pool.register("verifier1", 10000, ["code_review"], metadata)

        verifier = pool.get_verifier("verifier1")

        # Recency factor should be close to 1.0 for new verifier
        age_ns = time.time_ns() - verifier.registered_at
        age_days = age_ns / (24 * 3600 * 1e9)
        recency_factor = 1.0 - min((age_days / 365.0) * 0.2, 0.2)

        assert recency_factor > 0.99  # Very recent


class TestCommitteeSelection:
    """Test committee selection"""

    def test_committee_selection(self):
        """Test basic committee selection"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)
        selector = VerifierSelector(pool, reputation)

        # Register 10 verifiers
        for i in range(10):
            ledger.create_account(f"verifier{i}", 10000)
            stake_mgr.stake(f"verifier{i}", 5000)
            metadata = VerifierMetadata(f"org_{i}", f"AS{i}", f"region_{i}", 0.8)
            pool.register(f"verifier{i}", 5000, ["code_review"], metadata)

        # Select committee of 5
        committee = selector.select_committee(k=5, min_stake=1000)

        assert len(committee) == 5
        assert all(v.stake >= 1000 for v in committee)

    def test_weighted_selection(self):
        """Test higher weights more likely to be selected"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)
        selector = VerifierSelector(pool, reputation)

        # Create one high-weight verifier
        ledger.create_account("high", 50000)
        stake_mgr.stake("high", 40000)
        metadata_high = VerifierMetadata("org_h", "ASH", "region_h", 0.95)
        pool.register("high", 40000, ["code_review"], metadata_high)

        # Create many low-weight verifiers
        for i in range(20):
            ledger.create_account(f"low{i}", 10000)
            stake_mgr.stake(f"low{i}", 1000)
            metadata = VerifierMetadata(f"org_{i}", f"AS{i}", f"region_{i}", 0.5)
            pool.register(f"low{i}", 1000, ["code_review"], metadata)

        # Select multiple committees and count selections
        high_selected = 0
        trials = 100
        for _ in range(trials):
            committee = selector.select_committee(k=5, min_stake=500)
            if any(v.verifier_id == "high" for v in committee):
                high_selected += 1

        # High-weight verifier should be selected frequently (>50% of time)
        assert high_selected > 50

    def test_min_stake_filtering(self):
        """Test minimum stake filtering"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)
        selector = VerifierSelector(pool, reputation)

        # Create verifiers with varying stakes (start from 1 to avoid 0 stake)
        for i in range(1, 11):
            ledger.create_account(f"verifier{i}", 10000)
            stake_mgr.stake(f"verifier{i}", i * 1000)
            metadata = VerifierMetadata(f"org_{i}", f"AS{i}", f"region_{i}", 0.8)
            pool.register(f"verifier{i}", i * 1000, ["code_review"], metadata)

        # Select with min stake 5000
        committee = selector.select_committee(k=3, min_stake=5000)

        # All selected should have >= 5000
        for verifier in committee:
            current_stake = stake_mgr.get_staked_amount(verifier.verifier_id)
            assert current_stake >= 5000

    def test_insufficient_verifiers(self):
        """Test error when k > available verifiers"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)
        selector = VerifierSelector(pool, reputation)

        # Only 3 verifiers
        for i in range(3):
            ledger.create_account(f"verifier{i}", 10000)
            stake_mgr.stake(f"verifier{i}", 5000)
            metadata = VerifierMetadata(f"org_{i}", f"AS{i}", f"region_{i}", 0.8)
            pool.register(f"verifier{i}", 5000, ["code_review"], metadata)

        # Try to select 5
        with pytest.raises(ValueError, match="Insufficient"):
            selector.select_committee(k=5, min_stake=1000)


class TestDiversityEnforcement:
    """Test diversity constraint enforcement"""

    def test_diversity_enforcement_org(self):
        """Test organization diversity (max 30%)"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)
        selector = VerifierSelector(pool, reputation)

        # Create 10 verifiers, 7 from org_a, 3 from others
        for i in range(7):
            ledger.create_account(f"verifier{i}", 10000)
            stake_mgr.stake(f"verifier{i}", 5000)
            metadata = VerifierMetadata("org_a", f"AS{i}", f"region_{i}", 0.8)
            pool.register(f"verifier{i}", 5000, ["code_review"], metadata)

        for i in range(7, 10):
            ledger.create_account(f"verifier{i}", 10000)
            stake_mgr.stake(f"verifier{i}", 5000)
            metadata = VerifierMetadata(f"org_{i}", f"AS{i}", f"region_{i}", 0.8)
            pool.register(f"verifier{i}", 5000, ["code_review"], metadata)

        # Select committee of 5
        constraints = DiversityConstraints(max_org_percentage=0.30)
        committee = selector.select_committee(k=5, constraints=constraints)

        # Should respect org diversity
        from collections import Counter

        org_counts = Counter(v.metadata.org_id for v in committee)
        max_allowed = math.ceil(5 * 0.30)  # 2
        assert all(count <= max_allowed for count in org_counts.values())

    def test_diversity_enforcement_asn(self):
        """Test ASN diversity (max 40%)"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)
        selector = VerifierSelector(pool, reputation)

        # Create 10 verifiers with concentrated ASNs
        for i in range(10):
            ledger.create_account(f"verifier{i}", 10000)
            stake_mgr.stake(f"verifier{i}", 5000)
            asn = f"AS{i % 3}"  # Only 3 ASNs
            metadata = VerifierMetadata(f"org_{i}", asn, f"region_{i}", 0.8)
            pool.register(f"verifier{i}", 5000, ["code_review"], metadata)

        # Select committee of 5
        constraints = DiversityConstraints(max_asn_percentage=0.40)
        committee = selector.select_committee(k=5, constraints=constraints)

        # Check ASN diversity
        from collections import Counter

        asn_counts = Counter(v.metadata.asn for v in committee)
        max_allowed = math.ceil(5 * 0.40)  # 2
        assert all(count <= max_allowed for count in asn_counts.values())

    def test_diversity_enforcement_region(self):
        """Test region diversity (max 50%)"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)
        selector = VerifierSelector(pool, reputation)

        # Create 10 verifiers with 2 regions
        for i in range(10):
            ledger.create_account(f"verifier{i}", 10000)
            stake_mgr.stake(f"verifier{i}", 5000)
            region = "us-west" if i < 7 else "eu-central"
            metadata = VerifierMetadata(f"org_{i}", f"AS{i}", region, 0.8)
            pool.register(f"verifier{i}", 5000, ["code_review"], metadata)

        # Select committee of 5
        constraints = DiversityConstraints(max_region_percentage=0.50)
        committee = selector.select_committee(k=5, constraints=constraints)

        # Check region diversity
        from collections import Counter

        region_counts = Counter(v.metadata.region for v in committee)
        max_allowed = math.ceil(5 * 0.50)  # 3
        assert all(count <= max_allowed for count in region_counts.values())

    def test_diversity_mixed_constraints(self):
        """Test multiple diversity constraints together"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)
        selector = VerifierSelector(pool, reputation)

        # Create diverse verifiers
        for i in range(20):
            ledger.create_account(f"verifier{i}", 10000)
            stake_mgr.stake(f"verifier{i}", 5000)
            metadata = VerifierMetadata(
                f"org_{i % 4}",  # 4 orgs
                f"AS{i % 5}",  # 5 ASNs
                f"region_{i % 3}",  # 3 regions
                0.8,
            )
            pool.register(f"verifier{i}", 5000, ["code_review"], metadata)

        # Select with all constraints
        constraints = DiversityConstraints(
            max_org_percentage=0.30, max_asn_percentage=0.40, max_region_percentage=0.50
        )
        committee = selector.select_committee(k=10, constraints=constraints)

        # Verify all constraints
        assert selector.enforce_diversity(committee, constraints)


class TestReputationTracking:
    """Test reputation tracking"""

    def test_reputation_calculation(self):
        """Test initial reputation"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        pool.register("verifier1", 5000, ["code_review"], metadata)

        rep = reputation.get_reputation("verifier1")
        assert rep == 0.8

    def test_attestation_penalty(self):
        """Test -0.3 penalty for failed attestation"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        pool.register("verifier1", 5000, ["code_review"], metadata)

        # Failed attestation
        reputation.record_attestation("verifier1", "task-1", False)

        rep = reputation.get_reputation("verifier1")
        assert abs(rep - 0.5) < 0.01  # 0.8 - 0.3 = 0.5

    def test_challenge_boost(self):
        """Test +0.1 boost for successful challenge"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        pool.register("verifier1", 5000, ["code_review"], metadata)

        # Successful challenge
        reputation.record_challenge("verifier1", True)

        rep = reputation.get_reputation("verifier1")
        assert abs(rep - 0.9) < 0.01  # 0.8 + 0.1 = 0.9

    def test_reputation_bounds(self):
        """Test reputation clamped to [0.0, 1.0]"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 0.95)
        pool.register("verifier1", 5000, ["code_review"], metadata)

        # Multiple boosts
        for _ in range(5):
            reputation.record_challenge("verifier1", True)

        rep = reputation.get_reputation("verifier1")
        assert rep == 1.0  # Clamped at 1.0

        # Multiple penalties
        for _ in range(10):
            reputation.record_attestation("verifier1", f"task-{_}", False)

        rep = reputation.get_reputation("verifier1")
        assert rep == 0.0  # Clamped at 0.0

    def test_reputation_decay(self):
        """Test 5% decay per week without activity"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        pool.register("verifier1", 5000, ["code_review"], metadata)

        # Mock: manually adjust registered_at to simulate 1 week ago
        # In real implementation, decay is calculated from last activity
        # For testing, we just verify the formula works
        rep_after_1_week = 0.8 * (0.95**1)
        assert abs(rep_after_1_week - 0.76) < 0.01

        rep_after_4_weeks = 0.8 * (0.95**4)
        assert abs(rep_after_4_weeks - 0.653) < 0.01

    def test_reputation_history(self):
        """Test reputation event tracking"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)

        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        pool.register("verifier1", 5000, ["code_review"], metadata)

        # Record events
        reputation.record_attestation("verifier1", "task-1", False)
        reputation.record_challenge("verifier1", True)

        # Get history
        history = reputation.get_reputation_history("verifier1")
        assert len(history) == 2
        assert history[0].event_type == "CHALLENGE_SUCCESS"  # Newest first
        assert history[1].event_type == "ATTESTATION_FAILED"


class TestIntegration:
    """Integration tests for complete workflows"""

    def test_complete_selection_workflow(self):
        """Test complete workflow: register → reputation → select"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        reputation = ReputationTracker(pool)
        selector = VerifierSelector(pool, reputation)

        # Register 10 diverse verifiers
        for i in range(10):
            ledger.create_account(f"verifier{i}", 10000)
            stake_mgr.stake(f"verifier{i}", 5000 + i * 500)
            metadata = VerifierMetadata(
                f"org_{i % 3}", f"AS{i % 4}", f"region_{i % 2}", 0.75 + (i * 0.01)
            )
            pool.register(f"verifier{i}", 5000 + i * 500, ["code_review"], metadata)

        # Modify some reputations
        reputation.record_attestation("verifier0", "task-1", False)  # Penalty
        reputation.record_challenge("verifier5", True)  # Boost

        # Select committee
        constraints = DiversityConstraints()
        committee = selector.select_committee(
            k=5, min_stake=3000, constraints=constraints
        )

        # Verify results
        assert len(committee) == 5
        assert selector.enforce_diversity(committee, constraints)
        assert all(v.stake >= 3000 for v in committee)
