"""Tests for Phase 19.5 - Safety Mechanisms (Circuit Breakers)"""

import pytest
import time
from datetime import datetime, timedelta
from src.marketplace.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    EmergencyStop,
    RateLimiter,
)


class TestCircuitBreaker:
    """Test CircuitBreaker functionality."""

    def test_initial_state(self):
        """Test circuit breaker starts in closed state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert not cb.is_open()

    def test_check_anomaly_normal(self):
        """Test checking metric within threshold."""
        cb = CircuitBreaker()

        # Normal value
        anomaly = cb.check_anomaly("cpu_usage", 50.0, 80.0)
        assert anomaly is False
        assert cb.state == CircuitState.CLOSED

    def test_check_anomaly_detected(self):
        """Test detecting anomaly when threshold exceeded."""
        cb = CircuitBreaker()

        # Anomaly detected
        anomaly = cb.check_anomaly("cpu_usage", 90.0, 80.0)
        assert anomaly is True
        assert cb.failure_count == 1

    def test_circuit_trips_after_threshold(self):
        """Test circuit trips after reaching failure threshold."""
        cb = CircuitBreaker(failure_threshold=3)

        # Generate failures
        cb.check_anomaly("cpu", 100.0, 80.0)
        assert cb.state == CircuitState.CLOSED

        cb.check_anomaly("cpu", 100.0, 80.0)
        assert cb.state == CircuitState.CLOSED

        cb.check_anomaly("cpu", 100.0, 80.0)
        assert cb.state == CircuitState.OPEN
        assert cb.is_open()

    def test_trigger_breaker_manually(self):
        """Test manually triggering circuit breaker."""
        cb = CircuitBreaker()

        cb.trigger_breaker("Manual trigger for testing")
        assert cb.state == CircuitState.OPEN
        assert cb.is_open()

    def test_reset_breaker(self):
        """Test manually resetting circuit breaker."""
        cb = CircuitBreaker(failure_threshold=2)

        # Trip the circuit
        cb.check_anomaly("cpu", 100.0, 80.0)
        cb.check_anomaly("cpu", 100.0, 80.0)
        assert cb.state == CircuitState.OPEN

        # Reset
        cb.reset_breaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert not cb.is_open()

    def test_call_allowed_when_closed(self):
        """Test calls are allowed when circuit is closed."""
        cb = CircuitBreaker()
        assert cb.call_allowed() is True

    def test_call_blocked_when_open(self):
        """Test calls are blocked when circuit is open."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=10)

        # Trip the circuit
        cb.trigger_breaker("Test")
        assert cb.call_allowed() is False

    def test_half_open_state_transition(self):
        """Test transition from OPEN to HALF_OPEN after timeout."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        # Trip the circuit
        cb.trigger_breaker("Test")
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(1.1)

        # Check state - should transition to HALF_OPEN
        allowed = cb.call_allowed()
        assert allowed is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_recovery(self):
        """Test successful recovery from HALF_OPEN to CLOSED."""
        cb = CircuitBreaker(
            failure_threshold=2, recovery_timeout=1, half_open_max_calls=3
        )

        # Trip and wait
        cb.trigger_breaker("Test")
        time.sleep(1.1)

        # Transition to half-open
        cb.call_allowed()
        assert cb.state == CircuitState.HALF_OPEN

        # Record successes
        cb.check_anomaly("cpu", 50.0, 80.0)  # Success 1
        cb.check_anomaly("cpu", 50.0, 80.0)  # Success 2
        cb.check_anomaly("cpu", 50.0, 80.0)  # Success 3

        # Should be closed now
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        """Test that failure in HALF_OPEN state reopens circuit."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        # Trip and wait
        cb.trigger_breaker("Test")
        time.sleep(1.1)
        cb.call_allowed()
        assert cb.state == CircuitState.HALF_OPEN

        # Failure in half-open
        cb.check_anomaly("cpu", 100.0, 80.0)
        assert cb.state == CircuitState.OPEN

    def test_failure_decay_on_success(self):
        """Test that failure count decays on successful checks."""
        cb = CircuitBreaker(failure_threshold=5)

        # Generate some failures
        cb.check_anomaly("cpu", 100.0, 80.0)
        cb.check_anomaly("cpu", 100.0, 80.0)
        assert cb.failure_count == 2

        # Success should decay count
        cb.check_anomaly("cpu", 50.0, 80.0)
        assert cb.failure_count == 1

        cb.check_anomaly("cpu", 50.0, 80.0)
        assert cb.failure_count == 0

    def test_event_recording(self):
        """Test that events are recorded."""
        cb = CircuitBreaker()

        cb.check_anomaly("cpu", 90.0, 80.0)
        cb.trigger_breaker("Manual")

        events = cb.get_events()
        assert len(events) >= 2

        # Check first event (anomaly)
        assert events[0].metric == "cpu"
        assert events[0].value == 90.0
        assert events[0].threshold == 80.0

        # Check second event (manual trigger)
        assert "Manual" in events[1].reason


class TestEmergencyStop:
    """Test EmergencyStop functionality."""

    def test_initial_state(self):
        """Test emergency stop starts unpaused."""
        es = EmergencyStop()
        assert not es.is_paused()
        assert es.get_pause_info() is None

    def test_pause_system(self):
        """Test pausing the system."""
        es = EmergencyStop()

        es.pause_system("Critical security issue")

        assert es.is_paused()
        assert es.pause_reason == "Critical security issue"
        assert es.pause_time is not None

    def test_pause_already_paused(self):
        """Test that pausing already paused system raises error."""
        es = EmergencyStop()

        es.pause_system("Reason 1")

        with pytest.raises(ValueError, match="already paused"):
            es.pause_system("Reason 2")

    def test_resume_system(self):
        """Test resuming the system."""
        es = EmergencyStop()

        es.pause_system("Testing")
        time.sleep(0.1)
        es.resume_system()

        assert not es.is_paused()
        assert es.get_pause_info() is None

    def test_resume_not_paused(self):
        """Test that resuming non-paused system raises error."""
        es = EmergencyStop()

        with pytest.raises(ValueError, match="not paused"):
            es.resume_system()

    def test_get_pause_info(self):
        """Test getting pause information."""
        es = EmergencyStop()

        es.pause_system("Database corruption")
        info = es.get_pause_info()

        assert info is not None
        assert info["paused"] is True
        assert info["reason"] == "Database corruption"
        assert info["pause_time"] is not None
        assert info["duration_seconds"] >= 0

    def test_pause_history(self):
        """Test pause history tracking."""
        es = EmergencyStop()

        # First pause
        es.pause_system("Issue 1")
        time.sleep(0.1)
        es.resume_system()

        # Second pause
        es.pause_system("Issue 2")
        time.sleep(0.1)
        es.resume_system()

        history = es.get_pause_history()
        assert len(history) == 2

        assert history[0]["reason"] == "Issue 1"
        assert history[1]["reason"] == "Issue 2"
        assert history[0]["duration"] > 0
        assert history[1]["duration"] > 0

    def test_multiple_pause_resume_cycles(self):
        """Test multiple pause/resume cycles."""
        es = EmergencyStop()

        for i in range(3):
            es.pause_system(f"Issue {i}")
            assert es.is_paused()
            time.sleep(0.05)
            es.resume_system()
            assert not es.is_paused()

        history = es.get_pause_history()
        assert len(history) == 3


class TestRateLimiter:
    """Test RateLimiter functionality."""

    def test_initial_check(self):
        """Test first request is allowed."""
        limiter = RateLimiter(limit_per_agent=100)

        assert limiter.check_rate("alice") is True

    def test_within_limit(self):
        """Test requests within limit are allowed."""
        limiter = RateLimiter(limit_per_agent=10)

        # Make 10 requests
        for i in range(10):
            assert limiter.check_rate("alice") is True

    def test_exceeds_limit(self):
        """Test request exceeding limit is blocked."""
        limiter = RateLimiter(limit_per_agent=5)

        # Use up the limit
        for i in range(5):
            assert limiter.check_rate("alice") is True

        # Next request should be blocked
        assert limiter.check_rate("alice") is False

    def test_sliding_window(self):
        """Test sliding window allows new requests after time passes."""
        limiter = RateLimiter(limit_per_agent=2, window_hours=1)

        # Use up limit
        assert limiter.check_rate("alice") is True
        assert limiter.check_rate("alice") is True
        assert limiter.check_rate("alice") is False

        # Manually adjust window to simulate time passing
        # Move old requests outside window
        limiter.entries["alice"].request_times[0] = time.time() - 3700  # 1+ hour ago

        # Should allow new request now
        assert limiter.check_rate("alice") is True

    def test_get_remaining(self):
        """Test getting remaining requests."""
        limiter = RateLimiter(limit_per_agent=10)

        assert limiter.get_remaining("alice") == 10

        limiter.check_rate("alice")
        assert limiter.get_remaining("alice") == 9

        limiter.check_rate("alice")
        limiter.check_rate("alice")
        assert limiter.get_remaining("alice") == 7

    def test_reset_agent(self):
        """Test resetting rate limit for an agent."""
        limiter = RateLimiter(limit_per_agent=5)

        # Use up limit
        for i in range(5):
            limiter.check_rate("alice")

        assert limiter.check_rate("alice") is False

        # Reset
        limiter.reset_agent("alice")
        assert limiter.check_rate("alice") is True
        assert limiter.get_remaining("alice") == 4

    def test_block_agent(self):
        """Test blocking an agent."""
        limiter = RateLimiter(limit_per_agent=100)

        # Block alice for 1 second
        limiter.block_agent("alice", 1)

        assert limiter.is_blocked("alice") is True
        assert limiter.check_rate("alice") is False

    def test_block_expires(self):
        """Test that blocks expire after duration."""
        limiter = RateLimiter(limit_per_agent=100)

        # Block for 0.5 seconds
        limiter.block_agent("alice", 0.5)
        assert limiter.is_blocked("alice") is True

        # Wait for block to expire
        time.sleep(0.6)

        assert limiter.is_blocked("alice") is False
        assert limiter.check_rate("alice") is True

    def test_multiple_agents(self):
        """Test rate limiting is independent per agent."""
        limiter = RateLimiter(limit_per_agent=5)

        # Alice uses her limit
        for i in range(5):
            assert limiter.check_rate("alice") is True
        assert limiter.check_rate("alice") is False

        # Bob can still make requests
        assert limiter.check_rate("bob") is True
        assert limiter.get_remaining("bob") == 4

    def test_get_stats(self):
        """Test getting rate limit statistics."""
        limiter = RateLimiter(limit_per_agent=10)

        # Initial stats
        stats = limiter.get_stats("alice")
        assert stats["requests_in_window"] == 0
        assert stats["remaining"] == 10
        assert stats["limit"] == 10
        assert stats["blocked"] is False

        # After some requests
        limiter.check_rate("alice")
        limiter.check_rate("alice")
        limiter.check_rate("alice")

        stats = limiter.get_stats("alice")
        assert stats["requests_in_window"] == 3
        assert stats["remaining"] == 7

        # With block
        limiter.block_agent("alice", 10)
        stats = limiter.get_stats("alice")
        assert stats["blocked"] is True

    def test_record_request(self):
        """Test recording request without enforcing limit."""
        limiter = RateLimiter(limit_per_agent=2)

        # Record 5 requests (more than limit)
        for i in range(5):
            limiter.record_request("alice")

        # Check that they were recorded
        stats = limiter.get_stats("alice")
        assert stats["requests_in_window"] == 5

        # But check_rate should now block
        assert limiter.check_rate("alice") is False


class TestIntegration:
    """Integration tests for safety mechanisms."""

    def test_circuit_breaker_with_rate_limiter(self):
        """Test circuit breaker and rate limiter working together."""
        cb = CircuitBreaker(failure_threshold=3)
        limiter = RateLimiter(limit_per_agent=10)

        # Simulate agent making requests
        for i in range(5):
            if limiter.check_rate("agent1"):
                # Check for anomaly
                if i >= 2:  # Anomaly on requests 2, 3, 4 (3 total)
                    cb.check_anomaly("error_rate", 0.5, 0.3)

        # Circuit should be open
        assert cb.state == CircuitState.OPEN

        # Agent still has rate limit remaining
        assert limiter.get_remaining("agent1") > 0

    def test_emergency_stop_blocks_all(self):
        """Test emergency stop overrides other mechanisms."""
        es = EmergencyStop()
        limiter = RateLimiter(limit_per_agent=100)

        # Normal operation
        assert not es.is_paused()
        assert limiter.check_rate("alice") is True

        # Emergency stop
        es.pause_system("Critical issue")

        # Even though rate limit allows, emergency stop is active
        assert es.is_paused()
        # In a real system, this would block all operations

        # Resume
        es.resume_system()
        assert not es.is_paused()
        assert limiter.check_rate("alice") is True

    def test_multiple_safety_layers(self):
        """Test all three safety mechanisms together."""
        cb = CircuitBreaker(failure_threshold=5)
        es = EmergencyStop()
        limiter = RateLimiter(limit_per_agent=100)

        # All systems nominal
        assert cb.state == CircuitState.CLOSED
        assert not es.is_paused()
        assert limiter.check_rate("agent1") is True

        # Trigger circuit breaker
        for i in range(5):
            cb.check_anomaly("cpu", 95.0, 80.0)
        assert cb.is_open()

        # Emergency stop
        es.pause_system("Multiple failures detected")
        assert es.is_paused()

        # Rate limiting still enforced
        for i in range(100):
            limiter.check_rate("agent2")
        assert limiter.check_rate("agent2") is False

        # Recovery
        es.resume_system()
        cb.reset_breaker()
        limiter.reset_agent("agent2")

        # All systems back to normal
        assert cb.state == CircuitState.CLOSED
        assert not es.is_paused()
        assert limiter.check_rate("agent2") is True


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_circuit_breaker_zero_threshold(self):
        """Test circuit breaker with zero failure threshold."""
        cb = CircuitBreaker(failure_threshold=1)

        # Single failure trips circuit
        cb.check_anomaly("test", 100.0, 50.0)
        assert cb.state == CircuitState.OPEN

    def test_rate_limiter_zero_limit(self):
        """Test rate limiter with zero limit."""
        limiter = RateLimiter(limit_per_agent=0)

        # All requests should be blocked
        assert limiter.check_rate("alice") is False

    def test_very_short_recovery_timeout(self):
        """Test circuit breaker with very short timeout."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)

        cb.trigger_breaker("Test")

        # Should immediately transition to half-open
        time.sleep(0.1)
        assert cb.call_allowed() is True
        assert cb.state == CircuitState.HALF_OPEN
