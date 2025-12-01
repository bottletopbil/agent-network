"""
Feature Flag for CAS Backend Selection

Allows switching between FileCAS and IPFS-backed CAS storage
via environment variable or programmatic configuration.
"""

import os
import logging

logger = logging.getLogger(__name__)

# Default backend
_cas_backend = None


def use_ipfs_cas() -> bool:
    """
    Check if IPFS CAS should be used instead of FileCAS.

    Checks the IPFS_CAS environment variable. Set to 'true', '1', or 'yes'
    to enable IPFS backend.

    Returns:
        True if IPFS CAS should be used
    """
    global _cas_backend

    # If explicitly set programmatically, use that
    if _cas_backend is not None:
        return _cas_backend == "ipfs"

    # Check environment variable
    env_value = os.getenv("IPFS_CAS", "").lower()
    use_ipfs = env_value in ("true", "1", "yes", "on")

    if use_ipfs:
        logger.info("Using IPFS-backed CAS (IPFS_CAS=true)")
    else:
        logger.info("Using file-based CAS (IPFS_CAS not set)")

    return use_ipfs


def set_cas_backend(backend: str) -> None:
    """
    Programmatically set the CAS backend.

    Args:
        backend: Either 'ipfs' or 'file'
    """
    global _cas_backend

    if backend not in ("ipfs", "file"):
        raise ValueError(f"Invalid CAS backend: {backend}. Must be 'ipfs' or 'file'")

    _cas_backend = backend
    logger.info(f"CAS backend set to: {backend}")


def get_cas_backend() -> str:
    """
    Get the current CAS backend.

    Returns:
        Either 'ipfs' or 'file'
    """
    return "ipfs" if use_ipfs_cas() else "file"


def reset_cas_backend() -> None:
    """Reset CAS backend to environment-based selection"""
    global _cas_backend
    _cas_backend = None
    logger.info("CAS backend reset to environment-based selection")
