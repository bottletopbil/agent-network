"""
Test WASM Policy Runtime

Verifies:
- WASM evaluation works
- Gas metering tracks usage
- Gas limits are enforced
- Policy hash stability
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from policy.wasm_runtime import WASMRuntime
from policy.gas_meter import GasMeter, GasExceededError


class TestWASMEvaluation:
    """Test WASM policy evaluation"""

    def test_wasm_evaluation(self):
        """WASM runtime evaluates policies"""
        runtime = WASMRuntime(gas_limit=100000)

        envelope = {
            "kind": "NEED",
            "thread_id": "thread-1",
            "lamport": 1,
            "actor_id": "agent-1",
            "payload_size": 100,
        }

        result = runtime.evaluate(envelope)

        assert result.allowed is True
        assert result.gas_used > 0
        assert result.policy_version == "1.0.0"

    def test_wasm_evaluation_denied(self):
        """WASM runtime denies invalid envelopes"""
        runtime = WASMRuntime(gas_limit=100000)

        envelope = {
            "kind": "INVALID",
            "thread_id": "thread-1",
            "lamport": 1,
            "actor_id": "agent-1",
            "payload_size": 100,
        }

        result = runtime.evaluate(envelope)

        assert result.allowed is False
        assert result.gas_used > 0


class TestGasMetering:
    """Test gas metering functionality"""

    def test_gas_metering_tracks_usage(self):
        """Gas meter tracks usage"""
        runtime = WASMRuntime(gas_limit=100000)

        envelope = {
            "kind": "PROPOSE",
            "thread_id": "thread-1",
            "lamport": 2,
            "actor_id": "agent-2",
            "payload_size": 200,
        }

        result = runtime.evaluate(envelope)

        # Gas should be used
        assert result.gas_used > 0
        assert result.gas_used < runtime.gas_limit

    def test_gas_meter_operations(self):
        """Gas meter tracks individual operations"""
        meter = GasMeter(gas_limit=1000)

        meter.consume_field_access("kind")
        assert meter.used == GasMeter.COST_FIELD_ACCESS

        meter.consume_comparison()
        assert meter.used == GasMeter.COST_FIELD_ACCESS + GasMeter.COST_COMPARISON

        meter.consume_set_membership()
        expected = (
            GasMeter.COST_FIELD_ACCESS
            + GasMeter.COST_COMPARISON
            + GasMeter.COST_SET_MEMBERSHIP
        )
        assert meter.used == expected

    def test_gas_meter_metrics(self):
        """Can get gas metrics"""
        meter = GasMeter(gas_limit=1000)

        meter.consume(100)
        meter.consume(200)

        metrics = meter.get_metrics()

        assert metrics.used == 300
        assert metrics.limit == 1000
        assert metrics.operations == 2
        assert metrics.remaining() == 700
        assert metrics.percent_used() == 30.0


class TestGasLimitExceeded:
    """Test gas limit enforcement"""

    def test_gas_limit_exceeded(self):
        """Gas meter raises error when limit exceeded"""
        meter = GasMeter(gas_limit=100)

        # Consume gas up to limit
        meter.consume(90)

        # This should exceed limit
        with pytest.raises(GasExceededError):
            meter.consume(20)

    def test_runtime_handles_gas_exceeded(self):
        """Runtime handles gas exceeded gracefully"""
        # Very low gas limit
        runtime = WASMRuntime(gas_limit=10)

        envelope = {
            "kind": "DECIDE",
            "thread_id": "thread-1",
            "lamport": 5,
            "actor_id": "agent-5",
            "payload_size": 500,
        }

        result = runtime.evaluate(envelope)

        # Should deny due to gas limit
        assert result.allowed is False
        assert any("Gas limit exceeded" in r for r in result.reasons)
        assert result.gas_used > runtime.gas_limit

    def test_gas_meter_reset(self):
        """Gas meter can be reset"""
        meter = GasMeter(gas_limit=1000)

        meter.consume(500)
        assert meter.used == 500

        meter.reset()
        assert meter.used == 0
        assert meter.operations == 0


class TestPolicyHashStability:
    """Test policy hash for integrity"""

    def test_policy_hash_exists(self):
        """Runtime provides policy hash"""
        runtime = WASMRuntime()

        policy_hash = runtime.get_policy_hash()

        assert policy_hash is not None
        assert len(policy_hash) == 64  # SHA256 hex = 64 chars

    def test_policy_hash_stable(self):
        """Policy hash is stable across instances"""
        runtime1 = WASMRuntime()
        runtime2 = WASMRuntime()

        hash1 = runtime1.get_policy_hash()
        hash2 = runtime2.get_policy_hash()

        # Same policy should have same hash
        assert hash1 == hash2

    def test_verify_policy_integrity(self):
        """Can verify policy integrity"""
        runtime = WASMRuntime()

        correct_hash = runtime.get_policy_hash()
        wrong_hash = "0" * 64

        assert runtime.verify_policy_integrity(correct_hash) is True
        assert runtime.verify_policy_integrity(wrong_hash) is False


class TestBatchEvaluation:
    """Test batch evaluation"""

    def test_batch_evaluation(self):
        """Can evaluate multiple envelopes"""
        runtime = WASMRuntime(gas_limit=100000)

        envelopes = [
            {
                "kind": "NEED",
                "thread_id": "t1",
                "lamport": 1,
                "actor_id": "a1",
                "payload_size": 100,
            },
            {
                "kind": "PROPOSE",
                "thread_id": "t1",
                "lamport": 2,
                "actor_id": "a2",
                "payload_size": 200,
            },
        ]

        results = runtime.evaluate_batch(envelopes)

        assert len(results) == 2
        assert all(r.gas_used > 0 for r in results)


class TestRuntimeInfo:
    """Test runtime metadata"""

    def test_runtime_info(self):
        """Runtime provides metadata"""
        runtime = WASMRuntime(gas_limit=50000)

        info = runtime.get_runtime_info()

        assert info["runtime_type"] == "python_wasm_compat"
        assert info["gas_limit"] == 50000
        assert info["policy_version"] == "1.0.0"
        assert "policy_hash" in info


class TestGasMeterDisable:
    """Test gas meter disable/enable"""

    def test_gas_meter_disable(self):
        """Can disable gas metering"""
        meter = GasMeter(gas_limit=10)

        meter.disable()

        # Should not raise even with high consumption
        meter.consume(1000)
        assert meter.used == 1000  # Still tracked

        # No error raised

    def test_gas_meter_enable(self):
        """Can re-enable gas metering"""
        meter = GasMeter(gas_limit=100)

        meter.disable()
        meter.consume(50)

        meter.enable()

        # Should now enforce limit
        with pytest.raises(GasExceededError):
            meter.consume(100)


class TestGasEstimation:
    """Test gas estimation"""

    def test_estimate_remaining_operations(self):
        """Can estimate remaining operations"""
        meter = GasMeter(gas_limit=1000)

        meter.consume(400)

        # Remaining: 600
        # Cost per op: 10
        remaining_ops = meter.estimate_remaining_operations(10)

        assert remaining_ops == 60


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
