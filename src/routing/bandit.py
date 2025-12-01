"""
Contextual Bandit Learning

Implements Thompson Sampling and UCB1 for agent selection with contextual learning.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import random
import math
import logging

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    logging.warning("NumPy not available, using fallback implementations")

logger = logging.getLogger(__name__)


@dataclass
class ArmStats:
    """
    Statistics for a bandit arm (agent).

    Tracks successes, failures, and contexts seen.
    """

    successes: int = 0
    failures: int = 0
    contexts_seen: List[List[float]] = field(default_factory=list)
    total_reward: float = 0.0
    pulls: int = 0

    @property
    def alpha(self) -> float:
        """Alpha parameter for Beta distribution (successes + 1)"""
        return self.successes + 1

    @property
    def beta(self) -> float:
        """Beta parameter for Beta distribution (failures + 1)"""
        return self.failures + 1

    @property
    def mean_reward(self) -> float:
        """Mean reward"""
        return self.total_reward / self.pulls if self.pulls > 0 else 0.0

    def to_dict(self) -> Dict:
        """Serialize to dictionary"""
        return {
            "successes": self.successes,
            "failures": self.failures,
            "total_reward": self.total_reward,
            "pulls": self.pulls,
            "mean_reward": self.mean_reward,
        }


class ContextualBandit:
    """
    Contextual multi-armed bandit for agent selection.

    Implements:
    - Thompson Sampling (Bayesian approach)
    - UCB1 (Upper Confidence Bound)
    """

    def __init__(self, arms: Optional[List[str]] = None, exploration_bonus: float = 2.0):
        """
        Initialize contextual bandit.

        Args:
            arms: List of arm IDs (agent IDs)
            exploration_bonus: Exploration parameter for UCB1
        """
        self.arms: Dict[str, ArmStats] = {}
        self.exploration_bonus = exploration_bonus
        self.total_pulls = 0

        if arms:
            for arm in arms:
                self.arms[arm] = ArmStats()

    def add_arm(self, arm_id: str) -> None:
        """
        Add a new arm (agent).

        Args:
            arm_id: Arm ID to add
        """
        if arm_id not in self.arms:
            self.arms[arm_id] = ArmStats()
            logger.info(f"Added arm: {arm_id}")

    def thompson_sampling(self, context: Optional[List[float]] = None) -> Optional[str]:
        """
        Select arm using Thompson Sampling.

        Samples from Beta(α, β) for each arm and selects highest sample.

        Args:
            context: Contextual features (not used in basic Thompson Sampling)

        Returns:
            Selected arm ID or None if no arms
        """
        if not self.arms:
            logger.warning("No arms available for selection")
            return None

        # Sample from Beta distribution for each arm
        samples = {}

        for arm_id, stats in self.arms.items():
            # Beta distribution sampling
            if HAS_NUMPY:
                sample = np.random.beta(stats.alpha, stats.beta)
            else:
                # Fallback: use mean with random noise
                mean = stats.alpha / (stats.alpha + stats.beta)
                noise = random.gauss(0, 0.1)
                sample = max(0.0, min(1.0, mean + noise))

            samples[arm_id] = sample

        # Select arm with highest sample
        selected = max(samples.items(), key=lambda x: x[1])[0]

        logger.debug(f"Thompson Sampling selected: {selected} (samples: {samples})")

        return selected

    def ucb1(
        self,
        context: Optional[List[float]] = None,
        exploration_bonus: Optional[float] = None,
    ) -> Optional[str]:
        """
        Select arm using UCB1 algorithm.

        UCB1 formula:
        UCB = mean_reward + c * sqrt(ln(total_pulls) / arm_pulls)

        Args:
            context: Contextual features (not used in basic UCB1)
            exploration_bonus: Override exploration parameter (default: use self.exploration_bonus)

        Returns:
            Selected arm ID or None if no arms
        """
        if not self.arms:
            logger.warning("No arms available for selection")
            return None

        if exploration_bonus is None:
            exploration_bonus = self.exploration_bonus

        # Select unpulled arms first
        unpulled = [arm_id for arm_id, stats in self.arms.items() if stats.pulls == 0]
        if unpulled:
            selected = random.choice(unpulled)
            logger.debug(f"UCB1 selected unpulled arm: {selected}")
            return selected

        # Calculate UCB for each arm
        ucb_values = {}

        for arm_id, stats in self.arms.items():
            mean_reward = stats.mean_reward

            # Exploration bonus
            bonus = exploration_bonus * math.sqrt(math.log(self.total_pulls) / stats.pulls)

            ucb = mean_reward + bonus
            ucb_values[arm_id] = ucb

        # Select arm with highest UCB
        selected = max(ucb_values.items(), key=lambda x: x[1])[0]

        logger.debug(f"UCB1 selected: {selected} (UCB values: {ucb_values})")

        return selected

    def update(self, agent_id: str, reward: float, context: Optional[List[float]] = None) -> None:
        """
        Update arm statistics with observed reward.

        Args:
            agent_id: Arm that was pulled
            reward: Observed reward (0.0 - 1.0)
            context: Contextual features used for selection
        """
        # Ensure arm exists
        if agent_id not in self.arms:
            self.add_arm(agent_id)

        stats = self.arms[agent_id]

        # Update counts
        stats.pulls += 1
        self.total_pulls += 1

        # Update reward
        stats.total_reward += reward

        # Update success/failure (for Thompson Sampling)
        # Treat reward as success probability
        if reward >= 0.7:  # Threshold for "success"
            stats.successes += 1
        else:
            stats.failures += 1

        # Store context
        if context is not None:
            stats.contexts_seen.append(context)
            # Keep only recent contexts (max 100)
            if len(stats.contexts_seen) > 100:
                stats.contexts_seen = stats.contexts_seen[-100:]

        logger.info(
            f"Updated {agent_id}: pulls={stats.pulls}, "
            f"mean_reward={stats.mean_reward:.3f}, "
            f"alpha={stats.alpha}, beta={stats.beta}"
        )

    def get_stats(self) -> Dict[str, any]:
        """Get bandit statistics"""
        return {
            "total_pulls": self.total_pulls,
            "num_arms": len(self.arms),
            "arm_stats": {arm_id: stats.to_dict() for arm_id, stats in self.arms.items()},
        }

    def get_best_arm(self) -> Optional[str]:
        """
        Get arm with highest mean reward.

        Returns:
            Arm ID with best performance
        """
        if not self.arms:
            return None

        best = max(self.arms.items(), key=lambda x: x[1].mean_reward)

        return best[0]

    def reset(self) -> None:
        """Reset all statistics"""
        for stats in self.arms.values():
            stats.successes = 0
            stats.failures = 0
            stats.total_reward = 0.0
            stats.pulls = 0
            stats.contexts_seen.clear()

        self.total_pulls = 0

        logger.info("Reset bandit statistics")


# Global bandit instance
_global_bandit: Optional[ContextualBandit] = None


def get_bandit(
    arms: Optional[List[str]] = None, exploration_bonus: float = 2.0
) -> ContextualBandit:
    """Get or create global bandit"""
    global _global_bandit
    if _global_bandit is None:
        _global_bandit = ContextualBandit(arms=arms, exploration_bonus=exploration_bonus)
    return _global_bandit


def reset_bandit() -> None:
    """Reset global bandit (for testing)"""
    global _global_bandit
    _global_bandit = None
