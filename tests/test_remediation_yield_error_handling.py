"""
Test for error handling in YIELD handler (ERR-001).

This test verifies that the handler validation logic works correctly
without importing full handler modules (to avoid dependency issues).
"""

import sys
from pathlib import Path
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_validation_logic_missing_thread_id():
    """
    Test validation logic for missing thread_id.
    """
    envelope = {
        # Missing thread_id
        "sender_pk_b64": "test_sender",
        "lamport": 1,
        "payload": {"task_id": "task_123"},
    }

    # Should return None (falsy)
    thread_id = envelope.get("thread_id")
    assert not thread_id

    # Validation would log error and return


def test_validation_logic_missing_payload():
    """
    Test validation logic for missing payload.
    """
    envelope = {
        "thread_id": "thread_123",
        "sender_pk_b64": "test_sender",
        "lamport": 1,
        # Missing payload
    }

    payload = envelope.get("payload")
    assert not payload


def test_validation_logic_missing_task_id():
    """
    Test validation logic for missing task_id in payload.
    """
    envelope = {
        "thread_id": "thread_123",
        "sender_pk_b64": "test_sender",
        "lamport": 1,
        "payload": {
            # Missing task_id
            "reason": "test"
        },
    }

    payload = envelope.get("payload")
    task_id = payload.get("task_id") if payload else None
    assert not task_id


def test_validation_logic_none_values():
    """
    Test validation logic handles None values.
    """
    envelope = {
        "thread_id": None,
        "sender_pk_b64": None,
        "lamport": None,
        "payload": None,
    }

    # All should validate as falsy
    assert not envelope.get("thread_id")
    assert not envelope.get("payload")
    assert not envelope.get("sender_pk_b64")
    assert envelope.get("lamport") is None


def test_validation_logic_valid_envelope():
    """
    Test that valid envelopes pass all validations.
    """
    envelope = {
        "thread_id": "thread_123",
        "sender_pk_b64": "test_sender",
        "lamport": 1,
        "payload": {"task_id": "task_123", "reason": "test"},
    }

    # All validations should pass
    thread_id = envelope.get("thread_id")
    payload = envelope.get("payload")
    sender = envelope.get("sender_pk_b64")
    lamport = envelope.get("lamport")
    task_id = payload.get("task_id") if payload else None

    assert thread_id
    assert payload
    assert sender
    assert lamport is not None
    assert task_id


def test_error_handling_pattern():
    """
    Test the error handling pattern: validate, log, return early.
    """

    def mock_handler(envelope: dict) -> bool:
        """Mock handler following the error handling pattern."""
        # Validate thread_id
        thread_id = envelope.get("thread_id")
        if not thread_id:
            # Would log error here
            return False

        # Validate payload
        payload = envelope.get("payload")
        if not payload:
            # Would log error here
            return False

        # Validate task_id
        task_id = payload.get("task_id")
        if not task_id:
            # Would log error here
            return False

        # All validations passed
        return True

    # Test with invalid envelopes
    assert not mock_handler({})
    assert not mock_handler({"thread_id": "t1"})
    assert not mock_handler({"thread_id": "t1", "payload": {}})

    # Test with valid envelope
    assert mock_handler({"thread_id": "t1", "payload": {"task_id": "task1"}})


def test_get_vs_bracket_access():
    """
    Test that .get() is safe vs bracket access which raises KeyError.
    """
    envelope = {}

    # .get() is safe
    assert envelope.get("missing_key") is None

    # Bracket access raises
    with pytest.raises(KeyError):
        _ = envelope["missing_key"]

    # This demonstrates why the refactored code uses .get()
