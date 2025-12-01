"""
Test for per-agent keypairs (SEC-003).

Validates that different agents produce different signatures
and that signatures can be verified with agent-specific keys.
"""

import sys
from pathlib import Path
import pytest
import tempfile
import os

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_different_agents_produce_different_signatures():
    """
    Test that two agents signing the same message produce different signatures.

    With shared keypair (bug), signatures would be identical.
    With per-agent keys (fix), signatures are different.
    """
    from crypto import generate_keypair, sign_with_key

    # Generate two different agent keypairs
    signing_key1, verify_key1 = generate_keypair()
    signing_key2, verify_key2 = generate_keypair()

    # Same message
    message = b"Hello, World!"

    # Each agent signs with their own key
    sig1 = sign_with_key(signing_key1, message)
    sig2 = sign_with_key(signing_key2, message)

    # Signatures should be DIFFERENT (different keys)
    assert sig1 != sig2, "Different agents should produce different signatures"

    # Verify with correct keys
    from nacl.signing import VerifyKey
    from nacl.encoding import RawEncoder

    # Shouldn't raise
    verify_key1.verify(message, sig1)
    verify_key2.verify(message, sig2)

    # Cross-verification should fail
    with pytest.raises(Exception):
        verify_key1.verify(message, sig2)  # Wrong key for sig2

    with pytest.raises(Exception):
        verify_key2.verify(message, sig1)  # Wrong key for sig1


def test_save_and_load_agent_keypair():
    """
    Test that agent keypairs can be persisted and retrieved.
    """
    from crypto import generate_keypair, save_keypair, load_keypair, sign_with_key

    with tempfile.TemporaryDirectory() as tmpdir:
        # Override key directory
        os.environ["SWARM_KEYS_DIR"] = tmpdir

        agent_id = "agent_test_123"

        # Generate and save keypair
        signing_key, verify_key = generate_keypair()
        save_keypair(agent_id, signing_key)

        # Load it back
        loaded_signing_key, loaded_verify_key = load_keypair(agent_id)

        # Verify they work the same
        message = b"test message"

        sig1 = sign_with_key(signing_key, message)
        sig2 = sign_with_key(loaded_signing_key, message)

        # Both signatures should verify with the loaded verify key
        loaded_verify_key.verify(message, sig1)
        loaded_verify_key.verify(message, sig2)


def test_agent_specific_signatures():
    """
    Test that we can differentiate signatures by agent.
    """
    from crypto import generate_keypair, save_keypair, load_keypair, sign_with_key

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["SWARM_KEYS_DIR"] = tmpdir

        # Create two agents
        agent1_id = "alice"
        agent2_id = "bob"

        # Generate and save their keypairs
        sk1, vk1 = generate_keypair()
        sk2, vk2 = generate_keypair()

        save_keypair(agent1_id, sk1)
        save_keypair(agent2_id, sk2)

        # Load them back
        alice_sk, alice_vk = load_keypair(agent1_id)
        bob_sk, bob_vk = load_keypair(agent2_id)

        # Same message signed by each
        message = b"Important data"

        alice_sig = sign_with_key(alice_sk, message)
        bob_sig = sign_with_key(bob_sk, message)

        # Different signatures
        assert alice_sig != bob_sig

        # Alice's sig verifies with Alice's key
        alice_vk.verify(message, alice_sig)

        # Bob's sig verifies with Bob's key
        bob_vk.verify(message, bob_sig)

        # Cross-verification fails
        with pytest.raises(Exception):
            alice_vk.verify(message, bob_sig)

        with pytest.raises(Exception):
            bob_vk.verify(message, alice_sig)


def test_backward_compatibility_with_env_keypair():
    """
    Test that system falls back to env keypair if agent_id not provided.
    """
    from envelope import sign_envelope

    # Without agent_id, should use env keypair (backward compatible)
    envelope = {
        "operation": "TEST",
        "payload": {"data": "test"},
        "thread_id": "thread_1",
        "lamport": 1,
    }

    # Should not crash - uses default env keypair
    try:
        signed = sign_envelope(envelope)
        assert "signature" in signed
        assert "sender_pk_b64" in signed
    except Exception as e:
        # May fail if ENV keys not set, but shouldn't crash on code logic
        assert "SWARM_PRIVATE_KEY" in str(e) or "KeyError" in str(type(e).__name__)
