import os, json, hashlib, tempfile, shutil
from pathlib import Path
from typing import Optional, Union

from typing import Optional
import logging

logger = logging.getLogger(__name__)


def sha256_hash(data: bytes) -> str:
    """Compute SHA256 hash of data"""
    return hashlib.sha256(data).hexdigest()


class FileCAS:
    """File-based content-addressable storage"""

    def __init__(self, base_path: Path = None):
        self.base_path = base_path or Path(".cas")
        self.base_path.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes) -> str:
        """Store data and return its hash"""
        if not isinstance(data, bytes):
            raise TypeError(f"Expected bytes, got {type(data)}")

        h = sha256_hash(data)
        path = self.base_path / h

        if not path.exists():
            path.write_bytes(data)
            logger.debug(f"Stored content: {h} ({len(data)} bytes)")

        return h

    def get(self, content_hash: str) -> bytes:
        """Retrieve data by hash"""
        path = self.base_path / content_hash

        if not path.exists():
            raise KeyError(f"Content not found: {content_hash}")

        data = path.read_bytes()
        logger.debug(f"Retrieved content: {content_hash} ({len(data)} bytes)")
        return data

    def exists(self, content_hash: str) -> bool:
        """Check if content exists"""
        return (self.base_path / content_hash).exists()


def get_cas_store(base_path: Optional[Path] = None):
    """
    Factory function to get appropriate CAS store.

    Uses feature flag to determine whether to use FileCAS or IPFS backend.
    Set IPFS_CAS=true environment variable to use IPFS.

    Args:
        base_path: Base path for FileCAS (ignored for IPFS)

    Returns:
        Tuple of (cas_instance, is_ipfs: bool)
        - cas_instance: FileCAS or IPFSContentStore instance
        - is_ipfs: True if using IPFS, False if using FileCAS (including fallback)
    """
    # Import here to avoid circular dependencies
    from cas.feature_flag import use_ipfs_cas

    if use_ipfs_cas():
        # Use IPFS-backed CAS
        try:
            from cas.ipfs_store import IPFSContentStore

            logger.info("Using IPFS-backed CAS")
            return (IPFSContentStore(), True)
        except Exception as e:
            logger.error(
                f"Failed to initialize IPFS CAS: {e}. Falling back to file-based CAS."
            )
            return (FileCAS(base_path), False)
    else:
        # Use file-based CAS
        logger.info("Using file-based CAS")
        return (FileCAS(base_path), False)


def get_cas_health_status() -> dict:
    """
    Get health status of CAS backend.

    Returns:
        Dict with backend information:
        - backend: "ipfs" or "file"
        - is_ipfs: boolean flag
        - status: "healthy" or error message
    """
    try:
        cas, is_ipfs = get_cas_store()

        return {
            "backend": "ipfs" if is_ipfs else "file",
            "is_ipfs": is_ipfs,
            "status": "healthy",
        }
    except Exception as e:
        return {"backend": "unknown", "is_ipfs": False, "status": f"error: {str(e)}"}


# Backwards compatibility
CAS = FileCAS
