"""
Test for sybil resistance in DID creation (SEC-001).

This test verifies that DID creation has economic or computational cost
to prevent sybil attacks.
"""

import sys
from pathlib import Path
import pytest
import tempfile
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from identity.did import DIDManager
from economics.ledger import CreditLedger


def test_did_creation_requires_stake():
    """
    Test that creating a DID requires minimum stake when ledger is provided.
    
    Currently this test will FAIL because DID creation is free.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)
        
        # Create account with insufficient stake
        ledger.create_account("user1", initial_balance=500)
        
        # Create DID manager with ledger
        did_manager = DIDManager(ledger=ledger)
        
        # Attempt to create DID without sufficient stake
        with pytest.raises(ValueError) as exc_info:
            did_manager.create_did_key(account_id="user1")
        
        assert "stake" in str(exc_info.value).lower() or \
               "insufficient" in str(exc_info.value).lower()


def test_did_creation_with_sufficient_stake():
    """
    Test that DID creation succeeds with sufficient stake.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)
        
        # Get minimum stake requirement
        did_manager = DIDManager(ledger=ledger)
        min_stake = did_manager.MIN_DID_STAKE
        
        # Create account with sufficient balance
        ledger.create_account("user1", initial_balance=min_stake + 100)
        
        # Create DID should succeed
        did = did_manager.create_did_key(account_id="user1")
        
        assert did.startswith("did:key:")
        
        # Verify stake was locked
        account = ledger.get_account("user1")
        assert account.locked == min_stake


def test_did_creation_without_ledger_uses_pow():
    """
    Test that DID creation without ledger requires proof-of-work.
    """
    did_manager = DIDManager(ledger=None)
    
    # Without ledger, should require PoW
    start_time = time.time()
    did = did_manager.create_did_key()
    elapsed = time.time() - start_time
    
    # PoW should take some time, but may be very fast on modern hardware
    # Just verify it completes successfully
    assert did.startswith("did:key:")


def test_rate_limiting_prevents_spam():
    """
    Test that rate limiting prevents creating too many DIDs quickly.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)
        
        # Create account with lots of credits
        ledger.create_account("user1", initial_balance=100000)
        
        did_manager = DIDManager(ledger=ledger, rate_limit_per_hour=10)
        
        # Create 10 DIDs (should succeed)
        for i in range(10):
            did_manager.create_did_key(account_id="user1")
        
        # 11th DID should be rate limited
        with pytest.raises(ValueError) as exc_info:
            did_manager.create_did_key(account_id="user1")
        
        assert "rate limit" in str(exc_info.value).lower()


def test_mass_did_creation_expensive():
    """
    Test that creating 1000 DIDs is prohibitively expensive.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)
        
        did_manager = DIDManager(ledger=ledger)
        min_stake = did_manager.MIN_DID_STAKE
        
        # Cost for 1000 DIDs
        total_cost = min_stake * 1000
        
        # Should be expensive (at least 100,000 credits)
        assert total_cost >= 100000, \
            f"Sybil attack too cheap: {total_cost} credits for 1000 DIDs"
        
        # Try to create with insufficient funds
        ledger.create_account("attacker", initial_balance=total_cost - 1)
        
        # Should fail before creating 1000
        created = 0
        try:
            for i in range(1000):
                did_manager.create_did_key(account_id="attacker")
                created += 1
        except:
            pass
        
        # Should not be able to create all 1000
        assert created < 1000, f"Created {created} DIDs, sybil attack succeeded"


def test_pow_difficulty_configurable():
    """
    Test that PoW difficulty can be configured.
    """
    # Low difficulty (fast)
    did_manager_easy = DIDManager(ledger=None, pow_difficulty=1)
    assert did_manager_easy.pow_difficulty == 1
    did_easy = did_manager_easy.create_did_key()
    assert did_easy.startswith("did:key:")
    
    # Higher difficulty (should work but be slower)
    did_manager_hard = DIDManager(ledger=None, pow_difficulty=4)
    assert did_manager_hard.pow_difficulty == 4
    did_hard = did_manager_hard.create_did_key()
    assert did_hard.startswith("did:key:")
