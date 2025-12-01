"""
IPFS-backed Content-Addressable Storage

Implements the CAS interface using IPFS as the backend storage.
Provides content-addressable storage with automatic deduplication,
distributed availability, and cryptographic integrity.
"""

import logging

from .ipfs_config import IPFSClient, IPFSConfig

logger = logging.getLogger(__name__)


class IPFSContentStore:
    """
    IPFS-backed Content-Addressable Storage implementation.

    Implements the same interface as FileCAS but uses IPFS for storage.
    Content is addressed by IPFS CIDs (Content Identifiers) which are
    cryptographic hashes of the content.
    """

    def __init__(self, ipfs_host: str = "127.0.0.1", ipfs_port: int = 5001, auto_pin: bool = True):
        """
        Initialize IPFS content store.

        Args:
            ipfs_host: IPFS API host
            ipfs_port: IPFS API port
            auto_pin: Automatically pin added content
        """
        # Create IPFS config with provided connection settings
        config = IPFSConfig(api_host=ipfs_host, api_port=ipfs_port)

        self.client = IPFSClient(config)
        self.auto_pin = auto_pin

        # Circuit breaker state
        self._circuit_breaker_open = False
        self._circuit_open_time = 0
        self._failure_count = 0
        self._max_failures = 3
        self._circuit_cooldown = 60  # seconds

        # Connect to IPFS
        if not self.client.connect():
            logger.error("Failed to connect to IPFS daemon")
            raise ConnectionError(
                f"Could not connect to IPFS at {ipfs_host}:{ipfs_port}. "
                "Make sure IPFS daemon is running."
            )

        logger.info(
            f"IPFS content store initialized: {ipfs_host}:{ipfs_port} "
            f"(peer: {self.client.get_peer_id()})"
        )

    def put(self, data: bytes) -> str:
        """
        Store content in IPFS and return its CID.

        Args:
            data: Content bytes to store

        Returns:
            IPFS CID (Content Identifier) as string

        Raises:
            RuntimeError: If content cannot be stored
        """
        if not isinstance(data, bytes):
            raise TypeError(f"Expected bytes, got {type(data)}")

        try:
            # Add content to IPFS
            cid = self.client.add_content(data, pin=self.auto_pin)

            if not cid:
                raise RuntimeError("Failed to add content to IPFS")

            logger.debug(f"Stored content in IPFS: {cid} ({len(data)} bytes)")
            return cid

        except Exception as e:
            logger.error(f"Failed to put content: {e}", exc_info=True)
            raise RuntimeError(f"Failed to store content in IPFS: {e}")

    def get(self, cid: str, timeout: int = 5) -> bytes:
        """
        Retrieve content from IPFS by CID with timeout.

        Args:
            cid: IPFS Content Identifier
            timeout: Maximum seconds to wait (default 5)

        Returns:
            Content bytes

        Raises:
            KeyError: If content not found
            RuntimeError: If content cannot be retrieved or timeout
        """
        import time
        import threading

        if not cid:
            raise ValueError("CID cannot be empty")

        # Check circuit breaker
        if self._circuit_breaker_open:
            # Check if cooldown period has passed
            if time.time() - self._circuit_open_time < self._circuit_cooldown:
                raise RuntimeError(
                    f"Circuit breaker open: IPFS unavailable (retry in "
                    f"{int(self._circuit_cooldown - (time.time() - self._circuit_open_time))}s)"
                )
            else:
                # Close circuit breaker after cooldown
                logger.info("Circuit breaker closing: attempting IPFS reconnection")
                self._circuit_breaker_open = False
                self._failure_count = 0

        # Wrapper for timeout handling
        result = [None]
        error = [None]

        def fetch_with_timeout():
            try:
                result[0] = self.client.get_content(cid)
            except Exception as e:
                error[0] = e

        # Run fetch in thread with timeout
        thread = threading.Thread(target=fetch_with_timeout)
        thread.daemon = True
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            # Timeout occurred
            self._failure_count += 1
            logger.warning(
                f"IPFS get timeout after {timeout}s (failure {self._failure_count}/{self._max_failures})"
            )

            if self._failure_count >= self._max_failures:
                self._circuit_breaker_open = True
                self._circuit_open_time = time.time()
                logger.error(
                    f"Circuit breaker opened: {self._failure_count} consecutive failures. "
                    f"IPFS unavailable for {self._circuit_cooldown}s"
                )

            raise RuntimeError(f"IPFS get timeout after {timeout}s for CID: {cid}")

        # Check for errors
        if error[0]:
            self._failure_count += 1
            logger.warning(
                f"IPFS get error (failure {self._failure_count}/{self._max_failures}): {error[0]}"
            )

            if self._failure_count >= self._max_failures:
                self._circuit_breaker_open = True
                self._circuit_open_time = time.time()
                logger.error(f"Circuit breaker opened after {self._failure_count} failures")

            if isinstance(error[0], KeyError):
                raise error[0]
            raise RuntimeError(f"Failed to retrieve content from IPFS: {error[0]}")

        # Success - reset failure count
        content = result[0]

        if content is None:
            raise KeyError(f"Content not found: {cid}")

        # Reset failure counter on success
        if self._failure_count > 0:
            logger.info(f"IPFS get succeeded, resetting failure count from {self._failure_count}")
            self._failure_count = 0

        logger.debug(f"Retrieved content from IPFS: {cid} ({len(content)} bytes)")
        return content

    def exists(self, cid: str) -> bool:
        """
        Check if content exists in IPFS.

        Args:
            cid: IPFS Content Identifier

        Returns:
            True if content exists
        """
        try:
            # Try to get the content with a small timeout
            # If it exists locally or in the network, this will succeed
            content = self.client.get_content(cid)
            return content is not None
        except Exception:
            return False

    def pin(self, cid: str) -> None:
        """
        Pin content in IPFS to prevent garbage collection.

        Args:
            cid: IPFS Content Identifier to pin

        Raises:
            RuntimeError: If pinning fails
        """
        try:
            if not self.client.pin_content(cid):
                raise RuntimeError(f"Failed to pin content: {cid}")

            logger.debug(f"Pinned content: {cid}")

        except Exception as e:
            logger.error(f"Failed to pin content: {e}")
            raise RuntimeError(f"Failed to pin content: {e}")

    def unpin(self, cid: str) -> None:
        """
        Unpin content in IPFS to allow garbage collection.

        Args:
            cid: IPFS Content Identifier to unpin

        Raises:
            RuntimeError: If unpinning fails
        """
        try:
            if not self.client.unpin_content(cid):
                raise RuntimeError(f"Failed to unpin content: {cid}")

            logger.debug(f"Unpinned content: {cid}")

        except Exception as e:
            logger.error(f"Failed to unpin content: {e}")
            raise RuntimeError(f"Failed to unpin content: {e}")

    def list_pins(self) -> list:
        """
        List all pinned content.

        Returns:
            List of pinned CIDs
        """
        try:
            return self.client.list_pins()
        except Exception as e:
            logger.error(f"Failed to list pins: {e}")
            return []

    def gc(self) -> dict:
        """
        Run garbage collection to remove unpinned content.

        Returns:
            GC results dictionary
        """
        try:
            return self.client.run_gc()
        except Exception as e:
            logger.error(f"Failed to run GC: {e}")
            return {"error": str(e)}

    def close(self):
        """Close the IPFS client connection"""
        if self.client:
            self.client.close()
            logger.info("IPFS content store closed")


# Compatibility alias for common CAS interface
CAS = IPFSContentStore
