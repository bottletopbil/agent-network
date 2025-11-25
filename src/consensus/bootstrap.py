"""
Bootstrap Mode Manager

Handles network bootstrap mode detection and progressive quorum scaling.
Network starts with K=1 for low verifier counts and progressively increases
as the network stabilizes.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class BootstrapManager:
    """
    Manages bootstrap mode detection and progressive quorum calculation.
    
    Bootstrap mode allows networks to start with minimal verifiers (K=1)
    and gradually increase quorum requirements as the network grows and stabilizes.
    """
    
    bootstrap_threshold: int = 10  # Minimum verifiers to exit bootstrap
    bootstrap_stable_hours: int = 24  # Hours above threshold before exit
    k_target: int = 5  # Target K value after bootstrap
    
    def is_bootstrap_mode(self, active_verifiers: int) -> bool:
        """
        Check if network is in bootstrap mode.
        
        Args:
            active_verifiers: Number of currently active verifiers
            
        Returns:
            True if network has fewer than bootstrap_threshold verifiers
        """
        return active_verifiers < self.bootstrap_threshold
    
    def calculate_k_result(
        self, 
        active_verifiers: int, 
        bootstrap_mode: Optional[bool] = None
    ) -> int:
        """
        Calculate dynamic K value based on network state.
        
        Args:
            active_verifiers: Number of currently active verifiers
            bootstrap_mode: Override bootstrap detection (None = auto-detect)
            
        Returns:
            K value: 1 if bootstrap, otherwise progressive based on verifiers
            
        Progressive formula after bootstrap:
            K = min(k_target, max(2, int(active_verifiers × 0.3)))
        """
        if bootstrap_mode is None:
            bootstrap_mode = self.is_bootstrap_mode(active_verifiers)
        
        if bootstrap_mode:
            return 1
        
        # Progressive scaling: 30% of active verifiers, min 2, max k_target
        progressive_k = max(2, int(active_verifiers * 0.3))
        return min(self.k_target, progressive_k)
    
    def should_exit_bootstrap(
        self, 
        active_verifiers: int, 
        hours_above_threshold: int
    ) -> bool:
        """
        Determine if network should exit bootstrap mode.
        
        Args:
            active_verifiers: Current number of active verifiers
            hours_above_threshold: Hours continuously above threshold
            
        Returns:
            True if verifiers >= threshold for stable_hours duration
        """
        return (
            active_verifiers >= self.bootstrap_threshold and
            hours_above_threshold >= self.bootstrap_stable_hours
        )
    
    def boost_challenge_reward(self, base_reward: int, bootstrap_mode: bool) -> int:
        """
        Calculate boosted challenge reward during bootstrap.
        
        Args:
            base_reward: Normal challenge reward amount
            bootstrap_mode: Whether network is in bootstrap mode
            
        Returns:
            2x reward if bootstrap, otherwise base_reward
        """
        return base_reward * 2 if bootstrap_mode else base_reward


# Global instance
bootstrap_manager = BootstrapManager()
