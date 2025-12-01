"""
Test for Firecracker fail-closed behavior (SAND-001).

This test verifies that the system fails securely when Firecracker is not available,
rather than silently falling back to mock mode in production.
"""

import sys
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sandbox.firecracker import FirecrackerVM, SandboxError


def test_fail_closed_when_firecracker_unavailable():
    """
    Test that requesting real mode (mock_mode=False) when Firecracker is unavailable
    raises SandboxError instead of silently using mock mode.
    
    This is CRITICAL security: production must fail-closed if real isolation unavailable.
    """
    # Mock _is_firecracker_available to return False (simulating non-Linux or no KVM)
    with patch.object(FirecrackerVM, '_is_firecracker_available', return_value=False):
        # Attempt to create VM in real mode (explicitly requesting security)
        with pytest.raises(SandboxError) as exc_info:
            vm = FirecrackerVM(mock_mode=False)
        
        # Verify error message is informative
        error_msg = str(exc_info.value)
        assert "Firecracker is not available" in error_msg
        assert "mock_mode" in error_msg or "development" in error_msg


def test_auto_detect_uses_mock_when_unavailable():
    """
    Test that auto-detection (mock_mode=None) gracefully falls back to mock
    on systems without Firecracker (development scenario).
    """
    with patch.object(FirecrackerVM, '_is_firecracker_available', return_value=False):
        # Auto-detect should enable mock_mode without error
        vm = FirecrackerVM(mock_mode=None)
        assert vm.mock_mode is True


def test_explicit_mock_mode_always_works():
    """
    Test that explicitly requesting mock_mode=True always works,
    regardless of Firecracker availability.
    """
    with patch.object(FirecrackerVM, '_is_firecracker_available', return_value=False):
        vm = FirecrackerVM(mock_mode=True)
        assert vm.mock_mode is True
    
    with patch.object(FirecrackerVM, '_is_firecracker_available', return_value=True):
        vm = FirecrackerVM(mock_mode=True)
        assert vm.mock_mode is True


def test_real_mode_succeeds_when_firecracker_available():
    """
    Test that real mode (mock_mode=False) works when Firecracker is actually available.
    """
    with patch.object(FirecrackerVM, '_is_firecracker_available', return_value=True):
        vm = FirecrackerVM(mock_mode=False)
        assert vm.mock_mode is False


def test_production_ready_method():
    """
    Test the production_ready() method that checks if real Firecracker is available.
    """
    with patch.object(FirecrackerVM, '_is_firecracker_available', return_value=True):
        vm = FirecrackerVM(mock_mode=False)
        assert vm.production_ready() is True
    
    with patch.object(FirecrackerVM, '_is_firecracker_available', return_value=False):
        vm = FirecrackerVM(mock_mode=True)
        assert vm.production_ready() is False


def test_real_exec_raises_helpful_error():
    """
    Test that _real_exec raises a clear error when called on incomplete implementation.
    """
    with patch.object(FirecrackerVM, '_is_firecracker_available', return_value=True):
        vm = FirecrackerVM(mock_mode=False)
        
        # Even in real mode, _real_exec should raise NotImplementedError with helpful message
        with pytest.raises(NotImplementedError) as exc_info:
            vm._real_exec("vm123", "echo test", 30)
        
        error_msg = str(exc_info.value)
        assert "Real Firecracker execution" in error_msg or "full setup" in error_msg
