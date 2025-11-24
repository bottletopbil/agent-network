#!/usr/bin/env python3
"""
Minimal test to verify Phase 1 fixes work correctly.
Tests that:
1. current_policy_hash() is callable from envelope.py
2. make_envelope uses the correct policy hash by default
3. New verbs are allowed in policy validation
"""

import sys
sys.path.append("src")

from policy import current_policy_hash, ALLOWED_KINDS, validate_envelope, PolicyError

def test_policy_hash():
    """Test that the policy hash is correctly calculated."""
    policy_hash = current_policy_hash()
    print(f"✓ Policy hash calculated: {policy_hash[:16]}...")
    assert isinstance(policy_hash, str)
    assert len(policy_hash) == 64  # SHA-256 hex digest
    return policy_hash

def test_allowed_verbs():
    """Test that all required verbs are in ALLOWED_KINDS."""
    required_verbs = {"NEED", "PLAN", "COMMIT", "ATTEST", "FINAL", 
                      "DECIDE", "PROPOSE", "CLAIM", "YIELD", "RELEASE"}
    print(f"✓ Checking allowed kinds: {ALLOWED_KINDS}")
    assert required_verbs.issubset(ALLOWED_KINDS), \
        f"Missing verbs: {required_verbs - ALLOWED_KINDS}"
    print(f"✓ All required verbs present")

def test_envelope_default_policy():
    """Test that make_envelope uses current_policy_hash() by default."""
    from envelope import make_envelope
    
    # Create envelope without specifying policy_engine_hash
    env = make_envelope(
        kind="NEED",
        thread_id="test-thread",
        sender_pk_b64="dGVzdC1wdWJsaWMta2V5",  # base64 "test-public-key"
        payload={"test": "data"}
    )
    
    expected_hash = current_policy_hash()
    actual_hash = env.get("policy_engine_hash")
    
    print(f"✓ Envelope policy hash: {actual_hash[:16]}...")
    assert actual_hash == expected_hash, \
        f"Policy hash mismatch! Expected {expected_hash}, got {actual_hash}"
    print(f"✓ Envelope uses correct policy hash by default")
    
    return env

def main():
    print("=" * 60)
    print("Phase 1 Verification Tests")
    print("=" * 60)
    
    try:
        # Test 1: Policy hash calculation
        print("\n[Test 1] Policy hash calculation")
        policy_hash = test_policy_hash()
        
        # Test 2: Allowed verbs
        print("\n[Test 2] Allowed verbs in policy")
        test_allowed_verbs()
        
        # Test 3: Envelope default policy
        print("\n[Test 3] Envelope default policy hash")
        envelope = test_envelope_default_policy()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nPhase 1 fixes verified:")
        print(f"  • Policy hash dynamically calculated: {policy_hash[:16]}...")
        print(f"  • New verbs added: DECIDE, PROPOSE, CLAIM, YIELD, RELEASE")
        print(f"  • Envelope uses current_policy_hash() by default")
        print(f"  • No circular import issues")
        
    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ TEST FAILED")
        print("=" * 60)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
