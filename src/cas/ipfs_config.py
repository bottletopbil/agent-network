"""
IPFS Configuration and Client Management

Provides connection settings, pinning strategies, and garbage collection
configuration for the IPFS Content-Addressable Storage system.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class PinningStrategy(Enum):
    """Strategies for pinning content in IPFS"""

    PIN_ALL = "pin_all"  # Pin everything (permanent storage)
    PIN_RECENT = "pin_recent"  # Pin recent content only
    PIN_BY_SIZE = "pin_by_size"  # Pin based on size thresholds
    PIN_BY_IMPORTANCE = "pin_by_importance"  # Pin based on importance metadata
    NO_PIN = "no_pin"  # Don't pin (rely on network)


@dataclass
class IPFSConfig:
    """
    IPFS configuration settings.

    Attributes:
        api_host: IPFS API host address
        api_port: IPFS API port
        gateway_host: IPFS gateway host
        gateway_port: IPFS gateway port
        pinning_strategy: Strategy for pinning content
        max_storage_gb: Maximum storage in GB (for pinning strategies)
        gc_interval_hours: Garbage collection interval in hours
        gc_enabled: Whether garbage collection is enabled
    """

    api_host: str = "127.0.0.1"
    api_port: int = 5001
    gateway_host: str = "127.0.0.1"
    gateway_port: int = 8080
    pinning_strategy: PinningStrategy = PinningStrategy.PIN_RECENT
    max_storage_gb: float = 100.0
    gc_interval_hours: int = 24
    gc_enabled: bool = True
    pin_recent_days: int = 30  # For PIN_RECENT strategy
    pin_size_threshold_mb: float = 10.0  # For PIN_BY_SIZE strategy

    def get_api_url(self) -> str:
        """Get IPFS API URL"""
        return f"/ip4/{self.api_host}/tcp/{self.api_port}/http"

    def get_gateway_url(self) -> str:
        """Get IPFS Gateway URL"""
        return f"http://{self.gateway_host}:{self.gateway_port}"

    @classmethod
    def from_env(cls) -> "IPFSConfig":
        """Create config from environment variables"""
        return cls(
            api_host=os.getenv("IPFS_API_HOST", "127.0.0.1"),
            api_port=int(os.getenv("IPFS_API_PORT", "5001")),
            gateway_host=os.getenv("IPFS_GATEWAY_HOST", "127.0.0.1"),
            gateway_port=int(os.getenv("IPFS_GATEWAY_PORT", "8080")),
            pinning_strategy=PinningStrategy(
                os.getenv("IPFS_PINNING_STRATEGY", "pin_recent")
            ),
            max_storage_gb=float(os.getenv("IPFS_MAX_STORAGE_GB", "100.0")),
            gc_interval_hours=int(os.getenv("IPFS_GC_INTERVAL_HOURS", "24")),
            gc_enabled=os.getenv("IPFS_GC_ENABLED", "true").lower() == "true",
            pin_recent_days=int(os.getenv("IPFS_PIN_RECENT_DAYS", "30")),
            pin_size_threshold_mb=float(
                os.getenv("IPFS_PIN_SIZE_THRESHOLD_MB", "10.0")
            ),
        )


class IPFSClient:
    """
    IPFS client wrapper with configuration management.

    Provides a simplified interface to IPFS with built-in configuration
    and connection management.
    """

    def __init__(self, config: Optional[IPFSConfig] = None):
        """
        Initialize IPFS client.

        Args:
            config: IPFS configuration (uses default if None)
        """
        self.config = config or IPFSConfig()
        self._client = None
        logger.info(f"IPFS client initialized: {self.config.get_api_url()}")

    def connect(self) -> bool:
        """
        Connect to IPFS daemon.

        Returns:
            True if connection successful
        """
        try:
            import ipfshttpclient

            self._client = ipfshttpclient.connect(self.config.get_api_url())

            # Verify connection
            peer_id = self._client.id()
            logger.info(f"Connected to IPFS peer: {peer_id['ID']}")

            return True
        except Exception as e:
            logger.error(f"Failed to connect to IPFS: {e}", exc_info=True)
            return False

    def is_connected(self) -> bool:
        """Check if client is connected"""
        return self._client is not None

    def get_client(self):
        """Get the underlying IPFS client"""
        if not self.is_connected():
            self.connect()
        return self._client

    def get_peer_id(self) -> Optional[str]:
        """Get IPFS peer ID"""
        try:
            if not self.is_connected():
                self.connect()

            id_info = self._client.id()
            return id_info.get("ID")
        except Exception as e:
            logger.error(f"Failed to get peer ID: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get IPFS node statistics"""
        try:
            if not self.is_connected():
                self.connect()

            # Use repo stats method
            stats = self._client.repo.stat()
            return {
                "num_objects": stats.get("NumObjects", 0),
                "repo_size": stats.get("RepoSize", 0),
                "storage_max": stats.get("StorageMax", 0),
                "version": stats.get("Version", "unknown"),
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}

    def add_content(
        self, data: bytes, pin: Optional[bool] = None, wrap: bool = False
    ) -> Optional[str]:
        """
        Add content to IPFS.

        Args:
            data: Content to add
            pin: Whether to pin (uses strategy if None)
            wrap: Wrap in directory

        Returns:
            IPFS CID hash
        """
        try:
            if not self.is_connected():
                self.connect()

            # Determine pinning based on strategy
            should_pin = pin if pin is not None else self._should_pin(len(data))

            # Add content (ipfshttpclient 0.8.0a2 API)
            result = self._client.add_bytes(data)

            # Handle both string and dict responses
            if isinstance(result, dict):
                cid = result.get("Hash", result.get("hash"))
            else:
                cid = result

            # Pin if requested
            if should_pin and cid:
                self.pin_content(cid)

            logger.info(f"Added content to IPFS: {cid} (pinned: {should_pin})")
            return cid
        except Exception as e:
            logger.error(f"Failed to add content: {e}", exc_info=True)
            return None

    def get_content(self, cid: str) -> Optional[bytes]:
        """
        Get content from IPFS.

        Args:
            cid: IPFS CID hash

        Returns:
            Content bytes
        """
        try:
            if not self.is_connected():
                self.connect()

            content = self._client.cat(cid)
            logger.debug(f"Retrieved content from IPFS: {cid}")
            return content
        except Exception as e:
            logger.error(f"Failed to get content: {e}", exc_info=True)
            return None

    def pin_content(self, cid: str) -> bool:
        """
        Pin content in IPFS.

        Args:
            cid: IPFS CID hash

        Returns:
            True if pinned successfully
        """
        try:
            if not self.is_connected():
                self.connect()

            self._client.pin.add(cid)
            logger.info(f"Pinned content: {cid}")
            return True
        except Exception as e:
            logger.error(f"Failed to pin content: {e}")
            return False

    def unpin_content(self, cid: str) -> bool:
        """
        Unpin content in IPFS.

        Args:
            cid: IPFS CID hash

        Returns:
            True if unpinned successfully
        """
        try:
            if not self.is_connected():
                self.connect()

            self._client.pin.rm(cid)
            logger.info(f"Unpinned content: {cid}")
            return True
        except Exception as e:
            logger.error(f"Failed to unpin content: {e}")
            return False

    def list_pins(self) -> List[str]:
        """
        List all pinned content.

        Returns:
            List of pinned CIDs
        """
        try:
            if not self.is_connected():
                self.connect()

            pins = self._client.pin.ls()
            return list(pins.get("Keys", {}).keys())
        except Exception as e:
            logger.error(f"Failed to list pins: {e}")
            return []

    def run_gc(self) -> Dict[str, Any]:
        """
        Run garbage collection.

        Returns:
            GC results
        """
        try:
            if not self.is_connected():
                self.connect()

            if not self.config.gc_enabled:
                logger.warning("Garbage collection is disabled in config")
                return {"error": "GC disabled"}

            results = list(self._client.repo.gc())
            logger.info(f"Garbage collection completed: {len(results)} items removed")

            return {
                "removed_count": len(results),
                "removed_cids": [
                    r.get("Key", {}).get("/") for r in results if "Key" in r
                ],
            }
        except Exception as e:
            logger.error(f"Failed to run GC: {e}")
            return {"error": str(e)}

    def _should_pin(self, content_size_bytes: int) -> bool:
        """
        Determine if content should be pinned based on strategy.

        Args:
            content_size_bytes: Size of content in bytes

        Returns:
            True if should pin
        """
        strategy = self.config.pinning_strategy

        if strategy == PinningStrategy.PIN_ALL:
            return True
        elif strategy == PinningStrategy.NO_PIN:
            return False
        elif strategy == PinningStrategy.PIN_BY_SIZE:
            size_mb = content_size_bytes / (1024 * 1024)
            return size_mb <= self.config.pin_size_threshold_mb
        elif strategy == PinningStrategy.PIN_RECENT:
            # Would need timestamp metadata - default to True for now
            return True
        elif strategy == PinningStrategy.PIN_BY_IMPORTANCE:
            # Would need importance metadata - default to True for now
            return True
        else:
            return True

    def close(self):
        """Close IPFS client connection"""
        if self._client:
            try:
                self._client.close()
                logger.info("IPFS client connection closed")
            except Exception as e:
                logger.error(f"Error closing IPFS client: {e}")
        self._client = None


# Global IPFS client instance
_ipfs_client: Optional[IPFSClient] = None


def get_ipfs_client() -> IPFSClient:
    """Get global IPFS client instance"""
    global _ipfs_client
    if _ipfs_client is None:
        config = IPFSConfig.from_env()
        _ipfs_client = IPFSClient(config)
    return _ipfs_client


def init_ipfs_client(config: Optional[IPFSConfig] = None) -> IPFSClient:
    """
    Initialize global IPFS client.

    Args:
        config: IPFS configuration

    Returns:
        IPFSClient instance
    """
    global _ipfs_client
    _ipfs_client = IPFSClient(config)
    return _ipfs_client
