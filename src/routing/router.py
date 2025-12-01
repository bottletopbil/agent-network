"""
Intelligent Router

Combines all routing stages into a complete pipeline:
Filter → Score → Canary → Bandit → Fallback to Auction
"""

from typing import Dict, Any, Optional
import logging

from .manifests import ManifestRegistry, get_registry
from .filters import CapabilityFilter, get_filter
from .scoring import AgentScorer, get_scorer
from .canary import CanaryRunner, get_canary_runner
from .winner_selection import WinnerSelector, get_winner_selector
from .bandit import ContextualBandit, get_bandit
from .features import FeatureExtractor, get_feature_extractor
from .feedback import collect_feedback
from .metrics import MetricsCollector, get_metrics_collector

logger = logging.getLogger(__name__)


class IntelligentRouter:
    """
    Complete intelligent routing pipeline.

    Stages:
    1. Filter: Capability-based filtering (50-100 agents)
    2. Score: Multi-factor scoring and shortlisting (top 10)
    3. Canary: Micro-task testing (top 2-3)
    4. Bandit: Select from canary winners using learned preferences
    5. Fallback: Auction if no winner found
    """

    def __init__(
        self,
        registry: Optional[ManifestRegistry] = None,
        filter: Optional[CapabilityFilter] = None,
        scorer: Optional[AgentScorer] = None,
        canary_runner: Optional[CanaryRunner] = None,
        winner_selector: Optional[WinnerSelector] = None,
        bandit: Optional[ContextualBandit] = None,
        feature_extractor: Optional[FeatureExtractor] = None,
        metrics_collector: Optional[MetricsCollector] = None,
        enable_canary: bool = True,
        enable_bandit: bool = True,
    ):
        """
        Initialize intelligent router.

        Args:
            registry: Agent manifest registry
            filter: Capability filter
            scorer: Agent scorer
            canary_runner: Canary test runner
            winner_selector: Winner selector
            bandit: Contextual bandit
            feature_extractor: Feature extractor
            metrics_collector: Metrics collector
            enable_canary: Whether to run canary tests
            enable_bandit: Whether to use bandit selection
        """
        self.registry = registry or get_registry()
        self.filter = filter or get_filter()
        self.scorer = scorer or get_scorer()
        self.canary_runner = canary_runner or get_canary_runner()
        self.winner_selector = winner_selector or get_winner_selector()
        self.bandit = bandit or get_bandit()
        self.feature_extractor = feature_extractor or get_feature_extractor()
        self.metrics = metrics_collector or get_metrics_collector()

        self.enable_canary = enable_canary
        self.enable_bandit = enable_bandit

    async def route_need(
        self, need: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Route a NEED to the best agent.

        Pipeline:
        1. Filter by capabilities
        2. Score and shortlist top K
        3. Run canary tests (optional)
        4. Use bandit to select from winners (optional)
        5. Return selected agent or None

        Args:
            need: Task NEED payload
            context: Additional context (stake amounts, etc.)

        Returns:
            Selected agent ID or None if routing failed
        """
        need_id = need.get("need_id", "unknown")

        # Start metrics tracking
        metrics = self.metrics.start_routing(need_id)

        try:
            logger.info(f"Starting intelligent routing for {need_id}")

            # Stage 1: Filter by capabilities
            all_agents = self.registry.get_all()
            logger.info(f"Stage 1 - Filtering {len(all_agents)} agents")

            qualified = self.filter.filter_all(need, all_agents)

            if not qualified:
                logger.warning("No agents passed filtering")
                self.metrics.complete_routing(
                    metrics, None, "filter", success=False, fallback_used=True
                )
                return None

            logger.info(f"Stage 1 - {len(qualified)} agents qualified")

            # Stage 2: Score and shortlist
            logger.info(f"Stage 2 - Scoring agents")

            top_k = min(10, len(qualified))
            scored = self.scorer.score_and_select(
                manifests=qualified,
                need=need,
                k=top_k,
                context=context,
                diversity_bonus=0.1,
            )

            if not scored:
                logger.warning("No agents after scoring")
                self.metrics.complete_routing(
                    metrics, None, "score", success=False, fallback_used=True
                )
                return None

            logger.info(f"Stage 2 - Top {len(scored)} agents selected")

            # Stage 3: Canary tests (optional)
            if self.enable_canary and len(scored) >= 2:
                logger.info(f"Stage 3 - Running canary tests")

                # Select top 2-3 for canary testing
                canary_count = min(3, len(scored))
                canary_candidates = [s.manifest.agent_id for s in scored[:canary_count]]

                # Create micro-task
                canary_test = self.canary_runner.create_micro_task(need)

                # Run canaries
                canary_results = await self.canary_runner.run_canaries(
                    canary_candidates, canary_test
                )

                # Select winner from canary results
                canary_winner = self.winner_selector.select_winner(canary_results)

                if canary_winner:
                    logger.info(f"Stage 3 - Canary winner: {canary_winner}")

                    # Stage 4: Bandit selection (optional)
                    if self.enable_bandit:
                        # Extract context and use bandit to confirm or override
                        features = self.feature_extractor.extract_context(need)

                        # Ensure canary winner is in bandit
                        self.bandit.add_arm(canary_winner)

                        # Use bandit for final selection among canary winners
                        # For now, trust canary result (could use bandit to choose among top
                        # canaries)
                        selected = canary_winner
                        routing_method = "bandit"
                    else:
                        selected = canary_winner
                        routing_method = "canary"

                    self.metrics.complete_routing(
                        metrics, selected, routing_method, success=True
                    )
                    return selected
                else:
                    logger.warning("No canary winner found")

            # Stage 4: Bandit selection (if canary skipped or failed)
            if self.enable_bandit:
                logger.info("Stage 4 - Using bandit selection")

                # Extract context
                features = self.feature_extractor.extract_context(need)

                # Ensure top agents are in bandit
                for scored_agent in scored:
                    self.bandit.add_arm(scored_agent.manifest.agent_id)

                # Use Thompson Sampling to select
                selected = self.bandit.thompson_sampling(context=features)

                if selected:
                    logger.info(f"Stage 4 - Bandit selected: {selected}")
                    self.metrics.complete_routing(
                        metrics, selected, "bandit", success=True
                    )
                    return selected

            # Fallback: Select top scored agent
            if scored:
                selected = scored[0].manifest.agent_id
                logger.info(f"Fallback - Using top scored agent: {selected}")
                self.metrics.complete_routing(metrics, selected, "score", success=True)
                return selected

            # No agent found
            logger.warning("No agent selected through routing pipeline")
            self.metrics.complete_routing(
                metrics, None, "none", success=False, fallback_used=True
            )
            return None

        except Exception as e:
            logger.error(f"Routing error: {e}")
            self.metrics.complete_routing(
                metrics, None, "error", success=False, fallback_used=True
            )
            return None

    def record_outcome(
        self,
        need_id: str,
        need: Dict[str, Any],
        agent_id: str,
        task_result: Dict[str, Any],
    ) -> None:
        """
        Record task outcome for bandit learning and metrics.

        Args:
            need_id: NEED identifier
            need: Original NEED payload
            agent_id: Agent that executed task
            task_result: Task execution result
        """
        # Calculate reward
        task_price = need.get("task_price", 10.0)
        max_price = need.get("max_price", 100.0)

        reward = collect_feedback(
            task_result=task_result,
            agent_id=agent_id,
            task_price=task_price,
            max_price=max_price,
        )

        # Extract context
        features = self.feature_extractor.extract_context(need)

        # Update bandit
        if self.enable_bandit:
            self.bandit.update(agent_id, reward=reward, context=features)

        # Record metrics
        self.metrics.record_outcome(
            need_id=need_id, agent_id=agent_id, actual_reward=reward
        )

        logger.info(
            f"Recorded outcome: need={need_id}, agent={agent_id}, reward={reward:.2f}"
        )

    def get_stats(self) -> Dict:
        """Get router statistics"""
        return {
            "routing_metrics": self.metrics.get_stats(),
            "bandit_stats": self.bandit.get_stats() if self.enable_bandit else {},
            "registry_stats": self.registry.get_stats(),
        }


# Global router instance
_global_router: Optional[IntelligentRouter] = None


def get_router(
    enable_canary: bool = True, enable_bandit: bool = True
) -> IntelligentRouter:
    """Get or create global intelligent router"""
    global _global_router
    if _global_router is None:
        _global_router = IntelligentRouter(
            enable_canary=enable_canary, enable_bandit=enable_bandit
        )
    return _global_router


def reset_router() -> None:
    """Reset global router (for testing)"""
    global _global_router
    _global_router = None
