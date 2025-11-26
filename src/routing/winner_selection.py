"""
Winner Selection

Selects the best agent from canary test results.
Compares quality scores with latency as tiebreaker.
"""

from typing import List, Optional, Tuple
import logging

from .canary import CanaryResult

logger = logging.getLogger(__name__)


class WinnerSelector:
    """
    Selects winner from canary test results.
    
    Prioritizes:
    1. Quality score (must meet minimum threshold)
    2. Latency (lower is better for tiebreaking)
    """
    
    def __init__(
        self,
        min_quality_threshold: float = 0.6,
        quality_weight: float = 0.7,
        latency_weight: float = 0.3
    ):
        """
        Initialize winner selector.
        
        Args:
            min_quality_threshold: Minimum quality to be considered
            quality_weight: Weight for quality in combined score
            latency_weight: Weight for latency in combined score
        """
        self.min_quality_threshold = min_quality_threshold
        self.quality_weight = quality_weight
        self.latency_weight = latency_weight
        
        # Normalize weights
        total = quality_weight + latency_weight
        self.quality_weight /= total
        self.latency_weight /= total
    
    def select_winner(
        self,
        canary_results: List[CanaryResult]
    ) -> Optional[str]:
        """
        Select the best agent from canary results.
        
        Algorithm:
        1. Filter to agents meeting minimum quality threshold
        2. If multiple agents tie on quality, use latency as tiebreaker
        3. Return agent_id of winner
        
        Args:
            canary_results: Results from canary tests
            
        Returns:
            Agent ID of winner, or None if no qualified agents
        """
        if not canary_results:
            logger.warning("No canary results to select from")
            return None
        
        # Filter to passing results
        qualified = [
            result for result in canary_results
            if result.passed and result.quality_score >= self.min_quality_threshold
        ]
        
        if not qualified:
            logger.warning(
                f"No agents met quality threshold {self.min_quality_threshold}. "
                f"Best score: {max(r.quality_score for r in canary_results):.2f}"
            )
            return None
        
        # Sort by quality (descending), then latency (ascending)
        sorted_results = sorted(
            qualified,
            key=lambda r: (-r.quality_score, r.latency_ms)
        )
        
        winner = sorted_results[0]
        
        logger.info(
            f"Selected winner: {winner.agent_id} "
            f"(quality: {winner.quality_score:.2f}, latency: {winner.latency_ms:.1f}ms)"
        )
        
        return winner.agent_id
    
    def select_winner_with_score(
        self,
        canary_results: List[CanaryResult]
    ) -> Optional[Tuple[str, float]]:
        """
        Select winner and return combined score.
        
        Args:
            canary_results: Results from canary tests
            
        Returns:
            Tuple of (agent_id, combined_score) or None
        """
        winner_id = self.select_winner(canary_results)
        
        if winner_id is None:
            return None
        
        # Find winner's result
        winner_result = next(
            r for r in canary_results
            if r.agent_id == winner_id
        )
        
        # Calculate combined score
        combined_score = self._combined_score(winner_result, canary_results)
        
        return (winner_id, combined_score)
    
    def rank_all(
        self,
        canary_results: List[CanaryResult]
    ) -> List[Tuple[str, float]]:
        """
        Rank all qualified agents.
        
        Args:
            canary_results: Results from canary tests
            
        Returns:
            List of (agent_id, combined_score) tuples, sorted by score
        """
        # Filter to qualified
        qualified = [
            result for result in canary_results
            if result.passed and result.quality_score >= self.min_quality_threshold
        ]
        
        # Calculate combined scores
        scored = [
            (result.agent_id, self._combined_score(result, canary_results))
            for result in qualified
        ]
        
        # Sort by score (descending)
        scored.sort(key=lambda x: -x[1])
        
        return scored
    
    def _combined_score(
        self,
        result: CanaryResult,
        all_results: List[CanaryResult]
    ) -> float:
        """
        Calculate combined score from quality and latency.
        
        Normalizes latency relative to all results.
        
        Args:
            result: Result to score
            all_results: All results (for normalization)
            
        Returns:
            Combined score from 0.0 to 1.0
        """
        quality_score = result.quality_score
        
        # Normalize latency (0.0 = slowest, 1.0 = fastest)
        latencies = [r.latency_ms for r in all_results if r.latency_ms > 0]
        
        if not latencies or min(latencies) == max(latencies):
            latency_score = 0.5
        else:
            # Inverse normalization (lower latency = higher score)
            max_lat = max(latencies)
            min_lat = min(latencies)
            latency_score = 1.0 - (result.latency_ms - min_lat) / (max_lat - min_lat)
        
        # Weighted combination
        combined = (
            self.quality_weight * quality_score +
            self.latency_weight * latency_score
        )
        
        return combined
    
    def get_stats(self, canary_results: List[CanaryResult]) -> dict:
        """
        Get statistics about canary results.
        
        Args:
            canary_results: Results to analyze
            
        Returns:
            Dictionary of statistics
        """
        if not canary_results:
            return {
                "total": 0,
                "passed": 0,
                "qualified": 0,
                "pass_rate": 0.0
            }
        
        passed = sum(1 for r in canary_results if r.passed)
        qualified = sum(
            1 for r in canary_results
            if r.passed and r.quality_score >= self.min_quality_threshold
        )
        
        return {
            "total": len(canary_results),
            "passed": passed,
            "qualified": qualified,
            "pass_rate": passed / len(canary_results),
            "qualification_rate": qualified / len(canary_results),
            "avg_quality": sum(r.quality_score for r in canary_results) / len(canary_results),
            "avg_latency_ms": sum(r.latency_ms for r in canary_results) / len(canary_results),
        }


# Global selector instance
_global_selector: Optional[WinnerSelector] = None


def get_winner_selector(
    min_quality_threshold: float = 0.6,
    quality_weight: float = 0.7,
    latency_weight: float = 0.3
) -> WinnerSelector:
    """Get or create global winner selector"""
    global _global_selector
    if _global_selector is None:
        _global_selector = WinnerSelector(
            min_quality_threshold=min_quality_threshold,
            quality_weight=quality_weight,
            latency_weight=latency_weight
        )
    return _global_selector


def reset_winner_selector() -> None:
    """Reset global selector (for testing)"""
    global _global_selector
    _global_selector = None
