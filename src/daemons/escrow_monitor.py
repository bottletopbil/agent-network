"""Escrow monitor daemon for automatic TTL enforcement.

This daemon periodically checks escrows for expiration and triggers
rollback for timed-out cross-shard coordination.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class EscrowMonitor:
    """
    Background daemon that monitors escrow TTLs and triggers expiration.

    Runs periodically to check for expired escrows and invoke rollback.
    """

    def __init__(self, escrow_manager, check_interval_seconds: float = 1.0):
        """
        Initialize escrow monitor.

        Args:
            escrow_manager: EscrowManager instance to monitor
            check_interval_seconds: How often to check for expirations
        """
        self.escrow_manager = escrow_manager
        self.check_interval_seconds = check_interval_seconds
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the monitor daemon."""
        if self.running:
            logger.warning("Escrow monitor already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"Started escrow monitor with {self.check_interval_seconds}s interval")

    async def stop(self):
        """Stop the monitor daemon."""
        if not self.running:
            return

        self.running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped escrow monitor")

    async def _monitor_loop(self):
        """Main monitoring loop."""
        try:
            while self.running:
                await self._check_expirations()
                await asyncio.sleep(self.check_interval_seconds)
        except asyncio.CancelledError:
            logger.debug("Escrow monitor loop cancelled")
        except Exception as e:
            logger.error(f"Error in escrow monitor loop: {e}", exc_info=True)
            self.running = False

    async def _check_expirations(self):
        """Check for and handle expired escrows."""
        try:
            current_time_ns = int(datetime.utcnow().timestamp() * 1_000_000_000)

            expired = self.escrow_manager.check_expirations(current_time_ns)

            if expired:
                logger.info(f"Expired {len(expired)} escrow(s)")

                # Optionally cleanup old completed escrows periodically
                self.escrow_manager.cleanup_completed()

        except Exception as e:
            logger.error(f"Error checking expirations: {e}", exc_info=True)

    def get_status(self) -> dict:
        """
        Get monitor status.

        Returns:
            Status dictionary
        """
        pending = self.escrow_manager.get_pending_escrows()

        return {
            "running": self.running,
            "check_interval_seconds": self.check_interval_seconds,
            "pending_escrows": len(pending),
            "total_escrows": len(self.escrow_manager.escrows),
        }
