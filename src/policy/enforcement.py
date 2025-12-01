"""
Policy enforcement utilities to prevent bypass vulnerabilities.

Provides decorators and helpers to ensure policy validation cannot be skipped.
"""

from functools import wraps
from typing import Callable, Any
import logging

logger = logging.getLogger(__name__)


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
        # Import here to avoid circular dependencies
        from bus import get_gate_enforcer

        # Validate envelope structure
        if not isinstance(envelope, dict):
            raise ValueError("Envelope must be a dictionary")

        # Required fields
        required_fields = [
            "thread_id",
            "sender_pk_b64",
            "lamport",
            "operation",
            "payload",
        ]
        missing_fields = [field for field in required_fields if field not in envelope]
        if missing_fields:
            raise ValueError(f"Envelope missing required fields: {missing_fields}")

        # Get gate enforcer and validate
        gate_enforcer = get_gate_enforcer()

        # Use ingress validation (stronger than preflight)
        decision = gate_enforcer.ingress_validate(envelope)

        if not decision.allowed:
            logger.error(
                f"Policy enforcement rejected {envelope.get('operation')}: {decision.reason}"
            )
            raise ValueError(
                f"Policy enforcement failed: {decision.reason}. "
                f"Operation '{envelope.get('operation')}' is not allowed."
            )

        logger.debug(f"Policy validation passed for {envelope.get('operation')}")

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
