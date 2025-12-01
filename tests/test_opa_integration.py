"""
Test OPA Policy Engine Integration

Verifies:
- Allowed envelope validation
- Disallowed kinds rejection
- Payload size limits
- Policy versioning
- Batch evaluation
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from policy.opa_engine import OPAEngine, PolicyResult, BasePolicyEngine


class TestAllowedEnvelope:
    """Test allowed envelope validation"""

    def test_allowed_envelope(self):
        """Valid envelope passes policy"""
        engine = OPAEngine()

        envelope = {
            "kind": "NEED",
            "thread_id": "thread-1",
            "lamport": 1,
            "actor_id": "agent-1",
            "payload_size": 100,
        }

        result = engine.evaluate(envelope)

        assert result.allowed is True
        assert len(result.reasons) > 0
        assert result.policy_version == "1.0.0"

    def test_all_allowed_kinds(self):
        """All protocol message kinds are allowed"""
        engine = OPAEngine()

        allowed_kinds = [
            "NEED",
            "PROPOSE",
            "CLAIM",
            "COMMIT",
            "ATTEST",
            "DECIDE",
            "FINALIZE",
            "YIELD",
            "RELEASE",
            "UPDATE_PLAN",
            "ATTEST_PLAN",
            "CHALLENGE",
            "INVALIDATE",
            "RECONCILE",
            "CHECKPOINT",
        ]

        for kind in allowed_kinds:
            envelope = {
                "kind": kind,
                "thread_id": "thread-1",
                "lamport": 1,
                "actor_id": "agent-1",
                "payload_size": 100,
            }

            result = engine.evaluate(envelope)
            assert result.allowed is True, f"{kind} should be allowed"


class TestDisallowedKind:
    """Test disallowed kind rejection"""

    def test_disallowed_kind(self):
        """Invalid message kind is rejected"""
        engine = OPAEngine()

        envelope = {
            "kind": "INVALID_KIND",
            "thread_id": "thread-1",
            "lamport": 1,
            "actor_id": "agent-1",
            "payload_size": 100,
        }

        result = engine.evaluate(envelope)

        assert result.allowed is False
        assert any("Invalid message kind" in r for r in result.reasons)

    def test_missing_kind(self):
        """Missing kind field is rejected"""
        engine = OPAEngine()

        envelope = {
            # No kind field
            "thread_id": "thread-1",
            "lamport": 1,
            "actor_id": "agent-1",
            "payload_size": 100,
        }

        result = engine.evaluate(envelope)

        assert result.allowed is False
        # Should reject for missing kind
        assert any("kind" in r for r in result.reasons)


class TestPayloadSizeLimit:
    """Test payload size limit enforcement"""

    def test_within_size_limit(self):
        """Payload under limit is allowed"""
        engine = OPAEngine()

        envelope = {
            "kind": "NEED",
            "thread_id": "thread-1",
            "lamport": 1,
            "actor_id": "agent-1",
            "payload_size": 1024,  # 1KB - well under limit
        }

        result = engine.evaluate(envelope)

        assert result.allowed is True

    def test_at_size_limit(self):
        """Payload at exactly the limit is rejected"""
        engine = OPAEngine()

        max_size = engine.MAX_PAYLOAD_SIZE

        envelope = {
            "kind": "NEED",
            "thread_id": "thread-1",
            "lamport": 1,
            "actor_id": "agent-1",
            "payload_size": max_size,  # Exactly at limit
        }

        result = engine.evaluate(envelope)

        # Policy uses >= so at limit should be rejected
        assert result.allowed is False
        assert any("too large" in r.lower() for r in result.reasons)

    def test_over_size_limit(self):
        """Payload over limit is rejected"""
        engine = OPAEngine()

        max_size = engine.MAX_PAYLOAD_SIZE

        envelope = {
            "kind": "NEED",
            "thread_id": "thread-1",
            "lamport": 1,
            "actor_id": "agent-1",
            "payload_size": max_size + 1000,  # Over limit
        }

        result = engine.evaluate(envelope)

        assert result.allowed is False
        assert any("too large" in r.lower() for r in result.reasons)


class TestRequiredFields:
    """Test required field validation"""

    def test_missing_thread_id(self):
        """Missing thread_id is rejected"""
        engine = OPAEngine()

        envelope = {
            "kind": "NEED",
            # Missing thread_id
            "lamport": 1,
            "actor_id": "agent-1",
            "payload_size": 100,
        }

        result = engine.evaluate(envelope)

        assert result.allowed is False
        assert any("thread_id" in r for r in result.reasons)

    def test_missing_lamport(self):
        """Missing lamport is rejected"""
        engine = OPAEngine()

        envelope = {
            "kind": "NEED",
            "thread_id": "thread-1",
            # Missing lamport
            "actor_id": "agent-1",
            "payload_size": 100,
        }

        result = engine.evaluate(envelope)

        assert result.allowed is False
        assert any("lamport" in r for r in result.reasons)

    def test_missing_actor_id(self):
        """Missing actor_id is rejected"""
        engine = OPAEngine()

        envelope = {
            "kind": "NEED",
            "thread_id": "thread-1",
            "lamport": 1,
            # Missing actor_id
            "payload_size": 100,
        }

        result = engine.evaluate(envelope)

        assert result.allowed is False
        assert any("actor_id" in r for r in result.reasons)


class TestPolicyVersioning:
    """Test policy versioning"""

    def test_policy_version_present(self):
        """Policy result includes version"""
        engine = OPAEngine()

        envelope = {
            "kind": "NEED",
            "thread_id": "thread-1",
            "lamport": 1,
            "actor_id": "agent-1",
            "payload_size": 100,
        }

        result = engine.evaluate(envelope)

        assert result.policy_version is not None
        assert result.policy_version == "1.0.0"


class TestBatchEvaluation:
    """Test batch envelope evaluation"""

    def test_batch_evaluation(self):
        """Can evaluate multiple envelopes"""
        engine = OPAEngine()

        envelopes = [
            {
                "kind": "NEED",
                "thread_id": "thread-1",
                "lamport": 1,
                "actor_id": "agent-1",
                "payload_size": 100,
            },
            {
                "kind": "PROPOSE",
                "thread_id": "thread-1",
                "lamport": 2,
                "actor_id": "agent-2",
                "payload_size": 200,
            },
            {
                "kind": "INVALID",  # This should fail
                "thread_id": "thread-1",
                "lamport": 3,
                "actor_id": "agent-3",
                "payload_size": 300,
            },
        ]

        results = engine.evaluate_batch(envelopes)

        assert len(results) == 3
        assert results[0].allowed is True
        assert results[1].allowed is True
        assert results[2].allowed is False


class TestGasMetering:
    """Test gas usage tracking"""

    def test_gas_used(self):
        """Policy evaluation tracks gas usage"""
        engine = OPAEngine()

        envelope = {
            "kind": "NEED",
            "thread_id": "thread-1",
            "lamport": 1,
            "actor_id": "agent-1",
            "payload_size": 100,
        }

        result = engine.evaluate(envelope)

        # Simple gas metering: size of envelope
        assert result.gas_used > 0


class TestMultipleViolations:
    """Test envelopes with multiple policy violations"""

    def test_multiple_violations(self):
        """Envelope with multiple violations lists all reasons"""
        engine = OPAEngine()

        envelope = {
            "kind": "INVALID_KIND",  # Violation 1
            # Missing thread_id  # Violation 2
            "lamport": 1,
            "actor_id": "agent-1",
            "payload_size": 2000000,  # Violation 3 (over limit)
        }

        result = engine.evaluate(envelope)

        assert result.allowed is False
        # Should have multiple deny reasons
        assert len(result.reasons) >= 2


class TestBasePolicyEngine:
    """Test base policy engine directly"""

    def test_base_engine(self):
        """Base policy engine works without OPA"""
        engine = BasePolicyEngine()

        envelope = {
            "kind": "DECIDE",
            "thread_id": "thread-1",
            "lamport": 5,
            "actor_id": "agent-1",
            "payload_size": 500,
        }

        result = engine.evaluate(envelope)

        assert result.allowed is True
        assert isinstance(result, PolicyResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
