"""
Exponential Backoff: Retry logic with randomized jitter.
"""

import random


def calculate_backoff(
    attempt: int, base: float = 1.0, max_delay: float = 60.0, jitter: float = 0.5
) -> float:
    """
    Calculate exponential backoff with jitter.

    Args:
        attempt: Retry attempt number (0-indexed)
        base: Base delay in seconds
        max_delay: Maximum delay cap in seconds
        jitter: Jitter range in seconds (±jitter)

    Returns:
        Delay in seconds
    """
    # Exponential: base * 2^attempt
    exponential = base * (2**attempt)

    # Cap at max
    capped = min(exponential, max_delay)

    # Add jitter: random value between -jitter and +jitter
    jittered = capped + random.uniform(-jitter, jitter)

    # Ensure non-negative
    return max(0, jittered)


class RandomizedBackoff:
    """
    Stateful backoff calculator with configurable parameters.

    Tracks attempt count and provides next delay.
    """

    def __init__(self, base: float = 1.0, max_delay: float = 60.0, jitter: float = 0.5):
        """
        Initialize backoff calculator.

        Args:
            base: Base delay in seconds
            max_delay: Maximum delay cap in seconds
            jitter: Jitter range in seconds
        """
        self.base = base
        self.max_delay = max_delay
        self.jitter = jitter
        self.attempt = 0

    def get_delay(self, attempt: int) -> float:
        """
        Get delay for specific attempt.

        Args:
            attempt: Retry attempt number

        Returns:
            Delay in seconds
        """
        return calculate_backoff(attempt, self.base, self.max_delay, self.jitter)

    def next(self) -> float:
        """
        Get next delay and increment attempt counter.

        Returns:
            Delay in seconds
        """
        delay = self.get_delay(self.attempt)
        self.attempt += 1
        return delay

    def reset(self):
        """Reset attempt counter to zero."""
        self.attempt = 0

    def current_attempt(self) -> int:
        """Get current attempt number."""
        return self.attempt
