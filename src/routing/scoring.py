"""
Agent Scoring System

Scores agents using multiple factors and selects top candidates.
Supports diversity adjustments and configurable weighting.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

from .manifests import AgentManifest
from .domain_fit import DomainFitCalculator, get_domain_fit_calculator
from .recency import RecencyWeighter, get_recency_weighter

logger = logging.getLogger(__name__)


@dataclass
class ScoredAgent:
    """Agent with computed score and breakdown"""

    manifest: AgentManifest
    total_score: float
    score_breakdown: Dict[str, float]  # Component scores

    def __lt__(self, other: "ScoredAgent") -> bool:
        """Enable sorting by score (descending)"""
        return self.total_score > other.total_score


class AgentScorer:
    """
    Scores agents using configurable multi-factor formula.

    Factors:
    - Reputation (success_rate)
    - Price (inverse, normalized)
    - Latency (inverse, normalized)
    - Domain fit (semantic similarity)
    - Stake (economic commitment)
    - Recency (recent activity)
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        domain_fit_calculator: Optional[DomainFitCalculator] = None,
        recency_weighter: Optional[RecencyWeighter] = None,
    ):
        """
        Initialize agent scorer.

        Args:
            weights: Factor weights (defaults to equal weighting)
            domain_fit_calculator: Domain fit calculator instance
            recency_weighter: Recency weighter instance
        """
        # Default weights (sum to 1.0)
        self.weights = weights or {
            "reputation": 0.25,
            "price": 0.15,
            "latency": 0.15,
            "domain_fit": 0.25,
            "stake": 0.10,
            "recency": 0.10,
        }

        # Validate weights sum to ~1.0
        total_weight = sum(self.weights.values())
        if abs(total_weight - 1.0) > 0.01:
            logger.warning(f"Weights sum to {total_weight}, not 1.0. Normalizing.")
            self.weights = {k: v / total_weight for k, v in self.weights.items()}

        self.domain_fit_calc = domain_fit_calculator or get_domain_fit_calculator()
        self.recency_weighter = recency_weighter or get_recency_weighter()

    def score_agent(
        self,
        agent_manifest: AgentManifest,
        need: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ScoredAgent:
        """
        Score a single agent for a task.

        Args:
            agent_manifest: Agent to score
            need: Task requirements
            context: Additional context (stake amounts, etc.)

        Returns:
            ScoredAgent with total score and breakdown
        """
        context = context or {}

        # Compute component scores
        scores = {}

        # 1. Reputation (0.0 - 1.0, higher is better)
        # Prefer DID-based reputation if available (identity manifests),
        # fallback to success_rate (routing manifests) for compatibility
        reputation = getattr(agent_manifest, "reputation", None)
        if reputation is None:
            reputation = getattr(agent_manifest, "success_rate", 0.8)
        scores["reputation"] = reputation

        # 2. Price (0.0 - 1.0, lower price is better)
        max_price = need.get("max_price", 100.0)
        if max_price > 0:
            # Inverse score: cheaper = higher score
            price_score = 1.0 - min(agent_manifest.price_per_task / max_price, 1.0)
        else:
            price_score = 0.5
        scores["price"] = price_score

        # 3. Latency (0.0 - 1.0, lower latency is better)
        max_latency = need.get("max_latency_ms", 5000.0)
        if max_latency > 0:
            latency_score = 1.0 - min(agent_manifest.avg_latency_ms / max_latency, 1.0)
        else:
            latency_score = 0.5
        scores["latency"] = latency_score

        # 4. Domain fit (0.0 - 1.0)
        task_tags = need.get("tags", [])
        task_capabilities = need.get("capabilities", [])

        domain_fit = self.domain_fit_calc.compute_fit(
            task_tags=task_tags,
            task_capabilities=task_capabilities,
            agent_tags=agent_manifest.tags,
            agent_capabilities=agent_manifest.capabilities,
            agent_id=agent_manifest.agent_id,
        )
        scores["domain_fit"] = domain_fit

        # 5. Stake (0.0 - 1.0, normalized)
        agent_stake = context.get("agent_stakes", {}).get(agent_manifest.agent_id, 0.0)
        max_stake = context.get("max_stake", 1000.0)

        if max_stake > 0:
            stake_score = min(agent_stake / max_stake, 1.0)
        else:
            stake_score = 0.5
        scores["stake"] = stake_score

        # 6. Recency (0.0 - 1.0)
        recency_score = self.recency_weighter.get_recency_score(agent_manifest.agent_id)
        scores["recency"] = recency_score

        # Compute weighted total
        total_score = sum(
            self.weights.get(factor, 0.0) * score for factor, score in scores.items()
        )

        return ScoredAgent(
            manifest=agent_manifest, total_score=total_score, score_breakdown=scores
        )

    def score_agents(
        self,
        manifests: List[AgentManifest],
        need: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[ScoredAgent]:
        """
        Score multiple agents.

        Args:
            manifests: Agents to score
            need: Task requirements
            context: Additional context

        Returns:
            List of scored agents (unsorted)
        """
        return [self.score_agent(manifest, need, context) for manifest in manifests]

    def adjust_for_diversity(
        self, scored_agents: List[ScoredAgent], diversity_bonus: float = 0.1
    ) -> List[ScoredAgent]:
        """
        Adjust scores to boost diversity.

        Gives bonus to under-represented organizations/zones.

        Args:
            scored_agents: Agents with scores
            diversity_bonus: Bonus multiplier for diversity (e.g., 0.1 = 10% boost)

        Returns:
            Agents with adjusted scores
        """
        if not scored_agents or diversity_bonus == 0:
            return scored_agents

        # Count agents per zone
        zone_counts: Dict[str, int] = {}
        for scored in scored_agents:
            zone = scored.manifest.zone or "unknown"
            zone_counts[zone] = zone_counts.get(zone, 0) + 1

        # Apply diversity bonus (inversely proportional to zone count)
        adjusted = []
        for scored in scored_agents:
            zone = scored.manifest.zone or "unknown"
            zone_count = zone_counts[zone]

            # Bonus inversely proportional to frequency
            # More common zones get smaller bonus
            diversity_multiplier = 1.0 + (diversity_bonus / zone_count)

            adjusted_score = scored.total_score * diversity_multiplier

            adjusted_breakdown = scored.score_breakdown.copy()
            adjusted_breakdown["diversity_bonus"] = diversity_multiplier - 1.0

            adjusted.append(
                ScoredAgent(
                    manifest=scored.manifest,
                    total_score=adjusted_score,
                    score_breakdown=adjusted_breakdown,
                )
            )

        return adjusted

    def select_top_k(
        self, scored_agents: List[ScoredAgent], k: int
    ) -> List[ScoredAgent]:
        """
        Select top K agents by score.

        Sorts by score (descending) and returns top K.
        Ties broken by agent_id (lexicographic).

        Args:
            scored_agents: Agents with scores
            k: Number to select

        Returns:
            Top K agents sorted by score (best first)
        """
        if not scored_agents:
            return []

        # Sort by score (descending), then by agent_id (ascending) for tie-breaking
        sorted_agents = sorted(
            scored_agents, key=lambda x: (-x.total_score, x.manifest.agent_id)
        )

        return sorted_agents[:k]

    def score_and_select(
        self,
        manifests: List[AgentManifest],
        need: Dict[str, Any],
        k: int = 10,
        context: Optional[Dict[str, Any]] = None,
        diversity_bonus: float = 0.1,
    ) -> List[ScoredAgent]:
        """
        Complete scoring pipeline: score, adjust for diversity, select top K.

        Args:
            manifests: Agents to score
            need: Task requirements
            k: Number of top agents to select
            context: Additional context
            diversity_bonus: Diversity adjustment bonus

        Returns:
            Top K agents with scores
        """
        logger.info(f"Scoring {len(manifests)} agents for selection")

        # Score all agents
        scored = self.score_agents(manifests, need, context)

        # Adjust for diversity
        if diversity_bonus > 0:
            scored = self.adjust_for_diversity(scored, diversity_bonus)

        # Select top K
        top_k = self.select_top_k(scored, k)

        logger.info(f"Selected top {len(top_k)} agents")

        return top_k


# Global scorer instance
_global_scorer: Optional[AgentScorer] = None


def get_scorer(weights: Optional[Dict[str, float]] = None) -> AgentScorer:
    """Get or create global agent scorer"""
    global _global_scorer
    if _global_scorer is None or weights is not None:
        _global_scorer = AgentScorer(weights=weights)
    return _global_scorer


def reset_scorer() -> None:
    """Reset global scorer (for testing)"""
    global _global_scorer
    _global_scorer = None
