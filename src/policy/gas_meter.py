"""
Gas Metering for Policy Execution

Tracks computational cost of policy evaluation to prevent
denial-of-service attacks and ensure fair resource usage.

Metering Strategy:
- Each operation costs gas
- Configurable limits
- Raises exception when exceeded
"""

import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class GasExceededError(Exception):
    """Raised when gas limit is exceeded"""

    pass


@dataclass
class GasMetrics:
    """Gas usage metrics"""

    used: int = 0
    limit: int = 100000
    operations: int = 0

    def percent_used(self) -> float:
        """Calculate percentage of gas used"""
        return (self.used / self.limit) * 100 if self.limit > 0 else 0.0

    def remaining(self) -> int:
        """Calculate remaining gas"""
        return max(0, self.limit - self.used)


class GasMeter:
    """
    Tracks gas consumption during policy evaluation.

    Gas costs:
    - Field access: 1 gas
    - Comparison: 2 gas
    - Set membership: 5 gas
    - Iteration: 10 gas per item
    """

    # Gas costs for different operations
    COST_FIELD_ACCESS = 1
    COST_COMPARISON = 2
    COST_SET_MEMBERSHIP = 5
    COST_ITERATION_PER_ITEM = 10
    COST_FUNCTION_CALL = 20

    def __init__(self, gas_limit: int = 100000):
        """
        Initialize gas meter.

        Args:
            gas_limit: Maximum gas allowed (default: 100k)
        """
        self.limit = gas_limit
        self.used = 0
        self.operations = 0
        self._enabled = True

        logger.debug(f"GasMeter initialized with limit: {gas_limit}")

    def consume(self, amount: int, operation: Optional[str] = None) -> None:
        """
        Consume gas.

        Args:
            amount: Gas to consume
            operation: Optional operation name for debugging

        Raises:
            GasExceededError: If gas limit exceeded (and not disabled)
        """
        # Always track usage
        self.used += amount
        self.operations += 1

        if operation:
            logger.debug(
                f"Gas consumed: {amount} for {operation} (total: {self.used}/{self.limit})"
            )

        # Only enforce limit if enabled
        if self._enabled and self.used > self.limit:
            raise GasExceededError(
                f"Gas limit exceeded: {self.used} > {self.limit} "
                f"(operation: {operation or 'unknown'})"
            )

    def consume_field_access(self, field_name: Optional[str] = None) -> None:
        """Consume gas for field access"""
        self.consume(self.COST_FIELD_ACCESS, f"field_access:{field_name or 'unknown'}")

    def consume_comparison(self) -> None:
        """Consume gas for comparison operation"""
        self.consume(self.COST_COMPARISON, "comparison")

    def consume_set_membership(self) -> None:
        """Consume gas for set membership check"""
        self.consume(self.COST_SET_MEMBERSHIP, "set_membership")

    def consume_iteration(self, item_count: int) -> None:
        """Consume gas for iteration"""
        cost = self.COST_ITERATION_PER_ITEM * item_count
        self.consume(cost, f"iteration:{item_count}_items")

    def consume_function_call(self, function_name: Optional[str] = None) -> None:
        """Consume gas for function call"""
        self.consume(self.COST_FUNCTION_CALL, f"function:{function_name or 'unknown'}")

    def get_metrics(self) -> GasMetrics:
        """
        Get current gas metrics.

        Returns:
            GasMetrics with current usage
        """
        return GasMetrics(used=self.used, limit=self.limit, operations=self.operations)

    def reset(self) -> None:
        """Reset gas meter"""
        self.used = 0
        self.operations = 0
        logger.debug("GasMeter reset")

    def disable(self) -> None:
        """Disable gas metering (for testing)"""
        self._enabled = False
        logger.debug("GasMeter disabled")

    def enable(self) -> None:
        """Enable gas metering"""
        self._enabled = True
        logger.debug("GasMeter enabled")

    def check_limit(self) -> None:
        """
        Check if gas limit exceeded.

        Raises:
            GasExceededError: If limit exceeded
        """
        if self._enabled and self.used > self.limit:
            raise GasExceededError(f"Gas limit exceeded: {self.used} > {self.limit}")

    def estimate_remaining_operations(self, cost_per_op: int) -> int:
        """
        Estimate how many operations can still be performed.

        Args:
            cost_per_op: Gas cost per operation

        Returns:
            Number of operations that can be performed
        """
        remaining = self.limit - self.used
        if cost_per_op <= 0:
            return 0
        return max(0, remaining // cost_per_op)
