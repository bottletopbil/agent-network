"""
Tests for Three-Gate Policy Enforcement

Tests the three enforcement points:
1. PREFLIGHT: Client-side check before publishing
2. INGRESS: Receiver-side check on receive
3. COMMIT_GATE: Verifier-side check before ATTEST
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from policy.gates import GateEnforcer, PolicyGate
from policy.eval_digest import (
    compute_eval_digest,
    verify_eval_digest,
    create_eval_record,
)
from policy.opa_engine import PolicyResult


@pytest.fixture
def gate_enforcer():
    """Create a gate enforcer for testing"""
    return GateEnforcer(enable_cache=False)


@pytest.fixture
def sample_envelope():
    """Sample envelope for testing"""
    return {
        "operation": "PROPOSE",
        "agent_id": "agent-1",
        "thread_id": "thread-1",
        "lamport": 10,
        "signature": "test-signature",
        "timestamp": 1234567890,
        "payload": {
            "proposal_id": "prop-1",
            "resources": {"cpu_ms": 100, "memory_mb": 50, "gas": 1000},
        },
    }


@pytest.fixture
def sample_telemetry():
    """Sample telemetry for testing"""
    return {
        "resources": {"cpu_ms": 95, "memory_mb": 48, "gas": 950},
        "execution_time_ms": 95,
    }


class TestPreflightGate:
    """Tests for PREFLIGHT gate validation"""

    def test_preflight_allows_valid_envelope(self, gate_enforcer, sample_envelope):
        """Preflight should allow valid envelopes"""
        mock_result = PolicyResult(allowed=True, reasons=["Valid"], policy_version="1.0.0")

        with patch.object(gate_enforcer.opa_engine, "evaluate", return_value=mock_result):
            decision = gate_enforcer.preflight_validate(sample_envelope)

        assert decision.allowed is True
        assert decision.gate == PolicyGate.PREFLIGHT
        assert decision.gas_used == 0  # Preflight is fast

    def test_preflight_rejects_invalid(self, gate_enforcer, sample_envelope):
        """Preflight should reject invalid envelopes"""
        mock_result = PolicyResult(
            allowed=False, reasons=["Invalid operation"], policy_version="1.0.0"
        )

        with patch.object(gate_enforcer.opa_engine, "evaluate", return_value=mock_result):
            decision = gate_enforcer.preflight_validate(sample_envelope)

        assert decision.allowed is False
        assert decision.gate == PolicyGate.PREFLIGHT
        assert decision.reason == "Invalid operation"

    def test_preflight_caching(self, sample_envelope):
        """Preflight should cache decisions"""
        enforcer = GateEnforcer(enable_cache=True)
        mock_result = PolicyResult(allowed=True, reasons=["Valid"], policy_version="1.0.0")

        with patch.object(enforcer.opa_engine, "evaluate", return_value=mock_result) as mock_eval:
            # First call
            decision1 = enforcer.preflight_validate(sample_envelope)
            assert decision1.allowed is True
            assert mock_eval.call_count == 1

            # Second call should use cache
            decision2 = enforcer.preflight_validate(sample_envelope)
            assert decision2.allowed is True
            assert mock_eval.call_count == 1  # Not called again

    def test_preflight_handles_errors(self, gate_enforcer, sample_envelope):
        """Preflight should handle errors gracefully"""
        # Mock OPA engine to raise exception
        with patch.object(
            gate_enforcer.opa_engine, "evaluate", side_effect=Exception("Policy error")
        ):
            decision = gate_enforcer.preflight_validate(sample_envelope)

        assert decision.allowed is False
        assert "error" in decision.reason.lower()


class TestIngressGate:
    """Tests for INGRESS gate validation"""

    def test_ingress_allows_valid_envelope(self, gate_enforcer, sample_envelope):
        """Ingress should allow valid envelopes"""
        mock_result = PolicyResult(
            allowed=True, reasons=["Valid"], policy_version="1.0.0", gas_used=50
        )

        with patch.object(gate_enforcer.wasm_runtime, "evaluate", return_value=mock_result):
            with patch.object(gate_enforcer.gas_meter, "used", 50, create=True):
                decision = gate_enforcer.ingress_validate(sample_envelope)

        assert decision.allowed is True
        assert decision.gate == PolicyGate.INGRESS

    def test_ingress_blocks_bad_envelope(self, gate_enforcer, sample_envelope):
        """Ingress should block invalid envelopes"""
        mock_result = PolicyResult(
            allowed=False,
            reasons=["Signature invalid"],
            policy_version="1.0.0",
            gas_used=50,
        )

        with patch.object(gate_enforcer.wasm_runtime, "evaluate", return_value=mock_result):
            with patch.object(gate_enforcer.gas_meter, "used", 50, create=True):
                decision = gate_enforcer.ingress_validate(sample_envelope)

        assert decision.allowed is False
        assert decision.gate == PolicyGate.INGRESS
        assert "Signature invalid" in decision.reason

    def test_ingress_full_evaluation(self, gate_enforcer, sample_envelope):
        """Ingress should perform full WASM evaluation"""
        mock_result = PolicyResult(
            allowed=True, reasons=["Valid"], policy_version="1.0.0", gas_used=100
        )

        with patch.object(
            gate_enforcer.wasm_runtime, "evaluate", return_value=mock_result
        ) as mock_eval:
            with patch.object(gate_enforcer.gas_meter, "reset") as mock_reset:
                with patch.object(gate_enforcer.gas_meter, "used", 100, create=True):
                    gate_enforcer.ingress_validate(sample_envelope)

        # Verify gas meter was reset
        mock_reset.assert_called_once()
        # Verify WASM evaluation was called
        assert mock_eval.call_count == 1


class TestCommitGate:
    """Tests for COMMIT_GATE validation"""

    def test_commit_gate_allows_matching_resources(
        self, gate_enforcer, sample_envelope, sample_telemetry
    ):
        """Commit gate should allow when actual matches claimed"""
        mock_result = PolicyResult(
            allowed=True, reasons=["Valid"], policy_version="1.0.0", gas_used=75
        )

        with patch.object(gate_enforcer.wasm_runtime, "evaluate", return_value=mock_result):
            with patch.object(gate_enforcer.gas_meter, "used", 75, create=True):
                decision = gate_enforcer.commit_gate_validate(sample_envelope, sample_telemetry)

        assert decision.allowed is True
        assert decision.gate == PolicyGate.COMMIT_GATE

    def test_commit_gate_catches_violations(self, gate_enforcer, sample_envelope):
        """Commit gate should catch resource violations"""
        # Create telemetry with excessive resource usage
        bad_telemetry = {
            "resources": {
                "cpu_ms": 200,  # Claimed 100, used 200 (exceeds 10% margin)
                "memory_mb": 48,
                "gas": 950,
            }
        }

        mock_result = PolicyResult(
            allowed=True, reasons=["Valid"], policy_version="1.0.0", gas_used=75
        )

        with patch.object(gate_enforcer.wasm_runtime, "evaluate", return_value=mock_result):
            with patch.object(gate_enforcer.gas_meter, "used", 75, create=True):
                decision = gate_enforcer.commit_gate_validate(sample_envelope, bad_telemetry)

        # Should be rejected due to resource violation
        assert decision.allowed is False
        assert "cpu exceeded" in decision.reason.lower()

    def test_commit_gate_memory_violation(self, gate_enforcer, sample_envelope):
        """Commit gate should catch memory violations"""
        bad_telemetry = {
            "resources": {
                "cpu_ms": 95,
                "memory_mb": 100,  # Claimed 50, used 100
                "gas": 950,
            }
        }

        mock_result = PolicyResult(
            allowed=True, reasons=["Valid"], policy_version="1.0.0", gas_used=75
        )

        with patch.object(gate_enforcer.wasm_runtime, "evaluate", return_value=mock_result):
            with patch.object(gate_enforcer.gas_meter, "used", 75, create=True):
                decision = gate_enforcer.commit_gate_validate(sample_envelope, bad_telemetry)

        assert decision.allowed is False
        assert "memory exceeded" in decision.reason.lower()

    def test_commit_gate_gas_violation(self, gate_enforcer, sample_envelope):
        """Commit gate should catch gas violations"""
        bad_telemetry = {
            "resources": {
                "cpu_ms": 95,
                "memory_mb": 48,
                "gas": 2000,  # Claimed 1000, used 2000
            }
        }

        mock_result = PolicyResult(
            allowed=True, reasons=["Valid"], policy_version="1.0.0", gas_used=75
        )

        with patch.object(gate_enforcer.wasm_runtime, "evaluate", return_value=mock_result):
            with patch.object(gate_enforcer.gas_meter, "used", 75, create=True):
                decision = gate_enforcer.commit_gate_validate(sample_envelope, bad_telemetry)

        assert decision.allowed is False
        assert "gas exceeded" in decision.reason.lower()

    def test_commit_gate_allows_margin(self, gate_enforcer, sample_envelope):
        """Commit gate should allow 10% margin for resource variations"""
        # Use 109% of claimed resources (within margin)
        within_margin_telemetry = {
            "resources": {
                "cpu_ms": 109,  # 109% of 100
                "memory_mb": 54,  # 108% of 50
                "gas": 1090,  # 109% of 1000
            }
        }

        mock_result = PolicyResult(
            allowed=True, reasons=["Valid"], policy_version="1.0.0", gas_used=75
        )

        with patch.object(gate_enforcer.wasm_runtime, "evaluate", return_value=mock_result):
            with patch.object(gate_enforcer.gas_meter, "used", 75, create=True):
                decision = gate_enforcer.commit_gate_validate(
                    sample_envelope, within_margin_telemetry
                )

        assert decision.allowed is True


class TestEvalDigest:
    """Tests for policy evaluation digest"""

    def test_compute_eval_digest(self):
        """Compute digest should produce deterministic hash"""
        policy_input = {"operation": "PROPOSE", "agent_id": "agent-1"}
        decision = {"allow": True}
        policy_hash = "policy-v1"

        digest1 = compute_eval_digest(policy_input, decision, policy_hash)
        digest2 = compute_eval_digest(policy_input, decision, policy_hash)

        assert digest1 == digest2
        assert len(digest1) == 64  # SHA256 hex

    def test_digest_changes_with_input(self):
        """Digest should change when input changes"""
        policy_input1 = {"operation": "PROPOSE"}
        policy_input2 = {"operation": "ATTEST"}
        decision = {"allow": True}
        policy_hash = "policy-v1"

        digest1 = compute_eval_digest(policy_input1, decision, policy_hash)
        digest2 = compute_eval_digest(policy_input2, decision, policy_hash)

        assert digest1 != digest2

    def test_digest_changes_with_decision(self):
        """Digest should change when decision changes"""
        policy_input = {"operation": "PROPOSE"}
        decision1 = {"allow": True}
        decision2 = {"allow": False}
        policy_hash = "policy-v1"

        digest1 = compute_eval_digest(policy_input, decision1, policy_hash)
        digest2 = compute_eval_digest(policy_input, decision2, policy_hash)

        assert digest1 != digest2

    def test_digest_changes_with_policy_hash(self):
        """Digest should change when policy version changes"""
        policy_input = {"operation": "PROPOSE"}
        decision = {"allow": True}

        digest1 = compute_eval_digest(policy_input, decision, "policy-v1")
        digest2 = compute_eval_digest(policy_input, decision, "policy-v2")

        assert digest1 != digest2

    def test_verify_eval_digest(self):
        """Verify should validate correct digest"""
        policy_input = {"operation": "PROPOSE"}
        decision = {"allow": True}
        policy_hash = "policy-v1"

        eval_record = create_eval_record(policy_input, decision, policy_hash)

        # Create envelope with eval record
        envelope = {**eval_record}

        assert verify_eval_digest(envelope) is True

    def test_verify_detects_tampering(self):
        """Verify should detect tampered digest"""
        policy_input = {"operation": "PROPOSE"}
        decision = {"allow": True}
        policy_hash = "policy-v1"

        eval_record = create_eval_record(policy_input, decision, policy_hash)

        # Tamper with the decision
        envelope = {**eval_record, "policy_decision": {"allow": False}}  # Changed!

        assert verify_eval_digest(envelope) is False

    def test_verify_handles_missing_fields(self):
        """Verify should handle missing fields gracefully"""
        envelope = {"operation": "PROPOSE"}
        assert verify_eval_digest(envelope) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
