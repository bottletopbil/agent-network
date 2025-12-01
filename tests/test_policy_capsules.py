"""
Tests for Policy Capsules & Versioning

Tests capsule creation, signing, distribution, and conformance validation.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from policy.capsule import PolicyCapsule, CapsuleManager
from policy.conformance import ConformanceChecker


@pytest.fixture
def capsule_manager():
    """Create a capsule manager for testing"""
    return CapsuleManager()


@pytest.fixture
def conformance_checker():
    """Create a conformance checker for testing"""
    return ConformanceChecker()


@pytest.fixture
def sample_tests_passed():
    """Sample list of passed conformance tests"""
    return [
        "test_valid_message_kinds",
        "test_payload_size_limits",
        "test_required_fields",
        "test_signature_validation",
        "test_lamport_ordering",
        "test_gas_metering",
    ]


class TestCapsuleCreation:
    """Tests for capsule creation"""

    def test_create_capsule_without_wasm(self, capsule_manager, sample_tests_passed):
        """Can create capsule for Python-based policy"""
        capsule = capsule_manager.create_capsule(
            wasm_path=None,
            tests_passed=sample_tests_passed,
            schema_version="1.0.0",
            metadata={"author": "test"},
        )

        assert capsule.policy_engine_hash is not None
        assert len(capsule.policy_engine_hash) == 64  # SHA256
        assert capsule.policy_schema_version == "1.0.0"
        assert capsule.conformance_vector == sorted(sample_tests_passed)
        assert capsule.signature is None  # Not signed yet
        assert capsule.metadata["author"] == "test"

    def test_create_capsule_with_wasm(self, capsule_manager, sample_tests_passed, tmp_path):
        """Can create capsule from WASM file"""
        # Create a fake WASM file
        wasm_file = tmp_path / "policy.wasm"
        wasm_file.write_bytes(b"fake wasm content")

        capsule = capsule_manager.create_capsule(
            wasm_path=wasm_file,
            tests_passed=sample_tests_passed,
            schema_version="1.1.0",
        )

        assert capsule.policy_engine_hash is not None
        assert capsule.policy_schema_version == "1.1.0"
        assert len(capsule.conformance_vector) == len(sample_tests_passed)

    def test_capsule_to_dict(self, capsule_manager, sample_tests_passed):
        """Can convert capsule to dict"""
        capsule = capsule_manager.create_capsule(wasm_path=None, tests_passed=sample_tests_passed)

        capsule_dict = capsule.to_dict()

        assert capsule_dict["policy_engine_hash"] == capsule.policy_engine_hash
        assert capsule_dict["policy_schema_version"] == capsule.policy_schema_version
        assert capsule_dict["conformance_vector"] == capsule.conformance_vector

    def test_capsule_to_json(self, capsule_manager, sample_tests_passed):
        """Can convert capsule to JSON"""
        capsule = capsule_manager.create_capsule(wasm_path=None, tests_passed=sample_tests_passed)

        json_str = capsule.to_json()

        assert isinstance(json_str, str)
        assert "policy_engine_hash" in json_str
        assert capsule.policy_engine_hash in json_str

    def test_capsule_from_dict(self, capsule_manager, sample_tests_passed):
        """Can create capsule from dict"""
        original = capsule_manager.create_capsule(wasm_path=None, tests_passed=sample_tests_passed)

        capsule_dict = original.to_dict()
        restored = PolicyCapsule.from_dict(capsule_dict)

        assert restored.policy_engine_hash == original.policy_engine_hash
        assert restored.policy_schema_version == original.policy_schema_version
        assert restored.conformance_vector == original.conformance_vector


class TestCapsuleSigning:
    """Tests for capsule signing and verification"""

    def test_sign_capsule(self, capsule_manager, sample_tests_passed):
        """Can sign a capsule"""
        unsigned = capsule_manager.create_capsule(wasm_path=None, tests_passed=sample_tests_passed)

        signed = capsule_manager.sign_capsule(unsigned, signer_key="test-key")

        assert signed.signature is not None
        assert len(signed.signature) == 64  # SHA256
        assert signed.policy_engine_hash == unsigned.policy_engine_hash

    def test_verify_capsule_valid(self, capsule_manager, sample_tests_passed):
        """Can verify a valid capsule signature"""
        unsigned = capsule_manager.create_capsule(wasm_path=None, tests_passed=sample_tests_passed)

        signed = capsule_manager.sign_capsule(unsigned, signer_key="test-key")

        is_valid = capsule_manager.verify_capsule(signed, expected_signer_key="test-key")
        assert is_valid is True

    def test_verify_capsule_invalid_key(self, capsule_manager, sample_tests_passed):
        """Detects invalid signer key"""
        unsigned = capsule_manager.create_capsule(wasm_path=None, tests_passed=sample_tests_passed)

        signed = capsule_manager.sign_capsule(unsigned, signer_key="test-key")

        is_valid = capsule_manager.verify_capsule(signed, expected_signer_key="wrong-key")
        assert is_valid is False

    def test_verify_capsule_no_signature(self, capsule_manager, sample_tests_passed):
        """Detects missing signature"""
        unsigned = capsule_manager.create_capsule(wasm_path=None, tests_passed=sample_tests_passed)

        is_valid = capsule_manager.verify_capsule(unsigned)
        assert is_valid is False

    def test_get_canonical_bytes(self, capsule_manager, sample_tests_passed):
        """Canonical bytes are deterministic"""
        capsule = capsule_manager.create_capsule(wasm_path=None, tests_passed=sample_tests_passed)

        bytes1 = capsule.get_canonical_bytes()
        bytes2 = capsule.get_canonical_bytes()

        assert bytes1 == bytes2


class TestCapsuleDistribution:
    """Tests for capsule distribution via NATS"""

    @pytest.mark.asyncio
    async def test_distribute_capsule(self, capsule_manager, sample_tests_passed):
        """Can distribute capsule to NATS"""
        mock_nats = AsyncMock()
        capsule_manager.nats_client = mock_nats

        capsule = capsule_manager.create_capsule(wasm_path=None, tests_passed=sample_tests_passed)
        signed = capsule_manager.sign_capsule(capsule, signer_key="test-key")

        await capsule_manager.distribute_capsule(signed)

        # Verify NATS publish was called
        mock_nats.publish.assert_called_once()
        call_args = mock_nats.publish.call_args
        assert call_args[0][0] == "policy.capsule.update"
        assert isinstance(call_args[0][1], bytes)

    @pytest.mark.asyncio
    async def test_distribute_without_nats(self, capsule_manager, sample_tests_passed):
        """Handle missing NATS client gracefully"""
        capsule = capsule_manager.create_capsule(wasm_path=None, tests_passed=sample_tests_passed)

        # Should not raise exception
        await capsule_manager.distribute_capsule(capsule)

    @pytest.mark.asyncio
    async def test_receive_capsule_valid(self, capsule_manager, sample_tests_passed):
        """Can receive and accept valid capsule"""
        capsule = capsule_manager.create_capsule(wasm_path=None, tests_passed=sample_tests_passed)
        signed = capsule_manager.sign_capsule(capsule, signer_key="test-key")

        # Mock conformance checker
        mock_checker = Mock()
        mock_checker.validate_conformance = Mock(return_value=True)

        accepted = await capsule_manager.receive_capsule(
            signed, conformance_checker=mock_checker, signer_key="test-key"
        )

        assert accepted is True
        assert signed.policy_engine_hash in capsule_manager.received_capsules

    @pytest.mark.asyncio
    async def test_receive_capsule_invalid_signature(self, capsule_manager, sample_tests_passed):
        """Reject capsule with invalid signature"""
        capsule = capsule_manager.create_capsule(wasm_path=None, tests_passed=sample_tests_passed)
        signed = capsule_manager.sign_capsule(capsule, signer_key="test-key")

        accepted = await capsule_manager.receive_capsule(signed, signer_key="wrong-key")

        assert accepted is False

    @pytest.mark.asyncio
    async def test_receive_capsule_fails_conformance(self, capsule_manager, sample_tests_passed):
        """Reject capsule that fails conformance"""
        capsule = capsule_manager.create_capsule(wasm_path=None, tests_passed=sample_tests_passed)
        signed = capsule_manager.sign_capsule(capsule, signer_key="test-key")

        # Mock conformance checker that fails
        mock_checker = Mock()
        mock_checker.validate_conformance = Mock(return_value=False)

        accepted = await capsule_manager.receive_capsule(
            signed, conformance_checker=mock_checker, signer_key="test-key"
        )

        assert accepted is False


class TestConformanceValidation:
    """Tests for conformance checking"""

    def test_run_tests(self, conformance_checker):
        """Can run conformance tests"""
        passed_tests = conformance_checker.run_tests(policy_wasm=None)

        assert isinstance(passed_tests, list)
        assert len(passed_tests) > 0
        # Should pass all required tests with default policy
        assert "test_valid_message_kinds" in passed_tests
        assert "test_payload_size_limits" in passed_tests

    def test_validate_conformance_passing(self, conformance_checker, capsule_manager):
        """Validate capsule with all required tests"""
        all_tests = conformance_checker.REQUIRED_TESTS + conformance_checker.OPTIONAL_TESTS

        capsule = capsule_manager.create_capsule(wasm_path=None, tests_passed=all_tests)

        is_conformant = conformance_checker.validate_conformance(capsule)
        assert is_conformant is True

    def test_validate_conformance_missing_required(self, conformance_checker, capsule_manager):
        """Reject capsule missing required tests"""
        incomplete_tests = ["test_valid_message_kinds"]  # Missing other required tests

        capsule = capsule_manager.create_capsule(wasm_path=None, tests_passed=incomplete_tests)

        is_conformant = conformance_checker.validate_conformance(capsule)
        assert is_conformant is False

    def test_get_test_coverage(self, conformance_checker):
        """Can get test coverage statistics"""
        passed_tests = [
            "test_valid_message_kinds",
            "test_payload_size_limits",
            "test_required_fields",
            "test_signature_validation",
            "test_lamport_ordering",
        ]

        coverage = conformance_checker.get_test_coverage(passed_tests)

        assert coverage["passed_required"] == 5
        assert coverage["is_conformant"] is True
        assert coverage["coverage_percent"] > 0


class TestCapsuleManager:
    """Tests for capsule manager functionality"""

    def test_get_capsule(self, capsule_manager, sample_tests_passed):
        """Can retrieve stored capsule"""
        capsule = capsule_manager.create_capsule(wasm_path=None, tests_passed=sample_tests_passed)

        capsule_manager.received_capsules[capsule.policy_engine_hash] = capsule

        retrieved = capsule_manager.get_capsule(capsule.policy_engine_hash)
        assert retrieved == capsule

    def test_list_capsules(self, capsule_manager, sample_tests_passed):
        """Can list all capsules"""
        capsule1 = capsule_manager.create_capsule(
            wasm_path=None, tests_passed=sample_tests_passed, schema_version="1.0.0"
        )
        capsule2 = capsule_manager.create_capsule(
            wasm_path=None, tests_passed=sample_tests_passed, schema_version="1.1.0"
        )

        capsule_manager.received_capsules[capsule1.policy_engine_hash] = capsule1
        capsule_manager.received_capsules[capsule2.policy_engine_hash] = capsule2

        capsules = capsule_manager.list_capsules()
        assert len(capsules) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
