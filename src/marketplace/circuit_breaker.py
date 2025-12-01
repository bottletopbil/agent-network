"""Phase 19.5 - Safety Mechanisms

This module implements circuit breakers, emergency stop functionality,
and rate limiting to protect the system from anomalies and abuse.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from enum import Enum
import time


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Tripped, blocking requests
    HALF_OPEN = "half_open"  # Testing if system recovered


@dataclass
class CircuitBreakerEvent:
    """Record of a circuit breaker event."""

    timestamp: datetime
    reason: str
    metric: Optional[str] = None
    value: Optional[float] = None
    threshold: Optional[float] = None


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for fault tolerance.

    Monitors metrics and automatically trips when anomalies are detected,
    preventing cascading failures.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            half_open_max_calls: Max calls to test in half-open state
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = timedelta(seconds=recovery_timeout)
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.trip_time: Optional[datetime] = None
        self.half_open_calls = 0

        self.events: List[CircuitBreakerEvent] = []

    def check_anomaly(self, metric: str, value: float, threshold: float) -> bool:
        """
        Check if a metric exceeds threshold (anomaly detection).

        Args:
            metric: Name of the metric being checked
            value: Current value of the metric
            threshold: Threshold value

        Returns:
            True if anomaly detected (value > threshold)
        """
        anomaly = value > threshold

        if anomaly:
            self._record_failure(metric, value, threshold)
        else:
            self._record_success()

        return anomaly

    def trigger_breaker(self, reason: str):
        """
        Manually trigger the circuit breaker.

        Args:
            reason: Reason for triggering the breaker
        """
        self._trip_circuit(reason)

    def reset_breaker(self):
        """Manually reset the circuit breaker to closed state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.half_open_calls = 0
        self.last_failure_time = None
        self.trip_time = None

    def is_open(self) -> bool:
        """Check if circuit is open (tripped)."""
        # Check if we should transition from OPEN to HALF_OPEN
        if self.state == CircuitState.OPEN:
            if (
                self.trip_time
                and datetime.now() - self.trip_time >= self.recovery_timeout
            ):
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return False
            return True

        return False

    def call_allowed(self) -> bool:
        """
        Check if a call is allowed through the circuit.

        Returns:
            True if call should proceed, False if blocked by circuit
        """
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if (
                self.trip_time
                and datetime.now() - self.trip_time >= self.recovery_timeout
            ):
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Allow limited calls to test recovery
            if self.half_open_calls < self.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False

        return False

    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        # Update state if needed
        self.is_open()
        return self.state

    def get_events(self, limit: Optional[int] = None) -> List[CircuitBreakerEvent]:
        """Get recent circuit breaker events."""
        if limit:
            return self.events[-limit:]
        return self.events.copy()

    def _record_failure(self, metric: str, value: float, threshold: float):
        """Record a failure and potentially trip the circuit."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        event = CircuitBreakerEvent(
            timestamp=self.last_failure_time,
            reason=f"Metric {metric} exceeded threshold",
            metric=metric,
            value=value,
            threshold=threshold,
        )
        self.events.append(event)

        if self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open state reopens circuit
            self._trip_circuit(f"Failure during recovery test: {metric}")
        elif self.failure_count >= self.failure_threshold:
            self._trip_circuit(f"Failure threshold reached: {metric}")

    def _record_success(self):
        """Record a successful check."""
        if self.state == CircuitState.HALF_OPEN:
            # Success in half-open state
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                # Recovered successfully
                self.reset_breaker()
        elif self.state == CircuitState.CLOSED:
            # Decay failure count on success
            if self.failure_count > 0:
                self.failure_count = max(0, self.failure_count - 1)

    def _trip_circuit(self, reason: str):
        """Trip the circuit to open state."""
        self.state = CircuitState.OPEN
        self.trip_time = datetime.now()

        event = CircuitBreakerEvent(timestamp=self.trip_time, reason=reason)
        self.events.append(event)


class EmergencyStop:
    """
    Emergency stop mechanism for system-wide pausing.

    Provides ability to immediately halt operations in case of
    critical issues or security incidents.
    """

    def __init__(self):
        self.paused = False
        self.pause_reason: Optional[str] = None
        self.pause_time: Optional[datetime] = None
        self.resume_time: Optional[datetime] = None
        self.pause_history: List[Dict] = []

    def pause_system(self, reason: str):
        """
        Pause the system (emergency stop).

        Args:
            reason: Reason for pausing the system
        """
        if self.paused:
            raise ValueError("System is already paused")

        self.paused = True
        self.pause_reason = reason
        self.pause_time = datetime.now()
        self.resume_time = None

    def resume_system(self):
        """Resume normal operation after a pause."""
        if not self.paused:
            raise ValueError("System is not paused")

        self.resume_time = datetime.now()

        # Record in history
        self.pause_history.append(
            {
                "reason": self.pause_reason,
                "pause_time": self.pause_time,
                "resume_time": self.resume_time,
                "duration": (self.resume_time - self.pause_time).total_seconds(),
            }
        )

        self.paused = False
        self.pause_reason = None
        self.pause_time = None

    def is_paused(self) -> bool:
        """Check if system is currently paused."""
        return self.paused

    def get_pause_info(self) -> Optional[Dict]:
        """Get information about current pause, if any."""
        if not self.paused:
            return None

        return {
            "paused": True,
            "reason": self.pause_reason,
            "pause_time": self.pause_time,
            "duration_seconds": (
                (datetime.now() - self.pause_time).total_seconds()
                if self.pause_time
                else 0
            ),
        }

    def get_pause_history(self) -> List[Dict]:
        """Get history of all pauses."""
        return self.pause_history.copy()


@dataclass
class RateLimitEntry:
    """Track rate limit for an agent."""

    agent_id: str
    request_times: List[float] = field(default_factory=list)


class RateLimiter:
    """
    Rate limiter to prevent abuse and ensure fair resource allocation.

    Implements sliding window rate limiting per agent.
    """

    def __init__(self, limit_per_agent: int = 100, window_hours: int = 1):
        """
        Initialize rate limiter.

        Args:
            limit_per_agent: Maximum requests per agent in the time window
            window_hours: Time window in hours (default: 1 hour)
        """
        self.limit_per_agent = limit_per_agent
        self.window_seconds = window_hours * 3600

        self.entries: Dict[str, RateLimitEntry] = {}
        self.blocked_agents: Dict[str, float] = {}  # agent_id -> block_until_timestamp

    def check_rate(self, agent_id: str) -> bool:
        """
        Check if agent is within rate limit.

        Args:
            agent_id: ID of the agent

        Returns:
            True if within rate limit, False if exceeded
        """
        current_time = time.time()

        # Check if agent is blocked
        if agent_id in self.blocked_agents:
            if current_time < self.blocked_agents[agent_id]:
                return False
            else:
                # Unblock agent
                del self.blocked_agents[agent_id]

        # Get or create entry
        if agent_id not in self.entries:
            self.entries[agent_id] = RateLimitEntry(agent_id=agent_id)

        entry = self.entries[agent_id]

        # Remove old requests outside the window
        cutoff_time = current_time - self.window_seconds
        entry.request_times = [t for t in entry.request_times if t > cutoff_time]

        # Check if under limit
        if len(entry.request_times) < self.limit_per_agent:
            entry.request_times.append(current_time)
            return True
        else:
            return False

    def record_request(self, agent_id: str):
        """
        Record a request from an agent.

        This is an alternative to check_rate that doesn't enforce the limit,
        just records the request.

        Args:
            agent_id: ID of the agent
        """
        current_time = time.time()

        if agent_id not in self.entries:
            self.entries[agent_id] = RateLimitEntry(agent_id=agent_id)

        self.entries[agent_id].request_times.append(current_time)

    def get_remaining(self, agent_id: str) -> int:
        """
        Get remaining requests in current window for an agent.

        Args:
            agent_id: ID of the agent

        Returns:
            Number of requests remaining
        """
        if agent_id not in self.entries:
            return self.limit_per_agent

        current_time = time.time()
        cutoff_time = current_time - self.window_seconds

        entry = self.entries[agent_id]
        recent_requests = [t for t in entry.request_times if t > cutoff_time]

        return max(0, self.limit_per_agent - len(recent_requests))

    def reset_agent(self, agent_id: str):
        """Reset rate limit for a specific agent."""
        if agent_id in self.entries:
            self.entries[agent_id].request_times.clear()
        if agent_id in self.blocked_agents:
            del self.blocked_agents[agent_id]

    def block_agent(self, agent_id: str, duration_seconds: int):
        """
        Temporarily block an agent from making requests.

        Args:
            agent_id: ID of the agent to block
            duration_seconds: How long to block the agent
        """
        block_until = time.time() + duration_seconds
        self.blocked_agents[agent_id] = block_until

    def is_blocked(self, agent_id: str) -> bool:
        """Check if an agent is currently blocked."""
        if agent_id not in self.blocked_agents:
            return False

        current_time = time.time()
        if current_time >= self.blocked_agents[agent_id]:
            # Block expired
            del self.blocked_agents[agent_id]
            return False

        return True

    def get_stats(self, agent_id: str) -> Dict:
        """
        Get rate limit statistics for an agent.

        Args:
            agent_id: ID of the agent

        Returns:
            Dictionary with stats
        """
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds

        if agent_id not in self.entries:
            return {
                "requests_in_window": 0,
                "remaining": self.limit_per_agent,
                "limit": self.limit_per_agent,
                "blocked": False,
            }

        entry = self.entries[agent_id]
        recent_requests = [t for t in entry.request_times if t > cutoff_time]

        return {
            "requests_in_window": len(recent_requests),
            "remaining": max(0, self.limit_per_agent - len(recent_requests)),
            "limit": self.limit_per_agent,
            "blocked": self.is_blocked(agent_id),
        }
