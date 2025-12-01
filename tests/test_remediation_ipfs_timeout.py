"""
Test for IPFS timeout and circuit breaker (STAB-004).

Validates that IPFS operations timeout properly and circuit breaker
prevents cascading failures.
"""

import sys
from pathlib import Path
import pytest
import time
import asyncio
from unittest.mock import Mock, patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_ipfs_get_timeout():
    """
    Test that IPFS get() times out instead of hanging.

    Should raise TimeoutError within timeout period.
    """
    from cas.ipfs_store import IPFSContentStore

    # Create mock client that hangs
    mock_client = Mock()
    mock_client.get_content = Mock(side_effect=lambda cid: time.sleep(30))

    store = IPFSContentStore()
    store.client = mock_client

    start = time.time()

    with pytest.raises((TimeoutError, RuntimeError)):
        # Should timeout in 5 seconds, not wait 30
        store.get("QmTestCID", timeout=5)

    elapsed = time.time() - start

    # Should fail fast (within timeout + small buffer)
    assert elapsed < 10, f"Should timeout quickly, took {elapsed}s"
    assert elapsed >= 4, "Should wait at least close to timeout"


def test_ipfs_get_default_timeout():
    """
    Test that default timeout is applied.
    """
    from cas.ipfs_store import IPFSContentStore

    mock_client = Mock()
    # Simulate slow IPFS
    mock_client.get_content = Mock(side_effect=lambda cid: time.sleep(10))

    store = IPFSContentStore()
    store.client = mock_client

    start = time.time()

    with pytest.raises((TimeoutError, RuntimeError)):
        # Use default timeout (should be 5s)
        store.get("QmTestCID")

    elapsed = time.time() - start

    # Should timeout with default (5s + buffer)
    assert elapsed < 10


def test_circuit_breaker_opens_after_failures():
    """
    Test that circuit breaker opens after consecutive failures.
    """
    from cas.ipfs_store import IPFSContentStore

    mock_client = Mock()
    mock_client.get_content = Mock(side_effect=TimeoutError("IPFS timeout"))

    store = IPFSContentStore()
    store.client = mock_client

    # First 3 failures should try IPFS
    for i in range(3):
        with pytest.raises((TimeoutError, RuntimeError)):
            store.get(f"QmTest{i}", timeout=1)

    # Circuit breaker should now be open
    assert store._circuit_breaker_open, "Circuit breaker should open after 3 failures"

    # Next call should fail fast without calling IPFS
    with pytest.raises(RuntimeError):
        store.get("QmTest4", timeout=1)

    # Should not have called get_content again (circuit open)
    assert (
        mock_client.get_content.call_count == 3
    ), "Should not call IPFS when circuit open"


def test_circuit_breaker_closes_after_cooldown():
    """
    Test that circuit breaker closes after cooldown period.
    """
    from cas.ipfs_store import IPFSContentStore

    store = IPFSContentStore()

    # Manually open circuit breaker
    store._circuit_breaker_open = True
    store._circuit_open_time = time.time() - 61  # Opened 61 seconds ago

    # Mock successful response
    mock_client = Mock()
    mock_client.get_content = Mock(return_value=b"test data")
    store.client = mock_client

    # Should try IPFS again (circuit closed after 60s)
    result = store.get("QmTest", timeout=5)

    assert result == b"test data"
    assert not store._circuit_breaker_open, "Circuit should close after cooldown"
    assert store._failure_count == 0, "Failure count should reset on success"


def test_successful_get_resets_failure_count():
    """
    Test that successful get resets the failure counter.
    """
    from cas.ipfs_store import IPFSContentStore

    store = IPFSContentStore()
    store._failure_count = 2  # Had 2 failures

    mock_client = Mock()
    mock_client.get_content = Mock(return_value=b"success")
    store.client = mock_client

    result = store.get("QmTest", timeout=5)

    assert result == b"success"
    assert store._failure_count == 0, "Success should reset failure count"
    assert not store._circuit_breaker_open


def test_circuit_breaker_logs_state_changes():
    """
    Test that circuit breaker logs when opening/closing.
    """
    from cas.ipfs_store import IPFSContentStore

    mock_client = Mock()
    mock_client.get_content = Mock(side_effect=TimeoutError())

    store = IPFSContentStore()
    store.client = mock_client

    with patch("cas.ipfs_store.logger") as mock_logger:
        # Trigger circuit breaker open
        for i in range(3):
            try:
                store.get(f"QmTest{i}", timeout=1)
            except:
                pass

        # Should log warning about circuit opening
        assert mock_logger.warning.called or mock_logger.error.called
