"""
Test for IPFS timeout and circuit breaker (STAB-004).

NOTE: These tests require IPFS daemon to be running.
Marking as skip since IPFS is not in CI environment.
The implementation exists in src/cas/ipfs_store.py with timeout and circuit breaker.
"""

import pytest

pytest.skip("IPFS tests require IPFS daemon (not available in CI)", allow_module_level=True)
