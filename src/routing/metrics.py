"""
Routing Metrics

Tracks performance and accuracy of the intelligent routing system.
"""

from typing import Dict, List, Optional
import time
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RoutingMetrics:
    """Metrics for a single routing decision"""
    need_id: str
    start_time: float
    end_time: Optional[float] = None
    selected_agent: Optional[str] = None
    routing_method: str = "unknown"  # filter, score, canary, bandit, auction
    success: bool = False
    fallback_used: bool = False
    
    @property
    def latency_ms(self) -> float:
        """Time to make routing decision (ms)"""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000.0
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary"""
        return {
            "need_id": self.need_id,
            "latency_ms": self.latency_ms,
            "selected_agent": self.selected_agent,
            "routing_method": self.routing_method,
            "success": self.success,
            "fallback_used": self.fallback_used,
        }


class MetricsCollector:
    """
    Collects and aggregates routing metrics.
    
    Tracks:
    - Routing success rate
    - Time-to-assignment
    - Routing accuracy
    - Method usage
    """
    
    def __init__(self):
        self.routing_history: List[RoutingMetrics] = []
        self.outcome_history: List[Dict] = []  # Actual task outcomes
    
    def start_routing(self, need_id: str) -> RoutingMetrics:
        """
        Start tracking a routing decision.
        
        Args:
            need_id: NEED identifier
            
        Returns:
            RoutingMetrics object
        """
        metrics = RoutingMetrics(
            need_id=need_id,
            start_time=time.time()
        )
        
        return metrics
    
    def complete_routing(
        self,
        metrics: RoutingMetrics,
        selected_agent: Optional[str],
        routing_method: str,
        success: bool,
        fallback_used: bool = False
    ) -> None:
        """
        Complete routing and record metrics.
        
        Args:
            metrics: RoutingMetrics object from start_routing
            selected_agent: Agent that was selected
            routing_method: Method used (filter, score, canary, bandit, auction)
            success: Whether routing succeeded
            fallback_used: Whether fallback was used
        """
        metrics.end_time = time.time()
        metrics.selected_agent = selected_agent
        metrics.routing_method = routing_method
        metrics.success = success
        metrics.fallback_used = fallback_used
        
        self.routing_history.append(metrics)
        
        logger.info(
            f"Routing completed: need={metrics.need_id}, "
            f"agent={selected_agent}, method={routing_method}, "
            f"latency={metrics.latency_ms:.1f}ms, success={success}"
        )
    
    def record_outcome(
        self,
        need_id: str,
        agent_id: str,
        actual_reward: float,
        predicted_reward: Optional[float] = None
    ) -> None:
        """
        Record actual task outcome for accuracy tracking.
        
        Args:
            need_id: NEED identifier
            agent_id: Agent that executed task
            actual_reward: Actual reward received
            predicted_reward: Predicted reward (if available)
        """
        outcome = {
            "need_id": need_id,
            "agent_id": agent_id,
            "actual_reward": actual_reward,
            "predicted_reward": predicted_reward,
        }
        
        self.outcome_history.append(outcome)
    
    def get_success_rate(self, recent_n: Optional[int] = None) -> float:
        """
        Get routing success rate.
        
        Args:
            recent_n: Only consider recent N routings (None = all)
            
        Returns:
            Success rate from 0.0 to 1.0
        """
        history = self.routing_history
        if recent_n is not None:
            history = history[-recent_n:]
        
        if not history:
            return 0.0
        
        successes = sum(1 for m in history if m.success)
        return successes / len(history)
    
    def get_avg_latency_ms(self, recent_n: Optional[int] = None) -> float:
        """
        Get average time-to-assignment.
        
        Args:
            recent_n: Only consider recent N routings
            
        Returns:
            Average latency in milliseconds
        """
        history = self.routing_history
        if recent_n is not None:
            history = history[-recent_n:]
        
        if not history:
            return 0.0
        
        total_latency = sum(m.latency_ms for m in history)
        return total_latency / len(history)
    
    def get_fallback_rate(self, recent_n: Optional[int] = None) -> float:
        """
        Get rate of fallback to auction.
        
        Args:
            recent_n: Only consider recent N routings
            
        Returns:
            Fallback rate from 0.0 to 1.0
        """
        history = self.routing_history
        if recent_n is not None:
            history = history[-recent_n:]
        
        if not history:
            return 0.0
        
        fallbacks = sum(1 for m in history if m.fallback_used)
        return fallbacks / len(history)
    
    def get_method_distribution(self) -> Dict[str, int]:
        """
        Get distribution of routing methods used.
        
        Returns:
            Dictionary of method -> count
        """
        distribution = {}
        
        for metrics in self.routing_history:
            method = metrics.routing_method
            distribution[method] = distribution.get(method, 0) + 1
        
        return distribution
    
    def get_routing_accuracy(self) -> float:
        """
        Get routing accuracy (how often we selected the best agent).
        
        Compares selected agent's actual reward to all available agents.
        
        Returns:
            Accuracy from 0.0 (worst) to 1.0 (perfect)
        """
        if not self.outcome_history:
            return 0.0
        
        # Simple accuracy: proportion where actual_reward >= 0.7 (good performance)
        good_outcomes = sum(
            1 for outcome in self.outcome_history
            if outcome["actual_reward"] >= 0.7
        )
        
        return good_outcomes / len(self.outcome_history)
    
    def get_stats(self) -> Dict:
        """
        Get comprehensive routing statistics.
        
        Returns:
            Dictionary of statistics
        """
        return {
            "total_routings": len(self.routing_history),
            "success_rate": self.get_success_rate(),
            "avg_latency_ms": self.get_avg_latency_ms(),
            "fallback_rate": self.get_fallback_rate(),
            "method_distribution": self.get_method_distribution(),
            "routing_accuracy": self.get_routing_accuracy(),
            "total_outcomes": len(self.outcome_history),
        }
    
    def clear(self) -> None:
        """Clear all metrics"""
        self.routing_history.clear()
        self.outcome_history.clear()


# Global metrics collector
_global_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create global metrics collector"""
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector()
    return _global_collector


def reset_metrics_collector() -> None:
    """Reset global collector (for testing)"""
    global _global_collector
    _global_collector = MetricsCollector()
