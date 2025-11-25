"""
Bootstrap Monitor Daemon

Monitors active verifier count and tracks bootstrap mode status.
Logs when network should exit bootstrap mode based on stability criteria.
"""

import time
import logging
from typing import Optional
from threading import Thread, Event

from src.consensus.bootstrap import bootstrap_manager

logger = logging.getLogger(__name__)


class BootstrapMonitor:
    """
    Monitors bootstrap mode status and tracks exit conditions.
    
    Runs as a daemon thread, checking active verifiers every hour and
    tracking how long the network has been above the bootstrap threshold.
    """
    
    def __init__(
        self, 
        get_active_verifiers_callback,
        check_interval_seconds: int = 3600  # 1 hour default
    ):
        """
        Initialize bootstrap monitor.
        
        Args:
            get_active_verifiers_callback: Function that returns current active verifier count
            check_interval_seconds: How often to check status (default: 3600 = 1 hour)
        """
        self.get_active_verifiers = get_active_verifiers_callback
        self.check_interval = check_interval_seconds
        self.hours_above_threshold = 0
        self.last_bootstrap_status = True  # Assume starting in bootstrap
        self.stop_event = Event()
        self.thread: Optional[Thread] = None
        
    def start(self):
        """Start the monitoring daemon"""
        if self.thread is not None and self.thread.is_alive():
            logger.warning("Bootstrap monitor already running")
            return
        
        self.stop_event.clear()
        self.thread = Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logger.info("Bootstrap monitor started")
    
    def stop(self):
        """Stop the monitoring daemon"""
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Bootstrap monitor stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while not self.stop_event.is_set():
            try:
                self._check_bootstrap_status()
            except Exception as e:
                logger.error(f"Error in bootstrap monitor: {e}", exc_info=True)
            
            # Wait for next check or stop signal
            self.stop_event.wait(self.check_interval)
    
    def _check_bootstrap_status(self):
        """Check current bootstrap status and update tracking"""
        active_verifiers = self.get_active_verifiers()
        is_bootstrap = bootstrap_manager.is_bootstrap_mode(active_verifiers)
        k_value = bootstrap_manager.calculate_k_result(active_verifiers, is_bootstrap)
        
        # Track hours above threshold
        if active_verifiers >= bootstrap_manager.bootstrap_threshold:
            self.hours_above_threshold += 1
        else:
            self.hours_above_threshold = 0  # Reset if drops below
        
        # Log status changes
        if is_bootstrap != self.last_bootstrap_status:
            if is_bootstrap:
                logger.warning(
                    f"Entered bootstrap mode: {active_verifiers} verifiers "
                    f"(threshold: {bootstrap_manager.bootstrap_threshold})"
                )
            else:
                logger.info(
                    f"Exited bootstrap mode: {active_verifiers} verifiers, K={k_value}"
                )
        
        # Check if should exit bootstrap
        should_exit = bootstrap_manager.should_exit_bootstrap(
            active_verifiers, 
            self.hours_above_threshold
        )
        
        if should_exit and is_bootstrap:
            logger.info(
                f"BOOTSTRAP EXIT CRITERIA MET: {active_verifiers} verifiers stable "
                f"for {self.hours_above_threshold} hours "
                f"(required: {bootstrap_manager.bootstrap_stable_hours})"
            )
        
        # Log periodic status
        logger.debug(
            f"Bootstrap status: mode={is_bootstrap}, verifiers={active_verifiers}, "
            f"K={k_value}, hours_above={self.hours_above_threshold}"
        )
        
        self.last_bootstrap_status = is_bootstrap
    
    def get_status(self) -> dict:
        """
        Get current monitor status.
        
        Returns:
            Dict with bootstrap status, verifier count, K value, and hours above threshold
        """
        active_verifiers = self.get_active_verifiers()
        is_bootstrap = bootstrap_manager.is_bootstrap_mode(active_verifiers)
        k_value = bootstrap_manager.calculate_k_result(active_verifiers, is_bootstrap)
        
        return {
            "bootstrap_mode": is_bootstrap,
            "active_verifiers": active_verifiers,
            "k_value": k_value,
            "hours_above_threshold": self.hours_above_threshold,
            "should_exit": bootstrap_manager.should_exit_bootstrap(
                active_verifiers, 
                self.hours_above_threshold
            )
        }
