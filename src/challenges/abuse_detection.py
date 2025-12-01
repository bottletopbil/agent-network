"""
Anti-Abuse Detection: Detect and prevent frivolous challenge spam.

Tracks challenge patterns and applies rate limiting and reputation penalties
to discourage bad actors.
"""

import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ChallengerStats:
    """Statistics for a challenger"""

    challenger_id: str
    total_challenges: int = 0
    upheld_challenges: int = 0
    rejected_challenges: int = 0
    withdrawn_challenges: int = 0
    last_challenge_ns: int = 0
    challenges_in_window: List[int] = field(default_factory=list)  # Timestamps

    def get_success_rate(self) -> float:
        """Calculate percentage of challenges upheld"""
        total = self.upheld_challenges + self.rejected_challenges
        if total == 0:
            return 0.0
        return (self.upheld_challenges / total) * 100

    def get_rejection_rate(self) -> float:
        """Calculate percentage of challenges rejected"""
        total = self.upheld_challenges + self.rejected_challenges
        if total == 0:
            return 0.0
        return (self.rejected_challenges / total) * 100


class AbuseDetector:
    """
    Detect abusive challenge patterns and apply countermeasures.

    Detection mechanisms:
    - Rate limiting (max challenges per time window)
    - Success rate tracking (penalize low success rates)
    - Spam pattern detection (rapid-fire challenges)
    """

    # Configuration
    MAX_CHALLENGES_PER_HOUR = 10
    MAX_CHALLENGES_PER_DAY = 50
    MIN_SUCCESS_RATE_THRESHOLD = 20.0  # 20% minimum success rate
    SPAM_DETECTION_WINDOW_SECONDS = 60  # 1 minute
    SPAM_THRESHOLD_COUNT = 5  # 5 challenges in 1 minute = spam

    def __init__(self):
        self.stats: Dict[str, ChallengerStats] = {}

    def record_challenge(self, challenger_id: str) -> None:
        """Record a new challenge submission"""
        if challenger_id not in self.stats:
            self.stats[challenger_id] = ChallengerStats(challenger_id=challenger_id)

        stats = self.stats[challenger_id]
        stats.total_challenges += 1
        current_time_ns = time.time_ns()
        stats.last_challenge_ns = current_time_ns
        stats.challenges_in_window.append(current_time_ns)

        # Clean old timestamps (keep only last hour)
        one_hour_ago = current_time_ns - (3600 * 1e9)
        stats.challenges_in_window = [
            ts for ts in stats.challenges_in_window if ts > one_hour_ago
        ]

    def record_outcome(self, challenger_id: str, outcome: str) -> None:
        """Record the outcome of a challenge"""
        if challenger_id not in self.stats:
            return

        stats = self.stats[challenger_id]

        if outcome == "UPHELD":
            stats.upheld_challenges += 1
        elif outcome == "REJECTED":
            stats.rejected_challenges += 1
        elif outcome == "WITHDRAWN":
            stats.withdrawn_challenges += 1

    def check_rate_limit(self, challenger_id: str) -> tuple[bool, Optional[str]]:
        """
        Check if challenger has exceeded rate limits.

        Returns:
            (is_allowed, error_message)
        """
        if challenger_id not in self.stats:
            return True, None

        stats = self.stats[challenger_id]
        current_time_ns = time.time_ns()

        # Check hourly limit
        one_hour_ago = current_time_ns - (3600 * 1e9)
        challenges_last_hour = sum(
            1 for ts in stats.challenges_in_window if ts > one_hour_ago
        )

        if challenges_last_hour >= self.MAX_CHALLENGES_PER_HOUR:
            return (
                False,
                f"Rate limit exceeded: {challenges_last_hour} challenges in last hour (max: {self.MAX_CHALLENGES_PER_HOUR})",
            )

        # Check daily limit
        one_day_ago = current_time_ns - (24 * 3600 * 1e9)
        challenges_last_day = sum(
            1 for ts in stats.challenges_in_window if ts > one_day_ago
        )

        if challenges_last_day >= self.MAX_CHALLENGES_PER_DAY:
            return (
                False,
                f"Rate limit exceeded: {challenges_last_day} challenges in last 24h (max: {self.MAX_CHALLENGES_PER_DAY})",
            )

        return True, None

    def check_spam_pattern(self, challenger_id: str) -> tuple[bool, Optional[str]]:
        """
        Detect spam patterns (rapid-fire challenges).

        Returns:
            (is_spam, warning_message)
        """
        if challenger_id not in self.stats:
            return False, None

        stats = self.stats[challenger_id]
        current_time_ns = time.time_ns()

        # Check for rapid-fire pattern
        window_start = current_time_ns - (self.SPAM_DETECTION_WINDOW_SECONDS * 1e9)
        recent_challenges = sum(
            1 for ts in stats.challenges_in_window if ts > window_start
        )

        if recent_challenges >= self.SPAM_THRESHOLD_COUNT:
            return (
                True,
                f"Spam detected: {recent_challenges} challenges in {self.SPAM_DETECTION_WINDOW_SECONDS}s",
            )

        return False, None

    def calculate_reputation_impact(self, challenger_id: str) -> float:
        """
        Calculate reputation score based on challenge history.

        Returns:
            Reputation score (0.0 - 1.0), where 1.0 is perfect
        """
        if challenger_id not in self.stats:
            return 0.5  # Neutral for new challengers

        stats = self.stats[challenger_id]

        # If no challenges yet completed, return neutral
        total_completed = stats.upheld_challenges + stats.rejected_challenges
        if total_completed == 0:
            return 0.5

        # Calculate success rate
        success_rate = stats.get_success_rate()

        # Convert to 0-1 scale (0% = 0.0, 100% = 1.0)
        base_score = success_rate / 100

        # Penalty for too many withdrawals
        withdrawal_rate = 0
        if stats.total_challenges > 0:
            withdrawal_rate = stats.withdrawn_challenges / stats.total_challenges

        # Reduce score if too many withdrawals (> 20%)
        if withdrawal_rate > 0.2:
            base_score *= 1 - (withdrawal_rate - 0.2)

        return max(0.0, min(1.0, base_score))

    def is_low_quality_challenger(
        self, challenger_id: str, min_challenges: int = 5
    ) -> bool:
        """
        Check if challenger has consistently low success rate.

        Args:
            challenger_id: Challenger to check
            min_challenges: Minimum challenges before applying threshold

        Returns:
            True if challenger has low success rate
        """
        if challenger_id not in self.stats:
            return False

        stats = self.stats[challenger_id]
        total_completed = stats.upheld_challenges + stats.rejected_challenges

        # Need minimum challenges to make determination
        if total_completed < min_challenges:
            return False

        success_rate = stats.get_success_rate()
        return success_rate < self.MIN_SUCCESS_RATE_THRESHOLD

    def get_stats(self, challenger_id: str) -> Optional[ChallengerStats]:
        """Get statistics for a challenger"""
        return self.stats.get(challenger_id)

    def get_all_stats(self) -> Dict[str, ChallengerStats]:
        """Get all challenger statistics"""
        return dict(self.stats)
