"""
Policy enforcement utilities to prevent bypass vulnerabilities.

Provides decorators and helpers to ensure policy validation cannot be skipped.
"""

from functools import wraps
from typing import Callable, Any
import logging

logger = logging.getLogger(__name__)


class PolicyEnforcementError(ValueError):
    """Raised when ingress policy enforcement fails."""


def _operation_name(envelope: dict) -> str:
    return str(envelope.get("operation") or envelope.get("kind") or "unknown")


def validate_ingress_envelope(
    envelope: dict,
    *,
    source: str = "ingress",
    gate_enforcer=None,
):
    """
    Validate an externally received envelope with fail-closed semantics.

    This is the shared ingress gate for coordinator and transport boundaries.
    """
    if not isinstance(envelope, dict):
        raise PolicyEnforcementError(f"{source}: envelope must be a dictionary")

    required_fields = ["kind", "thread_id", "lamport", "payload"]
    missing_fields = [field for field in required_fields if field not in envelope]
    if missing_fields:
        raise PolicyEnforcementError(f"{source}: envelope missing required fields: {missing_fields}")

    if not any(
        key in envelope and envelope.get(key)
        for key in ("actor_id", "sender_pk_b64", "agent_id")
    ):
        raise PolicyEnforcementError(f"{source}: missing actor identity field")

    if not isinstance(envelope.get("lamport"), int) or envelope.get("lamport", 0) <= 0:
        raise PolicyEnforcementError(f"{source}: invalid lamport value")

    if not isinstance(envelope.get("payload"), dict):
        raise PolicyEnforcementError(f"{source}: payload must be a dictionary")

    # If signature/policy fields are present, require full baseline envelope validation.
    if any(
        key in envelope
        for key in ("policy_engine_hash", "payload_hash", "sig_b64", "sig_pk_b64", "signature")
    ):
        from policy import validate_envelope

        try:
            validate_envelope(envelope)
        except Exception as exc:
            raise PolicyEnforcementError(
                f"{source}: baseline envelope validation failed: {exc}"
            ) from exc

    if gate_enforcer is None:
        # Import lazily to avoid circular dependency.
        from bus import get_gate_enforcer

        gate_enforcer = get_gate_enforcer()

    try:
        decision = gate_enforcer.ingress_validate(envelope)
    except Exception as exc:
        raise PolicyEnforcementError(
            f"{source}: ingress gate evaluation failed: {exc}"
        ) from exc

    if not decision.allowed:
        raise PolicyEnforcementError(
            f"{source}: operation '{_operation_name(envelope)}' denied: {decision.reason}"
        )

    return decision


def require_policy_validation(handler_func: Callable) -> Callable:
    """
    Decorator that enforces policy validation on handler functions.

    This decorator ensures that even if a handler is called directly
    (bypassing the bus), it will still validate the envelope against policy.

    Usage:
        @require_policy_validation
        async def handle_my_operation(envelope: dict):
            # handler logic
            pass

    Args:
        handler_func: The async handler function to wrap

    Returns:
        Wrapped function that enforces policy validation
    """

    @wraps(handler_func)
    async def wrapper(envelope: dict, *args, **kwargs) -> Any:
        """Wrapper that validates envelope before calling handler."""
        decision = validate_ingress_envelope(
            envelope,
            source=f"handler:{handler_func.__name__}",
        )
        logger.debug(
            "Policy validation passed for %s via %s",
            _operation_name(envelope),
            decision.gate.value,
        )

        # Call the actual handler
        return await handler_func(envelope, *args, **kwargs)

    # Mark that this function is wrapped for testing
    wrapper.__wrapped__ = handler_func
    wrapper.__policy_enforced__ = True

    return wrapper


def enforce_strict_validation() -> None:
    """
    Global setting to make all policy validation strict and non-bypassable.

    This can be called at application startup to ensure validation cannot
    be disabled via environment variables or configuration.
    """
    import os

    # Remove any environment variables that might disable validation
    bypass_vars = [
        "SKIP_POLICY_VALIDATION",
        "DISABLE_POLICY",
        "BYPASS_VALIDATION",
        "NO_VALIDATION",
    ]

    for var in bypass_vars:
        if var in os.environ:
            logger.warning(f"Removing insecure environment variable: {var}")
            del os.environ[var]

    logger.info("Strict policy enforcement enabled - validation is mandatory")
