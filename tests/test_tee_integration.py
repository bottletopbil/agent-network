"""
Integration test to verify TEE weight boost in committee selection.

This test demonstrates that TEE-verified verifiers receive a 2x weight
multiplier in the committee selection algorithm.
"""

import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from economics.ledger import CreditLedger
from economics.stake import StakeManager
from economics.pools import VerifierPool, VerifierMetadata
from economics.selection import VerifierSelector
from economics.reputation import ReputationTracker


def test_tee_verifier_weight_boost():
    """Test that TEE-verified verifiers get 2x weight in selection."""
    
    # Setup test database
    db_path = Path(tempfile.mktemp())
    
    try:
        # Initialize components
        ledger = CreditLedger(db_path)
        stake_manager = StakeManager(ledger)
        pool = VerifierPool(stake_manager)
        reputation_tracker = ReputationTracker(pool)
        selector = VerifierSelector(pool, reputation_tracker)
        
        # Register two identical verifiers except for TEE status
        # Both have same stake, reputation, and registration time
        stake_amount = 10000
        
        # Verifier 1: No TEE
        ledger.create_account("verifier_no_tee", 20000)
        stake_manager.stake("verifier_no_tee", stake_amount)
        pool.register(
            "verifier_no_tee",
            stake_amount,
            ["testing"],
            VerifierMetadata(
                org_id="org1",
                asn="AS1234",
                region="us-west",
                reputation=0.9,
                tee_verified=False
            )
        )
        
        # Verifier 2: TEE verified
        ledger.create_account("verifier_tee", 20000)
        stake_manager.stake("verifier_tee", stake_amount)
        pool.register(
            "verifier_tee",
            stake_amount,
            ["testing"],
            VerifierMetadata(
                org_id="org2",
                asn="AS5678",
                region="us-east",
                reputation=0.9,
                tee_verified=True
            )
        )
        
        # Get verifier records
        verifier_no_tee = pool.get_verifier("verifier_no_tee")
        verifier_tee = pool.get_verifier("verifier_tee")
        
        # Calculate weights
        weight_no_tee = selector.calculate_weight(verifier_no_tee)
        weight_tee = selector.calculate_weight(verifier_tee)
        
        # TEE verifier should have exactly 2x the weight (allow floating point tolerance)
        print(f"Weight (no TEE): {weight_no_tee}")
        print(f"Weight (TEE): {weight_tee}")
        print(f"Ratio: {weight_tee / weight_no_tee}")
        
        # Allow for floating-point precision (within 0.001%)
        assert abs(weight_tee - (weight_no_tee * 2.0)) < 0.001, \
            f"TEE weight should be 2x: expected {weight_no_tee * 2.0}, got {weight_tee}"
        
        print("✓ TEE verifiers receive 2x weight boost as expected")
        
    finally:
        # Cleanup
        os.unlink(db_path)


if __name__ == "__main__":
    test_tee_verifier_weight_boost()
    print("\n✅ All TEE integration tests passed!")
