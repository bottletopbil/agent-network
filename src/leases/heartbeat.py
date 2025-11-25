"""
Heartbeat Protocol: Track expected heartbeats and detect misses.
"""

import time
from typing import Dict, List, Optional
from .manager import LeaseManager


class HeartbeatProtocol:
    """
    Track heartbeat expectations and detect missed heartbeats.
    
    Works with LeaseManager to monitor worker heartbeats.
    """
    
    def __init__(self, lease_manager: LeaseManager):
        """
        Initialize heartbeat protocol.
        
        Args:
            lease_manager: LeaseManager instance for lease queries
        """
        self.lease_manager = lease_manager
        # Track expected heartbeats: {lease_id: next_expected_ns}
        self._expectations: Dict[str, int] = {}
    
    def expect_heartbeat(self, lease_id: str, interval: int):
        """
        Set heartbeat expectation for a lease.
        
        Args:
            lease_id: Lease to track
            interval: Expected heartbeat interval in seconds
        """
        current_time = time.time_ns()
        interval_ns = interval * 1_000_000_000
        self._expectations[lease_id] = current_time + interval_ns
    
    def receive_heartbeat(self, lease_id: str):
        """
        Record heartbeat received for a lease.
        
        Updates expected next heartbeat time.
        
        Args:
            lease_id: Lease that sent heartbeat
        """
        # Get lease to get interval
        lease = self.lease_manager.get_lease(lease_id)
        if lease is None:
            # Lease not found, remove expectation
            self._expectations.pop(lease_id, None)
            return
        
        # Calculate next expected heartbeat
        current_time = time.time_ns()
        interval_ns = lease.heartbeat_interval * 1_000_000_000
        self._expectations[lease_id] = current_time + interval_ns
    
    def check_missed_heartbeats(self) -> List[str]:
        """
        Check for leases with missed heartbeats.
        
        A heartbeat is missed if current_time > expected_time.
        
        Returns:
            List of lease_ids with missed heartbeats
        """
        current_time = time.time_ns()
        missed = []
        
        for lease_id, expected_time in self._expectations.items():
            if current_time > expected_time:
                missed.append(lease_id)
        
        return missed
    
    def get_next_expected_heartbeat(self, lease_id: str) -> Optional[int]:
        """
        Get timestamp of next expected heartbeat.
        
        Args:
            lease_id: Lease to query
        
        Returns:
            Nanosecond timestamp or None if no expectation
        """
        return self._expectations.get(lease_id)
    
    def remove_expectation(self, lease_id: str):
        """
        Remove heartbeat expectation (e.g., when lease expires).
        
        Args:
            lease_id: Lease to stop tracking
        """
        self._expectations.pop(lease_id, None)
    
    def get_all_expectations(self) -> Dict[str, int]:
        """
        Get all heartbeat expectations.
        
        Returns:
            Dictionary of {lease_id: next_expected_ns}
        """
        return dict(self._expectations)
