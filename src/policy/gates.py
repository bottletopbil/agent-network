"""
Three-Gate Policy Enforcement System

Implements three enforcement points:
1. PREFLIGHT: Client-side check before publishing (fast, cached)
2. INGRESS: Every agent checks on receive (full WASM evaluation)
3. COMMIT_GATE: Verifiers check actual execution (compare claimed vs actual resources)
"""

from enum import Enum
from typing import Dict, Any, Optional
import json
import logging
from dataclasses import dataclass

from .opa_engine import OPAEngine
from .wasm_runtime import WASMRuntime
from .gas_meter import GasMeter

logger = logging.getLogger(__name__)


class PolicyGate(Enum):
    """Three enforcement gates for policy validation"""

    PREFLIGHT = "preflight"  # Client-side before publish
    INGRESS = "ingress"  # Receiver-side on receive
    COMMIT_GATE = "commit_gate"  # Verifier-side before ATTEST


@dataclass
class PolicyDecision:
    """Result of a policy evaluation"""

    allowed: bool
    gate: PolicyGate
    reason: Optional[str] = None
    gas_used: int = 0
    policy_hash: Optional[str] = None


class GateEnforcer:
    """
    Enforces policies at three gates:
    - Preflight: Fast check before publishing
    - Ingress: Full check on receive
    - Commit Gate: Verify claimed vs actual execution
    """

    def __init__(
        self,
        opa_engine: Optional[OPAEngine] = None,
        wasm_runtime: Optional[WASMRuntime] = None,
        gas_meter: Optional[GasMeter] = None,
        enable_cache: bool = True,
    ):
        self.opa_engine = opa_engine or OPAEngine()
        self.wasm_runtime = wasm_runtime or WASMRuntime()
        self.gas_meter = gas_meter or GasMeter()
        self.enable_cache = enable_cache
        self._preflight_cache: Dict[str, PolicyDecision] = {}

    def preflight_validate(self, envelope: Dict[str, Any]) -> PolicyDecision:
        """
        Client-side check before publishing.
        Fast validation using cached policies.

        Args:
            envelope: Message envelope to validate

        Returns:
            PolicyDecision with validation result
        """
        try:
            # Create cache key from operation type and agent
            cache_key = self._make_cache_key(envelope)

            # Check cache if enabled
            if self.enable_cache and cache_key in self._preflight_cache:
                logger.debug(f"Preflight cache hit for {cache_key}")
                return self._preflight_cache[cache_key]

            # Extract policy input from envelope
            policy_input = self._extract_policy_input(envelope, PolicyGate.PREFLIGHT)

            # Use OPA for quick policy check
            result = self.opa_engine.evaluate(policy_input)

            decision = PolicyDecision(
                allowed=result.allowed,
                gate=PolicyGate.PREFLIGHT,
                reason=result.reasons[0] if result.reasons else None,
                gas_used=0,  # Preflight is fast and doesn't use gas
                policy_hash=result.policy_version,  # Use policy version as hash
            )

            # Cache the decision
            if self.enable_cache:
                self._preflight_cache[cache_key] = decision

            logger.info(f"Preflight validation: {decision.allowed} - {decision.reason}")
            return decision

        except Exception as e:
            logger.error(f"Preflight validation error: {e}", exc_info=True)
            return PolicyDecision(
                allowed=False,
                gate=PolicyGate.PREFLIGHT,
                reason=f"Preflight error: {str(e)}",
            )

    def ingress_validate(self, envelope: Dict[str, Any]) -> PolicyDecision:
        """
        Every agent checks on receive.
        Full WASM evaluation with gas metering.

        Args:
            envelope: Message envelope to validate

        Returns:
            PolicyDecision with validation result
        """
        try:
            # Extract policy input
            policy_input = self._extract_policy_input(envelope, PolicyGate.INGRESS)

            # Start gas metering
            self.gas_meter.reset()

            # Full WASM evaluation
            result = self.wasm_runtime.evaluate(policy_input)
            gas_used = self.gas_meter.used  # Access used directly

            decision = PolicyDecision(
                allowed=result.allowed,
                gate=PolicyGate.INGRESS,
                reason=result.reasons[0] if result.reasons else None,
                gas_used=gas_used,
                policy_hash=result.policy_version,  # Use policy version as hash
            )

            logger.info(
                f"Ingress validation: {decision.allowed} - " f"{decision.reason} (gas: {gas_used})"
            )
            return decision

        except Exception as e:
            logger.error(f"Ingress validation error: {e}", exc_info=True)
            return PolicyDecision(
                allowed=False,
                gate=PolicyGate.INGRESS,
                reason=f"Ingress error: {str(e)}",
            )

    def commit_gate_validate(
        self, envelope: Dict[str, Any], telemetry: Dict[str, Any]
    ) -> PolicyDecision:
        """
        Verifiers check actual execution.
        Compare claimed vs actual resources.

        Args:
            envelope: Message envelope with claimed resources
            telemetry: Actual execution telemetry

        Returns:
            PolicyDecision with validation result
        """
        try:
            # Extract policy input including both claimed and actual
            policy_input = self._extract_policy_input(envelope, PolicyGate.COMMIT_GATE)
            policy_input["telemetry"] = telemetry

            # Start gas metering
            self.gas_meter.reset()

            # Full WASM evaluation with telemetry comparison
            result = self.wasm_runtime.evaluate(policy_input)
            gas_used = self.gas_meter.used  # Access used directly

            # Check for resource violations
            violations = self._check_resource_violations(envelope, telemetry)

            # Decision is only allowed if policy passes AND no violations
            allowed = result.allowed and not violations

            reason = result.reasons[0] if result.reasons else None
            if violations:
                reason = (
                    f"{reason}; Violations: {violations}" if reason else f"Violations: {violations}"
                )

            decision = PolicyDecision(
                allowed=allowed,
                gate=PolicyGate.COMMIT_GATE,
                reason=reason,
                gas_used=gas_used,
                policy_hash=result.policy_version,  # Use policy version as hash
            )

            logger.info(
                f"Commit gate validation: {decision.allowed} - "
                f"{decision.reason} (gas: {gas_used})"
            )
            return decision

        except Exception as e:
            logger.error(f"Commit gate validation error: {e}", exc_info=True)
            return PolicyDecision(
                allowed=False,
                gate=PolicyGate.COMMIT_GATE,
                reason=f"Commit gate error: {str(e)}",
            )

    def _make_cache_key(self, envelope: Dict[str, Any]) -> str:
        """Create cache key from envelope"""
        op_type = self._resolve_operation(envelope)
        agent_id = self._resolve_agent_id(envelope)
        return f"{op_type}:{agent_id}"

    def _extract_policy_input(self, envelope: Dict[str, Any], gate: PolicyGate) -> Dict[str, Any]:
        """Extract policy input from envelope for given gate"""
        operation = self._resolve_operation(envelope)
        agent_id = self._resolve_agent_id(envelope)
        kind = envelope.get("kind") or operation
        payload = envelope.get("payload", {})

        try:
            payload_size = len(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            )
        except Exception:
            payload_size = 0

        return {
            "gate": gate.value,
            "operation": operation,
            "kind": kind,
            "agent_id": agent_id,
            "actor_id": envelope.get("actor_id") or agent_id,
            "thread_id": envelope.get("thread_id"),
            "payload": payload,
            "payload_size": envelope.get("payload_size", payload_size),
            "lamport": envelope.get("lamport", 0),
            "signature": envelope.get("signature") or envelope.get("sig_b64"),
            "timestamp": envelope.get("timestamp") or envelope.get("ts_ns"),
        }

    def _resolve_operation(self, envelope: Dict[str, Any]) -> str:
        return str(envelope.get("operation") or envelope.get("kind") or "unknown")

    def _resolve_agent_id(self, envelope: Dict[str, Any]) -> str:
        return str(
            envelope.get("agent_id")
            or envelope.get("actor_id")
            or envelope.get("sender_pk_b64")
            or "unknown"
        )

    def _check_resource_violations(
        self, envelope: Dict[str, Any], telemetry: Dict[str, Any]
    ) -> Optional[str]:
        """
        Check if actual resource usage violates claimed resources.

        Args:
            envelope: Message with claimed resources
            telemetry: Actual execution telemetry

        Returns:
            String describing violations, or None if no violations
        """
        violations = []

        payload = envelope.get("payload", {})
        claimed_resources = payload.get("resources", {})
        actual_resources = telemetry.get("resources", {})

        # Check CPU time
        claimed_cpu = claimed_resources.get("cpu_ms", float("inf"))
        actual_cpu = actual_resources.get("cpu_ms", 0)
        if actual_cpu > claimed_cpu * 1.1:  # Allow 10% margin
            violations.append(f"CPU exceeded: claimed {claimed_cpu}ms, actual {actual_cpu}ms")

        # Check memory
        claimed_mem = claimed_resources.get("memory_mb", float("inf"))
        actual_mem = actual_resources.get("memory_mb", 0)
        if actual_mem > claimed_mem * 1.1:  # Allow 10% margin
            violations.append(f"Memory exceeded: claimed {claimed_mem}MB, actual {actual_mem}MB")

        # Check gas
        claimed_gas = claimed_resources.get("gas", float("inf"))
        actual_gas = actual_resources.get("gas", 0)
        if actual_gas > claimed_gas * 1.1:  # Allow 10% margin
            violations.append(f"Gas exceeded: claimed {claimed_gas}, actual {actual_gas}")

        return "; ".join(violations) if violations else None

    def clear_cache(self):
        """Clear the preflight cache"""
        self._preflight_cache.clear()
        logger.info("Preflight cache cleared")
