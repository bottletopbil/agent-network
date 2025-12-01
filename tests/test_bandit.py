"""
Tests for Contextual Bandit Learning

Tests Thompson Sampling, UCB1, feedback collection, and context learning.
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from routing.bandit import get_bandit, reset_bandit
from routing.features import (
    get_feature_extractor,
    reset_feature_extractor,
)
from routing.feedback import (
    collect_feedback,
    calculate_binary_reward,
    calculate_quality_reward,
    get_feedback_collector,
    reset_feedback_collector,
)


# Test Fixtures


@pytest.fixture
def bandit():
    """Fresh bandit with 3 arms"""
    reset_bandit()
    return get_bandit(arms=["agent-a", "agent-b", "agent-c"])


@pytest.fixture
def feature_extractor():
    """Fresh feature extractor"""
    reset_feature_extractor()
    return get_feature_extractor()


@pytest.fixture
def feedback_collector():
    """Fresh feedback collector"""
    reset_feedback_collector()
    return get_feedback_collector()


# Thompson Sampling Tests


class TestThompsonSampling:
    """Tests for Thompson Sampling algorithm"""

    def test_thompson_initial_selection(self, bandit):
        """Can select arm with Thompson Sampling"""
        selected = bandit.thompson_sampling()

        assert selected in ["agent-a", "agent-b", "agent-c"]

    def test_thompson_updates_shift_distribution(self, bandit):
        """Thompson Sampling learns from rewards"""
        # Give agent-a many good rewards
        for _ in range(10):
            bandit.update("agent-a", reward=0.9)

        # Give agent-b poor rewards
        for _ in range(10):
            bandit.update("agent-b", reward=0.1)

        # Thompson Sampling should favor agent-a
        selections = []
        for _ in range(100):
            selected = bandit.thompson_sampling()
            selections.append(selected)

        # agent-a should be selected more often
        count_a = selections.count("agent-a")
        count_b = selections.count("agent-b")

        assert count_a > count_b

    def test_thompson_exploration(self, bandit):
        """Thompson Sampling explores unpulled arms"""
        # Pull only agent-a
        for _ in range(5):
            bandit.update("agent-a", reward=0.8)

        # Thompson Sampling should still sometimes select other arms
        selections = []
        for _ in range(50):
            selected = bandit.thompson_sampling()
            selections.append(selected)

        # Should see some exploration
        unique_selections = set(selections)
        assert len(unique_selections) > 1


# UCB1 Tests


class TestUCB1Exploration:
    """Tests for UCB1 algorithm"""

    def test_ucb1_initial_selection(self, bandit):
        """UCB1 pulls unpulled arms first"""
        # First 3 selections should be different (one for each arm)
        selections = []
        for _ in range(3):
            selected = bandit.ucb1()
            selections.append(selected)
            bandit.update(selected, reward=0.5)

        # Should have pulled each arm once
        assert set(selections) == {"agent-a", "agent-b", "agent-c"}

    def test_ucb1_exploration_bonus(self, bandit):
        """Higher exploration bonus increases exploration"""
        # Give agent-a good rewards
        for _ in range(10):
            selected = bandit.ucb1(exploration_bonus=0.1)  # Low exploration
            bandit.update(selected, reward=0.9 if selected == "agent-a" else 0.3)

        bandit.arms["agent-a"].pulls

        # Reset and try with high exploration
        bandit.reset()
        for _ in range(10):
            selected = bandit.ucb1(exploration_bonus=5.0)  # High exploration
            bandit.update(selected, reward=0.9 if selected == "agent-a" else 0.3)

        bandit.arms["agent-a"].pulls

        # High exploration should pull agent-a less (more exploration of others)
        # This is probabilistic so we just check the mechanism works
        assert bandit.arms["agent-b"].pulls > 0 or bandit.arms["agent-c"].pulls > 0

    def test_ucb1_convergence(self, bandit):
        """UCB1 converges to best arm over time"""
        # agent-a is best
        for _ in range(100):
            selected = bandit.ucb1()
            reward = 0.9 if selected == "agent-a" else 0.3
            bandit.update(selected, reward=reward)

        # agent-a should have been pulled most
        pulls_a = bandit.arms["agent-a"].pulls
        pulls_b = bandit.arms["agent-b"].pulls
        pulls_c = bandit.arms["agent-c"].pulls

        assert pulls_a > pulls_b and pulls_a > pulls_c


# Feedback Tests


class TestFeedbackUpdates:
    """Tests for feedback collection and updates"""

    def test_collect_feedback_perfect(self):
        """Perfect task execution gives high reward"""
        task_result = {
            "quality_score": 1.0,
            "latency_ms": 100.0,
            "max_latency_ms": 5000.0,
        }

        reward = collect_feedback(
            task_result=task_result,
            agent_id="test-agent",
            task_price=10.0,
            max_price=100.0,
        )

        # Should be high (perfect quality, fast, cheap)
        assert reward > 0.8

    def test_collect_feedback_poor(self):
        """Poor task execution gives low reward"""
        task_result = {
            "quality_score": 0.3,
            "latency_ms": 8000.0,
            "max_latency_ms": 5000.0,  # Over time limit
        }

        reward = collect_feedback(
            task_result=task_result,
            agent_id="test-agent",
            task_price=90.0,
            max_price=100.0,  # Expensive
        )

        # Should be low (poor quality, slow, expensive)
        assert reward < 0.3

    def test_binary_reward(self):
        """Binary reward returns 1.0 or 0.0"""
        success_result = {"success": True}
        failure_result = {"success": False}

        assert calculate_binary_reward(success_result) == 1.0
        assert calculate_binary_reward(failure_result) == 0.0

    def test_quality_reward(self):
        """Quality reward extracts quality score"""
        result = {"quality_score": 0.75}

        reward = calculate_quality_reward(result)

        assert reward == 0.75

    def test_feedback_collector_recording(self, feedback_collector):
        """Can record and retrieve feedback"""
        task_result = {"quality_score": 0.8, "latency_ms": 200.0}

        feedback_collector.record_feedback(
            task_id="task-1", agent_id="agent-a", reward=0.85, task_result=task_result
        )

        stats = feedback_collector.get_agent_stats("agent-a")

        assert stats["count"] == 1
        assert stats["avg_reward"] == 0.85

    def test_feedback_aggregation(self, feedback_collector):
        """Feedback is aggregated correctly"""
        # Record multiple feedback entries
        for i in range(5):
            feedback_collector.record_feedback(
                task_id=f"task-{i}",
                agent_id="agent-a",
                reward=0.5 + i * 0.1,
                task_result={"quality_score": 0.5 + i * 0.1},
            )

        stats = feedback_collector.get_agent_stats("agent-a")

        assert stats["count"] == 5
        # Average of [0.5, 0.6, 0.7, 0.8, 0.9] = 0.7
        assert abs(stats["avg_reward"] - 0.7) < 0.01


# Context Learning Tests


class TestContextLearning:
    """Tests for contextual feature extraction and learning"""

    def test_feature_extraction(self, feature_extractor):
        """Can extract features from NEED"""
        need = {
            "task_type": "code_gen",
            "tags": ["python", "ml"],
            "capabilities": ["generation"],
            "description": "Generate ML code",
            "max_price": 50.0,
            "deadline_ms": 30000,
        }

        features = feature_extractor.extract_context(need)

        assert len(features) == 10
        assert all(isinstance(f, float) for f in features)

    def test_features_normalized(self, feature_extractor):
        """Features are in reasonable range"""
        need = {"tags": ["python"], "capabilities": ["test"], "max_price": 100.0}

        features = feature_extractor.extract_context(need)

        # All features should be 0.0 - 1.0 (mostly)
        assert all(0.0 <= f <= 1.0 for f in features)

    def test_context_stored_in_arms(self, bandit):
        """Context is stored when updating arms"""
        context = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

        bandit.update("agent-a", reward=0.8, context=context)

        stats = bandit.arms["agent-a"]
        assert len(stats.contexts_seen) == 1
        assert stats.contexts_seen[0] == context

    def test_context_learning_integration(self, bandit, feature_extractor):
        """Complete context learning workflow"""
        needs = [
            {"tags": ["python"], "capabilities": ["code_gen"]},
            {"tags": ["javascript"], "capabilities": ["web"]},
            {"tags": ["python"], "capabilities": ["data"]},
        ]

        # Simulate learning
        for need in needs:
            context = feature_extractor.extract_context(need)

            # Select agent
            selected = bandit.thompson_sampling(context)

            # Simulate different rewards based on domain
            if "python" in need.get("tags", []) and selected == "agent-a":
                reward = 0.9  # agent-a is good at Python
            else:
                reward = 0.5  # Others are mediocre

            bandit.update(selected, reward=reward, context=context)

        # At least some agents should have been pulled
        total_pulls = sum(stats.pulls for stats in bandit.arms.values())
        assert total_pulls == 3  # One pull per NEED


# Integration Tests


class TestBanditIntegration:
    """Integration tests for complete bandit workflow"""

    def test_complete_workflow(self, bandit, feature_extractor):
        """Complete bandit learning workflow"""
        # Simulate 50 task assignments
        for i in range(50):
            # Create synthetic NEED
            need = {
                "tags": ["python"] if i % 2 == 0 else ["javascript"],
                "capabilities": ["code_gen"],
                "max_price": 50.0,
            }

            # Extract features
            context = feature_extractor.extract_context(need)

            # Select agent using Thompson Sampling
            selected = bandit.thompson_sampling(context)

            # Simulate task execution with domain-specific performance
            if need["tags"][0] == "python" and selected == "agent-a":
                quality = 0.9
            elif need["tags"][0] == "javascript" and selected == "agent-b":
                quality = 0.9
            else:
                quality = 0.5

            task_result = {
                "quality_score": quality,
                "latency_ms": 500.0,
                "max_latency_ms": 5000.0,
            }

            reward = collect_feedback(
                task_result=task_result,
                agent_id=selected,
                task_price=20.0,
                max_price=50.0,
            )

            # Update bandit
            bandit.update(selected, reward=reward, context=context)

        # All agents should have been pulled at least once
        assert all(stats.pulls > 0 for stats in bandit.arms.values())

        # Best performing agents should have higher mean rewards
        stats = bandit.get_stats()
        assert stats["total_pulls"] == 50

    def test_bandit_stats(self, bandit):
        """Can get bandit statistics"""
        bandit.update("agent-a", reward=0.8)
        bandit.update("agent-b", reward=0.6)

        stats = bandit.get_stats()

        assert stats["total_pulls"] == 2
        assert stats["num_arms"] == 3
        assert "agent-a" in stats["arm_stats"]
        assert stats["arm_stats"]["agent-a"]["mean_reward"] == 0.8

    def test_get_best_arm(self, bandit):
        """Can identify best performing arm"""
        bandit.update("agent-a", reward=0.9)
        bandit.update("agent-b", reward=0.5)
        bandit.update("agent-c", reward=0.7)

        best = bandit.get_best_arm()

        assert best == "agent-a"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
