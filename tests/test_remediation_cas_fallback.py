"""
Test for CAS fallback notification (STAB-001).

Validates that IPFS failures are explicitly reported instead of
silently falling back to FileCAS.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_ipfs_failure_returns_fallback_flag():
    """
    Test that IPFS connection failure returns explicit fallback indicator.

    Should return (FileCAS, False) to indicate fallback mode.
    """
    from cas_core import get_cas_store

    with patch("cas.feature_flag.use_ipfs_cas", return_value=True):
        with patch("cas.ipfs_store.IPFSContentStore") as mock_ipfs:
            # Simulate IPFS connection failure
            mock_ipfs.side_effect = ConnectionError("IPFS daemon not available")

            # Should return fallback with flag
            cas, is_ipfs = get_cas_store()

            # Should be FileCAS in fallback mode
            assert is_ipfs is False, "Should indicate fallback mode"
            assert cas is not None, "Should still return a CAS instance"

            # Should be FileCAS type
            from cas_core import FileCAS

            assert isinstance(cas, FileCAS), "Should fallback to FileCAS"


def test_ipfs_success_returns_ipfs_flag():
    """
    Test that successful IPFS connection returns IPFS indicator.

    Should return (IPFSContentStore, True).
    """
    from cas_core import get_cas_store

    with patch("cas.feature_flag.use_ipfs_cas", return_value=True):
        with patch("cas.ipfs_store.IPFSContentStore") as mock_ipfs:
            # Mock successful IPFS instance
            mock_instance = Mock()
            mock_ipfs.return_value = mock_instance

            # Should return IPFS with flag
            cas, is_ipfs = get_cas_store()

            # Should indicate IPFS mode
            assert is_ipfs is True, "Should indicate IPFS mode"
            assert cas == mock_instance, "Should return IPFS instance"


def test_file_cas_mode_returns_correct_flag():
    """
    Test that FileCAS mode (when IPFS not configured) returns correct flag.

    Should return (FileCAS, False).
    """
    from cas_core import get_cas_store

    with patch("cas.feature_flag.use_ipfs_cas", return_value=False):
        # Should return FileCAS with flag
        cas, is_ipfs = get_cas_store()

        # Should indicate non-IPFS mode
        assert is_ipfs is False, "Should indicate FileCAS mode"

        # Should be FileCAS type
        from cas_core import FileCAS

        assert isinstance(cas, FileCAS), "Should be FileCAS instance"


def test_ipfs_failure_logs_error():
    """
    Test that IPFS connection failure logs an error.
    """
    from cas_core import get_cas_store

    with patch("cas.feature_flag.use_ipfs_cas", return_value=True):
        with patch("cas.ipfs_store.IPFSContentStore") as mock_ipfs:
            mock_ipfs.side_effect = ConnectionError("Connection refused")

            # Capture log output
            with patch("cas_core.logger") as mock_logger:
                cas, is_ipfs = get_cas_store()

                # Should log error about fallback
                assert mock_logger.error.called, "Should log error on IPFS failure"
                error_call = mock_logger.error.call_args
                assert "IPFS" in str(error_call) or "fallback" in str(error_call).lower()


def test_return_type_is_tuple():
    """
    Test that get_cas_store() always returns a tuple.
    """
    from cas_core import get_cas_store

    result = get_cas_store()

    assert isinstance(result, tuple), "Should return tuple"
    assert len(result) == 2, "Should return 2-tuple (cas, is_ipfs)"

    cas, is_ipfs = result
    assert cas is not None, "CAS instance should not be None"
    assert isinstance(is_ipfs, bool), "is_ipfs should be boolean"


def test_health_check_reports_cas_backend():
    """
    Test that health check endpoint reports CAS backend status.
    """
    from cas_core import get_cas_health_status

    # Should return dict with backend info
    status = get_cas_health_status()

    assert isinstance(status, dict), "Should return status dict"
    assert "backend" in status, "Should include backend type"
    assert "is_ipfs" in status, "Should include IPFS flag"

    # backend should be either "ipfs" or "file"
    assert status["backend"] in ["ipfs", "file"], "Backend should be ipfs or file"
    assert isinstance(status["is_ipfs"], bool), "is_ipfs should be boolean"
