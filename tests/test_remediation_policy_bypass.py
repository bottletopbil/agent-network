"""
Test for policy enforcement bypass prevention (SEC-002).

This test verifies that the policy enforcement decorator works correctly.
"""

import sys
from pathlib import Path
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from policy.enforcement import require_policy_validation


# Create a test handler
@require_policy_validation
async def test_handler(envelope: dict):
    """Mock handler that just returns success."""
    return {"status": "ok", "task_id": envelope["payload"].get("task_id")}


def test_missing_required_fields_rejected():
    """
    Test that envelopes missing required fields are rejected by decorator.
    """
    incomplete_envelope = {
        "thread_id": "thread_123",
        "operation": "YIELD",
        # Missing sender_pk_b64, lamport, payload, etc.
    }
    
    with pytest.raises(ValueError) as exc_info:
        asyncio.run(test_handler(incomplete_envelope))
    
    assert "missing required fields" in str(exc_info.value).lower()


def test_non_dict_envelope_rejected():
    """
    Test that non-dictionary envelopes are rejected  immediately.
    """
    with pytest.raises(ValueError) as exc_info:
        asyncio.run(test_handler("not_a_dict"))
    
    assert "must be a dictionary" in str(exc_info.value).lower()


def test_decorator_marks_function():
    """
    Test that decorator adds metadata to wrapped function.
    """
    assert hasattr(test_handler, '__wrapped__')
    assert hasattr(test_handler, '__policy_enforced__')
    assert test_handler.__policy_enforced__ == True


def test_policy_validation_invoked():
    """
    Test that policy validation is invoked (even if it fails).
    """
    valid_structure = {
        "thread_id": "thread_123",
        "sender_pk_b64": "valid_key",
        "lamport": 1,
        "operation": "TEST_OP",
        "payload": {
            "task_id": "task_123"
        }
    }
    
    # Mock the gate enforcer to simulate policy check
    mock_decision = Mock()
    mock_decision.allowed = False
    mock_decision.reason = "TEST_OP not in allowed operations"
    
    mock_enforcer = Mock()
    mock_enforcer.ingress_validate.return_value = mock_decision
    
    with patch('policy.enforcement.get_gate_enforcer', return_value=mock_enforcer):
        with pytest.raises(ValueError) as exc_info:
            asyncio.run(test_handler(valid_structure))
        
        # Verify policy check was called
        mock_enforcer.ingress_validate.assert_called_once_with(valid_structure)
        
        # Verify error message mentions policy
        assert "policy" in str(exc_info.value).lower()


def test_policy_validation_passes_when_allowed():
    """
    Test that handler execution proceeds when policy allows it.
    """
    valid_structure = {
        "thread_id": "thread_123",
        "sender_pk_b64": "valid_key",
        "lamport": 1,
        "operation": "YIELD",
        "payload": {
            "task_id": "task_123"
        }
    }
    
    # Mock the gate enforcer to allow the operation
    mock_decision = Mock()
    mock_decision.allowed = True
    
    mock_enforcer = Mock()
    mock_enforcer.ingress_validate.return_value = mock_decision
    
    with patch('policy.enforcement.get_gate_enforcer', return_value=mock_enforcer):
        result = asyncio.run(test_handler(valid_structure))
        
        # Handler should execute successfully
        assert result["status"] == "ok"
        assert result["task_id"] == "task_123"
        
        # Verify policy check was called
        mock_enforcer.ingress_validate.assert_called_once()


def test_bypass_flags_ignored():
    """
    Test that special bypass flags are ignored.
    """
    bypass_attempt = {
        "thread_id": "thread_123",
        "sender_pk_b64": "attacker",
        "lamport": 1,
        "operation": "MALICIOUS",
        "payload": {"task_id": "task_123"},
        "_skip_validation": True,
        "_bypass_policy": True,
        "__no_check__": True
    }
    
    # Mock to reject the operation
    mock_decision = Mock()
    mock_decision.allowed = False
    mock_decision.reason = "MALICIOUS not allowed"
    
    mock_enforcer = Mock()
    mock_enforcer.ingress_validate.return_value = mock_decision
    
    with patch('policy.enforcement.get_gate_enforcer', return_value=mock_enforcer):
        with pytest.raises(ValueError):
            asyncio.run(test_handler(bypass_attempt))
        
        # Policy check was still called despite bypass flags
        mock_enforcer.ingress_validate.assert_called_once()
