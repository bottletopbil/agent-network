"""
OPA-style Policy Engine

Pure Python implementation of policy evaluation with Rego-like semantics.
Provides policy validation without requiring OPA binary installation.

Since OPA is not available, this implements a Python-based policy engine
that can evaluate policies defined in Python with similar semantics.
"""

import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PolicyResult:
    """Result of policy evaluation"""

    allowed: bool
    reasons: List[str]
    gas_used: int = 0  # For future metering
    policy_version: str = "1.0.0"


class BasePolicyEngine:
    """
    Base policy engine implementing CAN Swarm validation rules.

    Validates:
    - Allowed message kinds
    - Payload size limits
    - Required fields
    """

    # Allowed message kinds in CAN Swarm protocol
    ALLOWED_KINDS = {
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
    }

    # Maximum payload size (1MB)
    MAX_PAYLOAD_SIZE = 1048576

    # Required envelope fields
    REQUIRED_FIELDS = {"kind", "thread_id", "lamport", "actor_id"}

    def __init__(self, policy_path: Optional[Path] = None):
        """
        Initialize policy engine.

        Args:
            policy_path: Optional path to policy directory (for future Rego support)
        """
        self.policy_path = policy_path
        logger.info(f"Policy engine initialized (version 1.0.0)")

    def evaluate(self, envelope: Dict[str, Any]) -> PolicyResult:
        """
        Evaluate envelope against policy.

        Args:
            envelope: Envelope to validate

        Returns:
            PolicyResult with allow/deny decision and reasons
        """
        reasons = []
        allowed = True

        # Check message kind
        kind = envelope.get("kind")
        if kind not in self.ALLOWED_KINDS:
            allowed = False
            reasons.append(f"Invalid message kind: {kind}")

        # Check payload size
        payload_size = envelope.get("payload_size", 0)
        if payload_size >= self.MAX_PAYLOAD_SIZE:
            allowed = False
            reasons.append(
                f"Payload too large: {payload_size} bytes (max: {self.MAX_PAYLOAD_SIZE})"
            )

        # Check required fields
        missing_fields = self.REQUIRED_FIELDS - set(envelope.keys())
        if missing_fields:
            allowed = False
            reasons.append(f"Missing required fields: {', '.join(missing_fields)}")

        # If allowed, provide confirmation reason
        if allowed:
            reasons.append(f"Envelope passes all policy checks")

        return PolicyResult(
            allowed=allowed,
            reasons=reasons,
            gas_used=len(envelope),  # Simple gas metering
            policy_version="1.0.0",
        )

    def evaluate_batch(self, envelopes: List[Dict]) -> List[PolicyResult]:
        """
        Evaluate multiple envelopes.

        Args:
            envelopes: List of envelopes to validate

        Returns:
            List of PolicyResults
        """
        return [self.evaluate(env) for env in envelopes]


class OPAEngine(BasePolicyEngine):
    """
    OPA-compatible policy engine.

    Uses subprocess to call OPA binary if available,
    falls back to Python-based implementation if not.
    """

    def __init__(
        self, policy_path: Optional[Path] = None, use_opa_binary: bool = False
    ):
        """
        Initialize OPA engine.

        Args:
            policy_path: Path to policy directory
            use_opa_binary: If True, attempt to use OPA binary
        """
        super().__init__(policy_path)

        self.use_opa_binary = use_opa_binary
        self.opa_available = False

        if use_opa_binary:
            self.opa_available = self._check_opa_binary()

        if self.use_opa_binary and not self.opa_available:
            logger.warning(
                "OPA binary requested but not available, "
                "falling back to Python implementation"
            )

    def _check_opa_binary(self) -> bool:
        """Check if OPA binary is available"""
        import subprocess

        try:
            result = subprocess.run(["opa", "version"], capture_output=True, timeout=5)
            if result.returncode == 0:
                logger.info("OPA binary available")
                return True
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return False

    def evaluate(self, envelope: Dict[str, Any]) -> PolicyResult:
        """
        Evaluate envelope against policy.

        Uses OPA binary if available, otherwise falls back to Python.

        Args:
            envelope: Envelope to validate

        Returns:
            PolicyResult
        """
        if self.use_opa_binary and self.opa_available:
            return self._evaluate_with_opa(envelope)
        else:
            return super().evaluate(envelope)

    def _evaluate_with_opa(self, envelope: Dict) -> PolicyResult:
        """
        Evaluate using OPA binary.

        Args:
            envelope: Envelope to validate

        Returns:
            PolicyResult
        """
        import subprocess
        import json

        try:
            # Prepare input
            input_data = {"input": envelope}

            # Call OPA eval
            cmd = [
                "opa",
                "eval",
                "--data",
                str(self.policy_path / "base.rego"),
                "--input",
                "-",
                "--format",
                "json",
                "data.swarm.policy.allow",
            ]

            result = subprocess.run(
                cmd,
                input=json.dumps(input_data).encode(),
                capture_output=True,
                timeout=5,
            )

            if result.returncode == 0:
                output = json.loads(result.stdout)
                allowed = (
                    output.get("result", [{}])[0]
                    .get("expressions", [{}])[0]
                    .get("value", False)
                )

                return PolicyResult(
                    allowed=allowed,
                    reasons=[f"OPA evaluation: {'allowed' if allowed else 'denied'}"],
                    gas_used=len(envelope),
                )
            else:
                logger.error(f"OPA evaluation failed: {result.stderr}")
                # Fall back to Python
                return super().evaluate(envelope)

        except Exception as e:
            logger.error(f"Error calling OPA: {e}")
            # Fall back to Python
            return super().evaluate(envelope)


# Singleton for easy access
_policy_engine: Optional[OPAEngine] = None


def get_policy_engine() -> OPAEngine:
    """Get global policy engine instance"""
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = OPAEngine()
    return _policy_engine


def init_policy_engine(
    policy_path: Optional[Path] = None, use_opa_binary: bool = False
) -> OPAEngine:
    """
    Initialize global policy engine.

    Args:
        policy_path: Path to policy directory
        use_opa_binary: Whether to use OPA binary

    Returns:
        OPAEngine instance
    """
    global _policy_engine
    _policy_engine = OPAEngine(policy_path, use_opa_binary)
    return _policy_engine
