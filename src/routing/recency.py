"""
Recency Weighting

Boosts recently active agents and applies decay to inactive agents.
Encourages use of agents with recent successful activity.
"""

from typing import Dict, Optional
import time
import logging
import math

logger = logging.getLogger(__name__)


class RecencyWeighter:
    """
    Weights agents based on recent activity.
    
    Recently active agents get boosted scores.
    Inactive agents get decayed scores.
    """
    
    def __init__(
        self,
        half_life_hours: float = 24.0,
        max_boost: float = 1.5,
        min_weight: float = 0.5
    ):
        """
        Initialize recency weighter.
        
        Args:
            half_life_hours: Hours after which weight decays to 50%
            max_boost: Maximum boost for very recent activity (e.g., 1.5 = 50% boost)
            min_weight: Minimum weight for very old activity (e.g., 0.5 = 50% penalty)
        """
        self.half_life_hours = half_life_hours
        self.max_boost = max_boost
        self.min_weight = min_weight
        
        # Track last activity: agent_id -> timestamp
        self.last_activity: Dict[str, float] = {}
    
    def record_activity(self, agent_id: str, timestamp: Optional[float] = None) -> None:
        """
        Record agent activity.
        
        Args:
            agent_id: Agent ID
            timestamp: Activity timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = time.time()
        
        self.last_activity[agent_id] = timestamp
        
        logger.debug(f"Recorded activity for {agent_id} at {timestamp}")
    
    def get_recency_weight(
        self,
        agent_id: str,
        current_time: Optional[float] = None
    ) -> float:
        """
        Calculate recency weight for an agent.
        
        Uses exponential decay:
        weight = max_boost * exp(-λ * age_hours)
        
        where λ = ln(2) / half_life_hours
        
        Args:
            agent_id: Agent ID
            current_time: Current timestamp (defaults to now)
            
        Returns:
            Recency weight from min_weight to max_boost
        """
        if current_time is None:
            current_time = time.time()
        
        # Get last activity time
        last_time = self.last_activity.get(agent_id)
        
        if last_time is None:
            # No activity recorded, use minimum weight
            return self.min_weight
        
        # Calculate age in hours
        age_seconds = current_time - last_time
        age_hours = age_seconds / 3600.0
        
        # Exponential decay
        decay_rate = math.log(2) / self.half_life_hours
        weight = self.max_boost * math.exp(-decay_rate * age_hours)
        
        # Clamp to [min_weight, max_boost]
        weight = max(self.min_weight, min(self.max_boost, weight))
        
        return weight
    
    def get_recency_score(
        self,
        agent_id: str,
        current_time: Optional[float] = None
    ) -> float:
        """
        Get normalized recency score (0.0 - 1.0).
        
        Maps weight from [min_weight, max_boost] to [0.0, 1.0]
        
        Args:
            agent_id: Agent ID
            current_time: Current timestamp
            
        Returns:
            Normalized score from 0.0 to 1.0
        """
        weight = self.get_recency_weight(agent_id, current_time)
        
        # Normalize to 0-1 range
        range_width = self.max_boost - self.min_weight
        normalized = (weight - self.min_weight) / range_width
        
        return normalized
    
    def cleanup_old_entries(
        self,
        max_age_hours: float = 168.0,  # 1 week default
        current_time: Optional[float] = None
    ) -> int:
        """
        Remove very old activity entries to prevent memory growth.
        
        Args:
            max_age_hours: Maximum age to keep
            current_time: Current timestamp
            
        Returns:
            Number of entries removed
        """
        if current_time is None:
            current_time = time.time()
        
        cutoff_time = current_time - (max_age_hours * 3600.0)
        
        old_agents = [
            agent_id for agent_id, last_time in self.last_activity.items()
            if last_time < cutoff_time
        ]
        
        for agent_id in old_agents:
            del self.last_activity[agent_id]
        
        if old_agents:
            logger.info(f"Cleaned up {len(old_agents)} old activity entries")
        
        return len(old_agents)
    
    def get_stats(self) -> Dict[str, any]:
        """Get recency tracking statistics"""
        if not self.last_activity:
            return {
                "tracked_agents": 0,
                "oldest_activity": None,
                "newest_activity": None,
            }
        
        timestamps = list(self.last_activity.values())
        
        return {
            "tracked_agents": len(self.last_activity),
            "oldest_activity": min(timestamps),
            "newest_activity": max(timestamps),
        }


# Global instance
_global_weighter: RecencyWeighter = None


def get_recency_weighter(
    half_life_hours: float = 24.0,
    max_boost: float = 1.5,
    min_weight: float = 0.5
) -> RecencyWeighter:
    """Get or create global recency weighter"""
    global _global_weighter
    if _global_weighter is None:
        _global_weighter = RecencyWeighter(
            half_life_hours=half_life_hours,
            max_boost=max_boost,
            min_weight=min_weight
        )
    return _global_weighter


def reset_recency_weighter() -> None:
    """Reset global weighter (for testing)"""
    global _global_weighter
    _global_weighter = None
