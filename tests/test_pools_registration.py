"""
Unit tests for Verifier Pool Registration.

Tests pool registration, deregistration, and stake-based filtering.
"""

import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from economics.ledger import CreditLedger
from economics.stake import StakeManager
from economics.pools import VerifierPool, VerifierMetadata, VerifierRecord


class TestPoolRegistration:
    """Test verifier pool registration"""
    
    def test_pool_registration(self):
        """Test basic pool registration"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        # Create account and stake
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        
        # Register in pool
        metadata = VerifierMetadata(
            org_id="org_a",
            asn="AS64512",
            region="us-west",
            reputation=0.95
        )
        pool.register("verifier1", 5000, ["code_review"], metadata)
        
        # Verify registered
        verifier = pool.get_verifier("verifier1")
        assert verifier is not None
        assert verifier.verifier_id == "verifier1"
        assert verifier.stake == 5000
        assert verifier.capabilities == ["code_review"]
        assert verifier.metadata.org_id == "org_a"
        assert verifier.active is True
    
    def test_registration_with_metadata(self):
        """Test registration with full metadata"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 3000)
        
        metadata = VerifierMetadata(
            org_id="org_b",
            asn="AS64513",
            region="eu-central",
            reputation=0.85
        )
        pool.register("verifier1", 3000, ["testing", "deployment"], metadata)
        
        verifier = pool.get_verifier("verifier1")
        assert verifier.metadata.org_id == "org_b"
        assert verifier.metadata.asn == "AS64513"
        assert verifier.metadata.region == "eu-central"
        assert verifier.metadata.reputation == 0.85
        assert "testing" in verifier.capabilities
        assert "deployment" in verifier.capabilities
    
    def test_reregistration(self):
        """Test re-registering updates existing verifier"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        
        # Initial registration
        metadata1 = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        pool.register("verifier1", 5000, ["code_review"], metadata1)
        
        # Re-register with updated capabilities
        metadata2 = VerifierMetadata("org_a", "AS1", "us-west", 0.9)
        pool.register("verifier1", 5000, ["code_review", "testing"], metadata2)
        
        # Should update, not create duplicate
        verifier = pool.get_verifier("verifier1")
        assert len(verifier.capabilities) == 2
        assert verifier.metadata.reputation == 0.9
    
    def test_registration_validates_stake(self):
        """Test registration validates verifier has sufficient stake"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 2000)
        
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        
        # Try to register with claimed stake > actual
        with pytest.raises(ValueError, match="stake mismatch"):
            pool.register("verifier1", 5000, ["code_review"], metadata)


class TestPoolDeregistration:
    """Test verifier pool deregistration"""
    
    def test_pool_deregistration(self):
        """Test deregistering a verifier"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        pool.register("verifier1", 5000, ["code_review"], metadata)
        
        # Deregister
        pool.deregister("verifier1")
        
        # Should be inactive
        verifier = pool.get_verifier("verifier1")
        assert verifier.active is False
    
    def test_deregister_nonexistent(self):
        """Test deregistering nonexistent verifier raises error"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        with pytest.raises(ValueError, match="not found"):
            pool.deregister("nonexistent")
    
    def test_deregister_preserves_history(self):
        """Test deregistration preserves historical data"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        pool.register("verifier1", 5000, ["code_review"], metadata)
        
        # Deregister
        pool.deregister("verifier1")
        
        # Data still exists
        verifier = pool.get_verifier("verifier1")
        assert verifier is not None
        assert verifier.metadata.org_id == "org_a"
        
        # Can see in all members (not just active)
        all_members = pool.get_pool_members(active_only=False)
        assert len(all_members) == 1


class TestPoolQueries:
    """Test pool member queries"""
    
    def test_get_pool_members(self):
        """Test querying all pool members"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        # Register multiple verifiers
        for i in range(3):
            ledger.create_account(f"verifier{i}", 10000)
            stake_mgr.stake(f"verifier{i}", 5000)
            metadata = VerifierMetadata(f"org_{i}", f"AS{i}", "us-west", 0.8)
            pool.register(f"verifier{i}", 5000, ["code_review"], metadata)
        
        members = pool.get_pool_members()
        assert len(members) == 3
    
    def test_get_pool_members_active_only(self):
        """Test filtering by active status"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        # Register 3 verifiers
        for i in range(3):
            ledger.create_account(f"verifier{i}", 10000)
            stake_mgr.stake(f"verifier{i}", 5000)
            metadata = VerifierMetadata(f"org_{i}", f"AS{i}", "us-west", 0.8)
            pool.register(f"verifier{i}", 5000, ["code_review"], metadata)
        
        # Deregister one
        pool.deregister("verifier1")
        
        # Active only
        active = pool.get_pool_members(active_only=True)
        assert len(active) == 2
        
        # All members
        all_members = pool.get_pool_members(active_only=False)
        assert len(all_members) == 3
    
    def test_get_active_verifiers(self):
        """Test getting active verifiers with stake filtering"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        # Register verifiers with different stakes
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        metadata1 = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        pool.register("verifier1", 5000, ["code_review"], metadata1)
        
        ledger.create_account("verifier2", 10000)
        stake_mgr.stake("verifier2", 2000)
        metadata2 = VerifierMetadata("org_b", "AS2", "us-east", 0.9)
        pool.register("verifier2", 2000, ["testing"], metadata2)
        
        # Get active with min stake 3000
        active = pool.get_active_verifiers(min_stake=3000)
        assert len(active) == 1
        assert active[0].verifier_id == "verifier1"
        
        # Get active with min stake 1000
        active = pool.get_active_verifiers(min_stake=1000)
        assert len(active) == 2
    
    def test_get_verifier(self):
        """Test getting specific verifier"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        pool.register("verifier1", 5000, ["code_review"], metadata)
        
        verifier = pool.get_verifier("verifier1")
        assert verifier is not None
        assert verifier.verifier_id == "verifier1"
        
        # Nonexistent
        assert pool.get_verifier("nonexistent") is None


class TestStakeRequirements:
    """Test stake requirement enforcement"""
    
    def test_stake_requirement(self):
        """Test minimum stake requirement enforced"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        # Register verifiers
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        metadata1 = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        pool.register("verifier1", 5000, ["code_review"], metadata1)
        
        ledger.create_account("verifier2", 10000)
        stake_mgr.stake("verifier2", 1000)
        metadata2 = VerifierMetadata("org_b", "AS2", "us-east", 0.9)
        pool.register("verifier2", 1000, ["testing"], metadata2)
        
        # Minimum stake 2000
        active = pool.get_active_verifiers(min_stake=2000)
        assert len(active) == 1
        assert active[0].verifier_id == "verifier1"
    
    def test_stake_dropped_below_minimum(self):
        """Test verifiers filtered out when stake drops below minimum"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        # Register with 5000 stake
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        pool.register("verifier1", 5000, ["code_review"], metadata)
        
        # Initially qualifies
        active = pool.get_active_verifiers(min_stake=3000)
        assert len(active) == 1
        
        # Unstake some
        stake_mgr.unstake("verifier1", 3000)
        
        # Now has only 2000 staked, doesn't qualify
        active = pool.get_active_verifiers(min_stake=3000)
        assert len(active) == 0
    
    def test_update_capabilities(self):
        """Test updating verifier capabilities"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        pool.register("verifier1", 5000, ["code_review"], metadata)
        
        # Update capabilities
        pool.update_capabilities("verifier1", ["code_review", "testing", "deployment"])
        
        verifier = pool.get_verifier("verifier1")
        assert len(verifier.capabilities) == 3
        assert "deployment" in verifier.capabilities
    
    def test_update_reputation(self):
        """Test updating verifier reputation"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        pool.register("verifier1", 5000, ["code_review"], metadata)
        
        # Update reputation
        pool.update_reputation("verifier1", 0.95)
        
        verifier = pool.get_verifier("verifier1")
        assert verifier.metadata.reputation == 0.95
    
    def test_update_nonexistent_verifier(self):
        """Test updating nonexistent verifier raises error"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        with pytest.raises(ValueError, match="not found"):
            pool.update_capabilities("nonexistent", ["test"])
        
        with pytest.raises(ValueError, match="not found"):
            pool.update_reputation("nonexistent", 0.5)
    
    def test_invalid_reputation(self):
        """Test invalid reputation values rejected"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 5000)
        
        # Invalid at registration
        metadata = VerifierMetadata("org_a", "AS1", "us-west", 1.5)
        with pytest.raises(ValueError, match="Reputation must be 0.0-1.0"):
            pool.register("verifier1", 5000, ["code_review"], metadata)
        
        # Valid registration
        metadata_valid = VerifierMetadata("org_a", "AS1", "us-west", 0.8)
        pool.register("verifier1", 5000, ["code_review"], metadata_valid)
        
        # Invalid at update
        with pytest.raises(ValueError, match="Reputation must be 0.0-1.0"):
            pool.update_reputation("verifier1", -0.5)


class TestIntegration:
    """Integration tests for complete workflows"""
    
    def test_complete_verifier_lifecycle(self):
        """Test complete lifecycle: register → query → update → deregister"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        stake_mgr = StakeManager(ledger)
        pool = VerifierPool(stake_mgr)
        
        # Setup
        ledger.create_account("verifier1", 10000)
        stake_mgr.stake("verifier1", 6000)
        
        # Register
        metadata = VerifierMetadata("org_a", "AS64512", "us-west", 0.90)
        pool.register("verifier1", 6000, ["code_review"], metadata)
        
        # Verify in pool
        active = pool.get_active_verifiers(min_stake=5000)
        assert len(active) == 1
        
        # Update capabilities
        pool.update_capabilities("verifier1", ["code_review", "testing"])
        
        # Update reputation
        pool.update_reputation("verifier1", 0.95)
        
        # Verify updates
        verifier = pool.get_verifier("verifier1")
        assert len(verifier.capabilities) == 2
        assert verifier.metadata.reputation == 0.95
        
        # Deregister
        pool.deregister("verifier1")
        
        # No longer active
        active = pool.get_active_verifiers()
        assert len(active) == 0
        
        # But history preserved
        all_members = pool.get_pool_members(active_only=False)
        assert len(all_members) == 1
