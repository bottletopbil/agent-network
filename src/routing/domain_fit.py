"""
Domain Fit Calculator

Computes semantic similarity between task requirements and agent capabilities.
Tracks past performance in specific domains.
"""

from typing import List, Dict, Any, Set
import logging
import math

logger = logging.getLogger(__name__)


class DomainFitCalculator:
    """
    Calculates domain fit score between task and agent.

    Combines:
    - Tag similarity (Jaccard similarity)
    - Past performance in domain
    - Capability overlap
    """

    def __init__(self):
        # Track past performance: domain -> agent_id -> success_rate
        self.performance_history: Dict[str, Dict[str, float]] = {}

    def compute_fit(
        self,
        task_tags: List[str],
        task_capabilities: List[str],
        agent_tags: List[str],
        agent_capabilities: List[str],
        agent_id: str,
    ) -> float:
        """
        Compute overall domain fit score.

        Args:
            task_tags: Tags from task requirement
            task_capabilities: Required capabilities
            agent_tags: Agent's tags
            agent_capabilities: Agent's capabilities
            agent_id: Agent ID for performance lookup

        Returns:
            Fit score from 0.0 (no fit) to 1.0 (perfect fit)
        """
        # Tag similarity (0.0 - 1.0)
        tag_sim = self.tag_similarity(task_tags, agent_tags)

        # Capability overlap (0.0 - 1.0)
        cap_overlap = self.capability_overlap(task_capabilities, agent_capabilities)

        # Past performance in domain (0.0 - 1.0)
        domain = self._infer_domain(task_tags)
        perf_score = self.get_performance_score(domain, agent_id)

        # Weighted combination
        fit_score = 0.4 * tag_sim + 0.4 * cap_overlap + 0.2 * perf_score

        return fit_score

    def tag_similarity(self, tags1: List[str], tags2: List[str]) -> float:
        """
        Compute Jaccard similarity between tag sets.

        Jaccard = |intersection| / |union|

        Args:
            tags1: First tag set
            tags2: Second tag set

        Returns:
            Similarity from 0.0 to 1.0
        """
        if not tags1 and not tags2:
            return 1.0  # Both empty = perfect match

        if not tags1 or not tags2:
            return 0.0  # One empty = no match

        set1 = set(tags1)
        set2 = set(tags2)

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        if union == 0:
            return 0.0

        return intersection / union

    def capability_overlap(self, required: List[str], provided: List[str]) -> float:
        """
        Compute capability overlap score.

        Score = |required ∩ provided| / |required|

        Args:
            required: Required capabilities
            provided: Agent's capabilities

        Returns:
            Overlap from 0.0 (none) to 1.0 (all required)
        """
        if not required:
            return 1.0  # No requirements = perfect match

        if not provided:
            return 0.0  # No capabilities = no match

        req_set = set(required)
        prov_set = set(provided)

        overlap = len(req_set & prov_set)

        return overlap / len(req_set)

    def record_performance(self, domain: str, agent_id: str, success: bool) -> None:
        """
        Record agent performance in a domain.

        Uses exponential moving average to track success rate.

        Args:
            domain: Domain identifier
            agent_id: Agent ID
            success: Whether task succeeded
        """
        if domain not in self.performance_history:
            self.performance_history[domain] = {}

        current_rate = self.performance_history[domain].get(agent_id, 0.5)

        # Exponential moving average (alpha = 0.3)
        alpha = 0.3
        new_value = 1.0 if success else 0.0
        updated_rate = alpha * new_value + (1 - alpha) * current_rate

        self.performance_history[domain][agent_id] = updated_rate

        logger.debug(
            f"Performance: {agent_id} in {domain}: {current_rate:.2f} → {updated_rate:.2f}"
        )

    def get_performance_score(self, domain: str, agent_id: str) -> float:
        """
        Get agent's performance score in a domain.

        Args:
            domain: Domain identifier
            agent_id: Agent ID

        Returns:
            Performance score from 0.0 to 1.0 (default 0.5 if unknown)
        """
        if domain not in self.performance_history:
            return 0.5  # Neutral score for unknown domain

        return self.performance_history[domain].get(agent_id, 0.5)

    def _infer_domain(self, tags: List[str]) -> str:
        """
        Infer domain from tags.

        Simple heuristic: use primary tag or combination.

        Args:
            tags: Task tags

        Returns:
            Domain identifier
        """
        if not tags:
            return "general"

        # Sort tags for consistent domain naming
        sorted_tags = sorted(tags)

        # Use first tag as primary domain
        # Could be more sophisticated (e.g., tag ontology)
        return sorted_tags[0]

    def get_stats(self) -> Dict[str, Any]:
        """Get performance tracking statistics"""
        return {
            "domains_tracked": len(self.performance_history),
            "total_agents": sum(
                len(agents) for agents in self.performance_history.values()
            ),
        }


# Global instance
_global_calculator: DomainFitCalculator = None


def get_domain_fit_calculator() -> DomainFitCalculator:
    """Get or create global domain fit calculator"""
    global _global_calculator
    if _global_calculator is None:
        _global_calculator = DomainFitCalculator()
    return _global_calculator


def reset_domain_fit_calculator() -> None:
    """Reset global calculator (for testing)"""
    global _global_calculator
    _global_calculator = DomainFitCalculator()
