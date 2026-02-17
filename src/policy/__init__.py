"""
Policy management and backward-compatible validation API.
"""

import hashlib
from typing import Any, Dict

from policy.opa_engine import OPAEngine, PolicyResult, BasePolicyEngine


class PolicyError(Exception):
    """Raised when envelope validation fails policy requirements."""


# Legacy v0 payload limit expected by core tests.
_MAX_PAYLOAD_BYTES = 64 * 1024  # 64KB
_LEGACY_ALLOWED_KINDS = {"PLAN", "FINAL"}


def _canonical_payload_size(payload: Dict[str, Any]) -> int:
    """Return canonical JSON payload byte size."""
    import json

    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def current_policy_hash() -> str:
    """
    Return deterministic hash of the active envelope policy contract.

    This keeps legacy callers stable while policy internals evolve.
    """
    contract = {
        "allowed_kinds": sorted(BasePolicyEngine.ALLOWED_KINDS),
        "max_payload_bytes": _MAX_PAYLOAD_BYTES,
        "required_fields": sorted(["kind", "thread_id", "lamport", "payload", "policy_engine_hash"]),
        "version": "legacy-v0-compat",
    }
    import json

    return hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_envelope(envelope: Dict[str, Any]) -> bool:
    """
    Validate signed envelope and enforce baseline policy checks.

    Raises:
        PolicyError: If validation fails.
    """
    from envelope import verify_envelope

    allowed_kinds = set(BasePolicyEngine.ALLOWED_KINDS) | _LEGACY_ALLOWED_KINDS
    kind = envelope.get("kind")
    if kind not in allowed_kinds:
        raise PolicyError("kind not allowed")

    payload = envelope.get("payload", {})
    if _canonical_payload_size(payload) > _MAX_PAYLOAD_BYTES:
        raise PolicyError("payload too large")

    policy_hash = envelope.get("policy_engine_hash")
    if policy_hash != current_policy_hash():
        raise PolicyError("policy_engine_hash mismatch")

    if not verify_envelope(envelope):
        raise PolicyError("signature or payload_hash invalid")

    return True


__all__ = [
    "OPAEngine",
    "PolicyResult",
    "BasePolicyEngine",
    "PolicyError",
    "validate_envelope",
    "current_policy_hash",
]
