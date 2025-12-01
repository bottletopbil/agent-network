"""
Core functionality unit tests for the CAN Swarm project.

Tests cover:
- Cryptographic signing and verification
- Lamport clock ordering
- Envelope creation
- Policy validation
"""

import sys, os, json, base64, tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from nacl.signing import SigningKey


@pytest.fixture(scope="session", autouse=True)
def setup_test_crypto_keys():
    """Generate and set test crypto keys for all tests."""
    # Generate a test signing key
    sk = SigningKey.generate()
    vk = sk.verify_key

    # Set environment variables
    os.environ["SWARM_SIGNING_SK_B64"] = base64.b64encode(bytes(sk)).decode()
    os.environ["SWARM_VERIFY_PK_B64"] = base64.b64encode(bytes(vk)).decode()

    yield

    # Cleanup (optional)
    os.environ.pop("SWARM_SIGNING_SK_B64", None)
    os.environ.pop("SWARM_VERIFY_PK_B64", None)


# Now import after setting up environment
from crypto import sign_record, verify_record, cjson
from lamport import Lamport
from envelope import make_envelope, sign_envelope, verify_envelope
from policy import validate_envelope, PolicyError, current_policy_hash


class TestCryptoSigningVerification:
    """Test cryptographic signing and tampering detection."""

    def test_sign_verify_record(self):
        """Test that sign_record creates valid signatures."""
        record = {"id": "test-123", "data": "hello", "value": 42}
        signed = sign_record(record)

        # Should have signature fields
        assert "sig_pk_b64" in signed
        assert "sig_b64" in signed

        # Original fields should be preserved
        assert signed["id"] == "test-123"
        assert signed["data"] == "hello"
        assert signed["value"] == 42

        # Verification should pass
        assert verify_record(signed) is True

    def test_verify_rejects_tampered_data(self):
        """Test that verify_record rejects tampered data."""
        record = {"id": "test-456", "message": "original"}
        signed = sign_record(record)

        # Tamper with the data
        signed["message"] = "tampered"

        # Verification should fail
        assert verify_record(signed) is False

    def test_verify_rejects_tampered_signature(self):
        """Test that verify_record rejects tampered signatures."""
        record = {"id": "test-789", "data": "authentic"}
        signed = sign_record(record)

        # Tamper with the signature
        sig_bytes = base64.b64decode(signed["sig_b64"])
        # Flip a bit
        tampered = bytearray(sig_bytes)
        tampered[0] ^= 0x01
        signed["sig_b64"] = base64.b64encode(bytes(tampered)).decode()

        # Verification should fail
        assert verify_record(signed) is False

    def test_verify_rejects_missing_signature(self):
        """Test that verify_record rejects records without signatures."""
        record = {"id": "test-no-sig", "data": "unsigned"}

        # Should fail verification (no sig fields)
        assert verify_record(record) is False


class TestLamportOrdering:
    """Test Lamport clock tick and observe operations."""

    def test_lamport_tick_increments(self):
        """Test that tick() increments the clock."""
        # Use a temporary file for this test
        with tempfile.TemporaryDirectory() as tmpdir:
            clock_file = Path(tmpdir) / "test_clock.json"
            clock = Lamport(clock_file)

            initial = clock.value()
            t1 = clock.tick()
            t2 = clock.tick()
            t3 = clock.tick()

            assert t1 == initial + 1
            assert t2 == initial + 2
            assert t3 == initial + 3

    def test_lamport_observe_updates_to_higher(self):
        """Test that observe() updates to higher values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            clock_file = Path(tmpdir) / "test_clock2.json"
            clock = Lamport(clock_file)

            # Start at some value
            clock.tick()
            clock.tick()
            current = clock.value()

            # Observe a higher value
            higher = current + 100
            result = clock.observe(higher)

            # Should jump to higher + 1
            assert result == higher + 1
            assert clock.value() == higher + 1

    def test_lamport_observe_doesnt_go_backward(self):
        """Test that observe() doesn't go backward for lower values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            clock_file = Path(tmpdir) / "test_clock3.json"
            clock = Lamport(clock_file)

            # Get to a high value
            for _ in range(10):
                clock.tick()
            current = clock.value()

            # Try to observe a lower value
            lower = 5
            result = clock.observe(lower)

            # Should stay at current + 1 (not go backward)
            assert result == current + 1
            assert clock.value() == current + 1


class TestEnvelopeCreation:
    """Test envelope creation and structure."""

    def test_make_envelope_structure(self):
        """Test that make_envelope creates valid structure."""
        env = make_envelope(
            kind="NEED",
            thread_id="test-thread-123",
            sender_pk_b64="dGVzdC1wdWJsaWMta2V5",
            payload={"task": "test"},
        )

        # Check all required fields exist
        assert "v" in env
        assert "id" in env
        assert "thread_id" in env
        assert "kind" in env
        assert "lamport" in env
        assert "ts_ns" in env
        assert "sender_pk_b64" in env
        assert "payload_hash" in env
        assert "payload" in env
        assert "policy_engine_hash" in env
        assert "nonce" in env

        # Check field values
        assert env["v"] == 1
        assert env["kind"] == "NEED"
        assert env["thread_id"] == "test-thread-123"
        assert env["payload"]["task"] == "test"

    def test_envelope_policy_hash_default(self):
        """Test that envelope uses current_policy_hash by default."""
        env = make_envelope(
            kind="PLAN",
            thread_id="test-thread-456",
            sender_pk_b64="dGVzdC1wdWJsaWMta2V5Mg==",
            payload={"plan": "data"},
        )

        # Should use current policy hash
        expected_hash = current_policy_hash()
        assert env["policy_engine_hash"] == expected_hash

    def test_envelope_payload_hash_calculated(self):
        """Test that payload hash is correctly calculated."""
        payload = {"data": "test", "value": 123}
        env = make_envelope(
            kind="COMMIT",
            thread_id="test-thread-789",
            sender_pk_b64="dGVzdC1wdWJsaWMta2V5Mw==",
            payload=payload,
        )

        # Calculate expected hash
        from hashlib import sha256

        expected_hash = sha256(cjson(payload)).hexdigest()

        assert env["payload_hash"] == expected_hash


class TestPolicyValidation:
    """Test policy validation for various scenarios."""

    def test_valid_envelope_passes(self):
        """Test that a valid envelope passes validation."""
        # Create a proper signed envelope
        env = make_envelope(
            kind="NEED",
            thread_id="test-valid",
            sender_pk_b64="dGVzdC1wdWJsaWMta2V5",
            payload={"test": "data"},
        )
        signed_env = sign_envelope(env)

        # Should not raise
        validate_envelope(signed_env)

    def test_invalid_signature_fails(self):
        """Test that invalid signature fails validation."""
        env = make_envelope(
            kind="PLAN",
            thread_id="test-bad-sig",
            sender_pk_b64="dGVzdC1wdWJsaWMta2V5",
            payload={"test": "data"},
        )
        signed_env = sign_envelope(env)

        # Tamper with the data
        signed_env["payload"]["test"] = "tampered"

        # Should raise PolicyError
        with pytest.raises(PolicyError, match="signature or payload_hash invalid"):
            validate_envelope(signed_env)

    def test_wrong_policy_hash_fails(self):
        """Test that wrong policy hash fails validation."""
        env = make_envelope(
            kind="COMMIT",
            thread_id="test-bad-policy",
            sender_pk_b64="dGVzdC1wdWJsaWMta2V5",
            payload={"test": "data"},
            policy_engine_hash="wrong-hash-12345",
        )
        signed_env = sign_envelope(env)

        # Should raise PolicyError
        with pytest.raises(PolicyError, match="policy_engine_hash mismatch"):
            validate_envelope(signed_env)

    def test_disallowed_kind_fails(self):
        """Test that disallowed message kind fails validation."""
        env = make_envelope(
            kind="INVALID_KIND",
            thread_id="test-bad-kind",
            sender_pk_b64="dGVzdC1wdWJsaWMta2V5",
            payload={"test": "data"},
        )
        signed_env = sign_envelope(env)

        # Should raise PolicyError
        with pytest.raises(PolicyError, match="kind not allowed"):
            validate_envelope(signed_env)

    def test_oversized_payload_fails(self):
        """Test that oversized payload fails validation."""
        # Create a payload larger than 64KB
        large_payload = {"data": "x" * 70000}

        env = make_envelope(
            kind="NEED",
            thread_id="test-oversized",
            sender_pk_b64="dGVzdC1wdWJsaWMta2V5",
            payload=large_payload,
        )
        signed_env = sign_envelope(env)

        # Should raise PolicyError
        with pytest.raises(PolicyError, match="payload too large"):
            validate_envelope(signed_env)
