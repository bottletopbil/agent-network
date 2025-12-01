"""
WASM-Compatible Policy Runtime

Provides WASM-like execution environment for policies with gas metering.
Uses Python implementation with WASM-compatible semantics.

Since WASM compilation requires OPA binary (not installed), this provides
a Python-based runtime that can be upgraded to real WASM later.
"""

import json
import hashlib
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from policy.opa_engine import OPAEngine, PolicyResult
from policy.gas_meter import GasMeter, GasExceededError

logger = logging.getLogger(__name__)


class WASMRuntime:
    """
    WASM-compatible policy runtime.

    Provides:
    - Gas-metered policy execution
    - Policy hash for integrity
    - WASM-like API
    - Future upgrade path to real WASM
    """

    def __init__(self, policy_path: Optional[Path] = None, gas_limit: int = 100000):
        """
        Initialize WASM runtime.

        Args:
            policy_path: Path to policy (for future WASM support)
            gas_limit: Maximum gas per evaluation
        """
        self.policy_path = policy_path
        self.gas_limit = gas_limit

        # Use OPA engine as backend
        self.engine = OPAEngine(policy_path)

        # Calculate policy hash for integrity
        self._policy_hash = self._calculate_policy_hash()

        logger.info(
            f"WASM runtime initialized (gas_limit: {gas_limit}, "
            f"policy_hash: {self._policy_hash[:16]}...)"
        )

    def _calculate_policy_hash(self) -> str:
        """
        Calculate SHA256 hash of policy.

        Returns:
            Hex-encoded SHA256 hash
        """
        # For now, hash the policy logic itself
        # In future with real WASM, hash the .wasm file

        policy_repr = json.dumps(
            {
                "allowed_kinds": sorted(self.engine.ALLOWED_KINDS),
                "max_payload_size": self.engine.MAX_PAYLOAD_SIZE,
                "required_fields": sorted(self.engine.REQUIRED_FIELDS),
                "version": "1.0.0",
            },
            sort_keys=True,
        )

        return hashlib.sha256(policy_repr.encode()).hexdigest()

    def get_policy_hash(self) -> str:
        """
        Get SHA256 hash of loaded policy.

        Returns:
            Policy hash as hex string
        """
        return self._policy_hash

    def evaluate(self, input_data: Dict[str, Any]) -> PolicyResult:
        """
        Evaluate policy with gas metering.

        Args:
            input_data: Input envelope for policy

        Returns:
            PolicyResult with gas tracking

        Raises:
            GasExceededError: If gas limit exceeded
        """
        # Create gas meter for this evaluation
        gas_meter = GasMeter(gas_limit=self.gas_limit)

        try:
            # Metered evaluation
            result = self._evaluate_with_metering(input_data, gas_meter)

            # Update gas usage in result
            metrics = gas_meter.get_metrics()
            result.gas_used = metrics.used

            logger.debug(
                f"Policy evaluation complete: allowed={result.allowed}, "
                f"gas={metrics.used}/{metrics.limit}"
            )

            return result

        except GasExceededError as e:
            logger.error(f"Gas limit exceeded during evaluation: {e}")

            # Return denial with gas exceeded reason
            return PolicyResult(
                allowed=False,
                reasons=[str(e)],
                gas_used=gas_meter.used,
                policy_version="1.0.0",
            )

    def _evaluate_with_metering(
        self, input_data: Dict, gas_meter: GasMeter
    ) -> PolicyResult:
        """
        Evaluate policy with gas metering.

        Args:
            input_data: Input envelope
            gas_meter: Gas meter instance

        Returns:
            PolicyResult
        """
        # Meter field accesses
        for field in ["kind", "thread_id", "lamport", "actor_id", "payload_size"]:
            if field in input_data:
                gas_meter.consume_field_access(field)

        # Meter kind check (set membership)
        gas_meter.consume_set_membership()

        # Meter comparisons
        gas_meter.consume_comparison()  # kind check
        gas_meter.consume_comparison()  # size check

        # Meter function call overhead
        gas_meter.consume_function_call("evaluate")

        # Actual policy evaluation
        result = self.engine.evaluate(input_data)

        # Meter result reasons (iteration)
        if result.reasons:
            gas_meter.consume_iteration(len(result.reasons))

        return result

    def evaluate_batch(self, inputs: list[Dict]) -> list[PolicyResult]:
        """
        Evaluate multiple inputs.

        Each evaluation has its own gas limit.

        Args:
            inputs: List of input envelopes

        Returns:
            List of PolicyResults
        """
        results = []

        for input_data in inputs:
            result = self.evaluate(input_data)
            results.append(result)

        return results

    def get_runtime_info(self) -> Dict[str, Any]:
        """
        Get runtime information.

        Returns:
            Dict with runtime metadata
        """
        return {
            "runtime_type": "python_wasm_compat",
            "policy_hash": self._policy_hash,
            "gas_limit": self.gas_limit,
            "policy_version": "1.0.0",
            "wasm_enabled": False,  # Future: detect real WASM
            "backend": "python_opa_engine",
        }

    def verify_policy_integrity(self, expected_hash: str) -> bool:
        """
        Verify policy hasn't been tampered with.

        Args:
            expected_hash: Expected policy hash

        Returns:
            True if hash matches
        """
        return self._policy_hash == expected_hash


# Singleton for easy access
_wasm_runtime: Optional[WASMRuntime] = None


def get_wasm_runtime() -> WASMRuntime:
    """Get global WASM runtime instance"""
    global _wasm_runtime
    if _wasm_runtime is None:
        _wasm_runtime = WASMRuntime()
    return _wasm_runtime


def init_wasm_runtime(
    policy_path: Optional[Path] = None, gas_limit: int = 100000
) -> WASMRuntime:
    """
    Initialize global WASM runtime.

    Args:
        policy_path: Path to policy
        gas_limit: Gas limit per evaluation

    Returns:
        WASMRuntime instance
    """
    global _wasm_runtime
    _wasm_runtime = WASMRuntime(policy_path, gas_limit)
    return _wasm_runtime
