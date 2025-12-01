"""Tests for TEE attestation (mock implementation)."""

import sys
import os
import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from identity.attestation import AttestationReport, TEEVerifier


class TestAttestationReport:
    """Test attestation report dataclass."""

    def test_create_report(self):
        """Test creating attestation report."""
        report = AttestationReport(
            quote="abc123",
            mrenclave="enclave_hash",
            mrsigner="signer_hash",
            report_data="test_data",
            timestamp_ns=12345,
        )

        assert report.quote == "abc123"
        assert report.mrenclave == "enclave_hash"
        assert report.platform == "mock-sgx"

    def test_report_to_dict(self):
        """Test report serialization."""
        report = AttestationReport(
            quote="quote123", mrenclave="mr1", mrsigner="mr2", report_data="data"
        )

        report_dict = report.to_dict()

        assert isinstance(report_dict, dict)
        assert report_dict["quote"] == "quote123"
        assert "platform" in report_dict

    def test_report_from_dict(self):
        """Test report deserialization."""
        data = {
            "quote": "q456",
            "mrenclave": "mr_enc",
            "mrsigner": "mr_sign",
            "report_data": "custom_data",
            "timestamp_ns": 0,
            "platform": "mock-sgx",
        }

        report = AttestationReport.from_dict(data)

        assert report.quote == "q456"
        assert report.mrenclave == "mr_enc"


class TestTEEVerifier:
    """Test TEE verifier operations."""

    def test_create_verifier(self):
        """Test creating TEE verifier."""
        verifier = TEEVerifier(mock_mode=True)

        assert verifier is not None
        assert verifier.mock_mode is True
        assert verifier.mock_mrenclave is not None

    def test_generate_quote(self):
        """Test generating attestation quote."""
        verifier = TEEVerifier()

        report = verifier.generate_quote("test_report_data")

        assert report is not None
        assert report.report_data == "test_report_data"
        assert len(report.quote) == 64  # SHA256 hex
        assert report.mrenclave == verifier.mock_mrenclave

    def test_generate_quote_with_did(self):
        """Test generating quote with DID as report data."""
        verifier = TEEVerifier()

        agent_did = "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"
        report = verifier.generate_quote(agent_did)

        assert report is not None
        assert report.report_data == agent_did

    def test_verify_valid_quote(self):
        """Test verifying valid quote."""
        verifier = TEEVerifier()

        # Generate quote
        report = verifier.generate_quote("test_data")

        # Verify it
        is_valid = verifier.verify_quote(report)

        assert is_valid is True

    def test_verify_untrusted_enclave(self):
        """Test verifying quote from untrusted enclave."""
        verifier = TEEVerifier()

        # Create report with unknown MRENCLAVE
        report = AttestationReport(
            quote="a" * 64,
            mrenclave="unknown_enclave_hash",
            mrsigner="unknown_signer",
            report_data="data",
        )

        is_valid = verifier.verify_quote(report)

        assert is_valid is False

    def test_verify_invalid_platform(self):
        """Test verifying quote from unsupported platform."""
        verifier = TEEVerifier()

        report = AttestationReport(
            quote="a" * 64,
            mrenclave=verifier.mock_mrenclave,
            mrsigner=verifier.mock_mrsigner,
            report_data="data",
            platform="real-sgx",  # Different platform
        )

        is_valid = verifier.verify_quote(report)

        assert is_valid is False

    def test_verify_invalid_quote_format(self):
        """Test verifying quote with invalid format."""
        verifier = TEEVerifier()

        report = AttestationReport(
            quote="short",  # Invalid length
            mrenclave=verifier.mock_mrenclave,
            mrsigner=verifier.mock_mrsigner,
            report_data="data",
        )

        is_valid = verifier.verify_quote(report)

        assert is_valid is False

    def test_check_mrenclave_match(self):
        """Test checking MRENCLAVE matches."""
        verifier = TEEVerifier()

        report = verifier.generate_quote("data")

        matches = verifier.check_mrenclave(report, verifier.mock_mrenclave)

        assert matches is True

    def test_check_mrenclave_mismatch(self):
        """Test checking MRENCLAVE doesn't match."""
        verifier = TEEVerifier()

        report = verifier.generate_quote("data")

        matches = verifier.check_mrenclave(report, "different_mrenclave")

        assert matches is False

    def test_register_trusted_enclave(self):
        """Test registering trusted enclave."""
        verifier = TEEVerifier()

        success = verifier.register_trusted_enclave(
            mrenclave="new_enclave_hash", name="test-enclave", version="2.0"
        )

        assert success is True

        # Should now be trusted
        info = verifier.get_enclave_info("new_enclave_hash")
        assert info is not None
        assert info["name"] == "test-enclave"
        assert info["trusted"] is True

    def test_revoke_enclave(self):
        """Test revoking enclave trust."""
        verifier = TEEVerifier()

        # Register enclave
        verifier.register_trusted_enclave("revoke_test", "test", "1.0")

        # Revoke it
        success = verifier.revoke_enclave("revoke_test")

        assert success is True

        # Should no longer be trusted
        info = verifier.get_enclave_info("revoke_test")
        assert info["trusted"] is False

    def test_revoke_unknown_enclave(self):
        """Test revoking unknown enclave."""
        verifier = TEEVerifier()

        success = verifier.revoke_enclave("unknown")

        assert success is False

    def test_get_enclave_info(self):
        """Test getting enclave information."""
        verifier = TEEVerifier()

        # Get default mock enclave info
        info = verifier.get_enclave_info(verifier.mock_mrenclave)

        assert info is not None
        assert info["name"] == "mock-verifier-enclave"
        assert info["version"] == "1.0"

    def test_get_unknown_enclave_info(self):
        """Test getting info for unknown enclave."""
        verifier = TEEVerifier()

        info = verifier.get_enclave_info("unknown_enclave")

        assert info is None


class TestTEEIntegration:
    """Integration tests for TEE attestation."""

    def test_full_attestation_flow(self):
        """Test complete attestation workflow."""
        verifier = TEEVerifier()

        # Agent generates quote
        agent_did = "did:key:z6MkTestAgent"
        report = verifier.generate_quote(agent_did)

        assert report is not None

        # Verifier pool validates quote
        is_valid = verifier.verify_quote(report)
        assert is_valid is True

        # Check MRENCLAVE
        matches = verifier.check_mrenclave(report, verifier.mock_mrenclave)
        assert matches is True

    def test_attestation_with_verifier_pool(self):
        """Test TEE attestation verification flow."""
        # Demonstrate TEE verification flow (without full StakeManager setup)

        tee_verifier = TEEVerifier()
        verifier_id = "verifier_tee"

        # Generate TEE attestation
        report = tee_verifier.generate_quote(verifier_id)

        # Verify attestation
        is_verified = tee_verifier.verify_quote(report)

        # TEE verification successful
        assert is_verified is True
        assert report.report_data == verifier_id

        # In production with verifier pool:
        # metadata = VerifierMetadata(..., tee_verified=is_verified)
        # pool.register(verifier_id, stake, capabilities, metadata)

    def test_tee_verifier_weight_bonus(self):
        """Test that TEE-verified verifiers should get weight bonus."""
        # Demonstrate expected TEE weight bonus behavior

        tee_verifier = TEEVerifier()

        # TEE-verified verifier
        report = tee_verifier.generate_quote("tee_agent")
        is_tee_verified = tee_verifier.verify_quote(report)

        # Calculate expected weights (conceptual demonstration)
        base_weight = 1000
        tee_multiplier = 2.0 if is_tee_verified else 1.0

        tee_weight = base_weight * tee_multiplier
        regular_weight = base_weight * 1.0

        # TEE verifiers should get 2x bonus
        assert tee_weight == regular_weight * 2.0
        assert tee_weight == 2000

        # In production, VerifierSelector would apply this multiplier
        # based on verifier_record.metadata.tee_verified flag

    def test_revoked_enclave_fails_verification(self):
        """Test that revoked enclave fails verification."""
        verifier = TEEVerifier()

        # Generate quote
        report = verifier.generate_quote("data")

        # Should verify initially
        assert verifier.verify_quote(report) is True

        # Revoke the enclave
        verifier.revoke_enclave(report.mrenclave)

        # Should fail verification now
        assert verifier.verify_quote(report) is False
