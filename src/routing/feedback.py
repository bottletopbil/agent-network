"""
Feedback Collection System

Collects and calculates reward signals for bandit learning.
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def collect_feedback(
    task_result: Dict[str, Any],
    agent_id: str,
    task_price: float,
    max_price: float = 100.0
) -> float:
    """
    Calculate reward from task execution.
    
    Reward formula:
    reward = quality × speed × (1 - cost_ratio)
    
    Where:
    - quality: 0.0 (failure) to 1.0 (perfect)
    - speed: 1.0 (fast) to 0.0 (slow), based on latency
    - cost_ratio: actual_cost / max_acceptable_cost
    
    Args:
        task_result: Task execution result with quality and latency metrics
        agent_id: Agent that executed the task
        task_price: Actual price charged
        max_price: Maximum acceptable price
        
    Returns:
        Reward from 0.0 (worst) to 1.0 (best)
    """
    # Extract quality (0.0 - 1.0)
    quality = task_result.get("quality_score", 0.5)
    quality = max(0.0, min(1.0, quality))
    
    # Extract latency and convert to speed score
    latency_ms = task_result.get("latency_ms", 5000.0)
    max_latency = task_result.get("max_latency_ms", 10000.0)
    
    # Speed: 1.0 if instant, 0.0 if at max latency
    if max_latency > 0:
        speed = max(0.0, 1.0 - (latency_ms / max_latency))
    else:
        speed = 0.5
    
    # Calculate cost ratio
    if max_price > 0:
        cost_ratio = task_price / max_price
    else:
        cost_ratio = 0.0
    
    # Cost factor: rewards lower cost
    # (1 - cost_ratio) means:
    # - cost = 0 → factor = 1.0 (best)
    # - cost = max → factor = 0.0 (worst)
    cost_factor = max(0.0, 1.0 - cost_ratio)
    
    # Combined reward (multiplicative)
    reward = quality * speed * cost_factor
    
    logger.debug(
        f"Feedback for {agent_id}: quality={quality:.2f}, "
        f"speed={speed:.2f}, cost_factor={cost_factor:.2f}, "
        f"reward={reward:.2f}"
    )
    
    return reward


def calculate_binary_reward(task_result: Dict[str, Any]) -> float:
    """
    Simple binary reward: 1.0 for success, 0.0 for failure.
    
    Args:
        task_result: Task execution result
        
    Returns:
        1.0 if successful, 0.0 otherwise
    """
    success = task_result.get("success", False)
    return 1.0 if success else 0.0


def calculate_quality_reward(task_result: Dict[str, Any]) -> float:
    """
    Quality-based reward (ignores latency and cost).
    
    Args:
        task_result: Task execution result
        
    Returns:
        Quality score from 0.0 to 1.0
    """
    quality = task_result.get("quality_score", 0.0)
    return max(0.0, min(1.0, quality))


class FeedbackCollector:
    """
    Collects and aggregates feedback over time.
    
    Tracks feedback for analysis and debugging.
    """
    
    def __init__(self):
        self.feedback_history: list[Dict[str, Any]] = []
    
    def record_feedback(
        self,
        task_id: str,
        agent_id: str,
        reward: float,
        task_result: Dict[str, Any]
    ) -> None:
        """
        Record feedback for later analysis.
        
        Args:
            task_id: Task identifier
            agent_id: Agent that executed task
            reward: Calculated reward
            task_result: Full task result
        """
        feedback = {
            "task_id": task_id,
            "agent_id": agent_id,
            "reward": reward,
            "quality": task_result.get("quality_score"),
            "latency_ms": task_result.get("latency_ms"),
            "price": task_result.get("price"),
        }
        
        self.feedback_history.append(feedback)
        
        logger.info(f"Recorded feedback: task={task_id}, agent={agent_id}, reward={reward:.2f}")
    
    def get_agent_stats(self, agent_id: str) -> Dict[str, float]:
        """
        Get aggregated stats for an agent.
        
        Args:
            agent_id: Agent to analyze
            
        Returns:
            Dictionary of statistics
        """
        agent_feedback = [
            f for f in self.feedback_history
            if f["agent_id"] == agent_id
        ]
        
        if not agent_feedback:
            return {
                "count": 0,
                "avg_reward": 0.0,
                "avg_quality": 0.0,
                "avg_latency_ms": 0.0,
            }
        
        return {
            "count": len(agent_feedback),
            "avg_reward": sum(f["reward"] for f in agent_feedback) / len(agent_feedback),
            "avg_quality": sum(
                f["quality"] for f in agent_feedback if f["quality"] is not None
            ) / len(agent_feedback),
            "avg_latency_ms": sum(
                f["latency_ms"] for f in agent_feedback if f["latency_ms"] is not None
            ) / len(agent_feedback),
        }
    
    def clear(self) -> None:
        """Clear feedback history"""
        self.feedback_history.clear()


# Global feedback collector
_global_collector: Optional[FeedbackCollector] = None


def get_feedback_collector() -> FeedbackCollector:
    """Get or create global feedback collector"""
    global _global_collector
    if _global_collector is None:
        _global_collector = FeedbackCollector()
    return _global_collector


def reset_feedback_collector() -> None:
    """Reset global collector (for testing)"""
    global _global_collector
    _global_collector = FeedbackCollector()
