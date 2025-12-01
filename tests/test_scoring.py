"""
Tests for Agent Scoring System

Tests multi-factor scoring, diversity bonuses, top-K selection, and tie-breaking.
"""

import pytest
import sys
from pathlib import Path
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from routing.manifests import AgentManifest
from routing.scoring import AgentScorer, ScoredAgent, get_scorer, reset_scorer
from routing.domain_fit import DomainFitCalculator, reset_domain_fit_calculator
from routing.recency import RecencyWeighter, reset_recency_weighter


# Test Fixtures


@pytest.fixture
def sample_agents():
    """Sample agent manifests for testing"""
    return [
        AgentManifest(
            agent_id="agent-high-rep",
            capabilities=["code_gen"],
            io_schema={},
            tags=["python", "ml"],
            success_rate=0.95,
            price_per_task=20.0,
            avg_latency_ms=500.0,
            zone="us-west-2",
        ),
        AgentManifest(
            agent_id="agent-cheap",
            capabilities=["code_gen"],
            io_schema={},
            tags=["python"],
            success_rate=0.80,
            price_per_task=5.0,
            avg_latency_ms=800.0,
            zone="us-west-2",
        ),
        AgentManifest(
            agent_id="agent-fast",
            capabilities=["code_gen"],
            io_schema={},
            tags=["python", "ml"],
            success_rate=0.85,
            price_per_task=15.0,
            avg_latency_ms=200.0,
            zone="us-east-1",
        ),
        AgentManifest(
            agent_id="agent-diverse",
            capabilities=["code_gen"],
            io_schema={},
            tags=["python"],
            success_rate=0.90,
            price_per_task=12.0,
            avg_latency_ms=600.0,
            zone="eu-west-1",  # Different zone
        ),
    ]


@pytest.fixture
def domain_fit_calc():
    """Fresh domain fit calculator"""
    reset_domain_fit_calculator()
    from routing.domain_fit import get_domain_fit_calculator

    return get_domain_fit_calculator()


@pytest.fixture
def recency_weighter():
    """Fresh recency weighter"""
    reset_recency_weighter()
    from routing.recency import get_recency_weighter

    return get_recency_weighter()


@pytest.fixture
def scorer(domain_fit_calc, recency_weighter):
    """Fresh agent scorer with default weights"""
    return AgentScorer(
        domain_fit_calculator=domain_fit_calc, recency_weighter=recency_weighter
    )


# Domain Fit Tests


class TestDomainFit:
    """Tests for domain fit calculation"""

    def test_tag_similarity_perfect_match(self, domain_fit_calc):
        """Perfect tag match gives 1.0"""
        tags1 = ["python", "ml", "sklearn"]
        tags2 = ["python", "ml", "sklearn"]

        similarity = domain_fit_calc.tag_similarity(tags1, tags2)

        assert similarity == 1.0

    def test_tag_similarity_no_match(self, domain_fit_calc):
        """No tag overlap gives 0.0"""
        tags1 = ["python", "ml"]
        tags2 = ["javascript", "web"]

        similarity = domain_fit_calc.tag_similarity(tags1, tags2)

        assert similarity == 0.0

    def test_tag_similarity_partial_match(self, domain_fit_calc):
        """Partial overlap gives Jaccard similarity"""
        tags1 = ["python", "ml"]
        tags2 = ["python", "web"]

        similarity = domain_fit_calc.tag_similarity(tags1, tags2)

        # Jaccard = |{python}| / |{python, ml, web}| = 1/3
        assert abs(similarity - 1 / 3) < 0.01

    def test_capability_overlap_full(self, domain_fit_calc):
        """Full capability overlap gives 1.0"""
        required = ["code_gen", "refactor"]
        provided = ["code_gen", "refactor", "test_gen"]

        overlap = domain_fit_calc.capability_overlap(required, provided)

        assert overlap == 1.0

    def test_capability_overlap_partial(self, domain_fit_calc):
        """Partial capability overlap"""
        required = ["code_gen", "refactor", "test_gen"]
        provided = ["code_gen", "refactor"]

        overlap = domain_fit_calc.capability_overlap(required, provided)

        # 2 out of 3 required
        assert abs(overlap - 2 / 3) < 0.01

    def test_capability_overlap_none(self, domain_fit_calc):
        """No capability overlap gives 0.0"""
        required = ["code_gen"]
        provided = ["web_scraping"]

        overlap = domain_fit_calc.capability_overlap(required, provided)

        assert overlap == 0.0

    def test_performance_tracking(self, domain_fit_calc):
        """Can record and retrieve performance"""
        domain = "python"
        agent_id = "test-agent"

        # Record some successes and failures
        domain_fit_calc.record_performance(domain, agent_id, success=True)
        domain_fit_calc.record_performance(domain, agent_id, success=True)
        domain_fit_calc.record_performance(domain, agent_id, success=False)

        score = domain_fit_calc.get_performance_score(domain, agent_id)

        # Should be between 0.5 and 1.0 (more successes than failures)
        assert 0.5 < score <= 1.0


# Recency Tests


class TestRecency:
    """Tests for recency weighting"""

    def test_recent_activity_high_weight(self, recency_weighter):
        """Recent activity gets high weight"""
        agent_id = "test-agent"
        current_time = time.time()

        # Activity 1 hour ago
        recency_weighter.record_activity(agent_id, current_time - 3600)

        weight = recency_weighter.get_recency_weight(agent_id, current_time)

        # Should be close to max_boost (1.5)
        assert weight > 1.0

    def test_old_activity_low_weight(self, recency_weighter):
        """Old activity gets low weight"""
        agent_id = "test-agent"
        current_time = time.time()

        # Activity 7 days ago
        recency_weighter.record_activity(agent_id, current_time - 7 * 24 * 3600)

        weight = recency_weighter.get_recency_weight(agent_id, current_time)

        # Should be close to min_weight (0.5)
        assert weight < 1.0

    def test_no_activity_minimum_weight(self, recency_weighter):
        """No activity gives minimum weight"""
        agent_id = "unknown-agent"

        weight = recency_weighter.get_recency_weight(agent_id)

        # Should be min_weight (0.5)
        assert abs(weight - 0.5) < 0.01

    def test_recency_score_normalized(self, recency_weighter):
        """Recency score is 0.0-1.0"""
        agent_id = "test-agent"
        recency_weighter.record_activity(agent_id)

        score = recency_weighter.get_recency_score(agent_id)

        assert 0.0 <= score <= 1.0

    def test_cleanup_old_entries(self, recency_weighter):
        """Can cleanup old activity entries"""
        current_time = time.time()

        # Add some old and new entries
        recency_weighter.record_activity("old-agent", current_time - 200 * 3600)
        recency_weighter.record_activity("new-agent", current_time - 1 * 3600)

        # Cleanup entries older than 100 hours
        removed = recency_weighter.cleanup_old_entries(
            max_age_hours=100.0, current_time=current_time
        )

        assert removed == 1
        assert "new-agent" in recency_weighter.last_activity
        assert "old-agent" not in recency_weighter.last_activity


# Scoring Tests


class TestScoreCalculation:
    """Tests for agent scoring"""

    def test_score_agent_basic(self, scorer, sample_agents):
        """Can score an agent"""
        agent = sample_agents[0]
        need = {
            "tags": ["python", "ml"],
            "capabilities": ["code_gen"],
            "max_price": 50.0,
            "max_latency_ms": 1000.0,
        }

        scored = scorer.score_agent(agent, need)

        assert isinstance(scored, ScoredAgent)
        assert 0.0 <= scored.total_score <= 1.0
        assert "reputation" in scored.score_breakdown
        assert "price" in scored.score_breakdown
        assert "latency" in scored.score_breakdown

    def test_high_reputation_scores_better(self, scorer):
        """Higher reputation gets better score"""
        high_rep = AgentManifest(
            agent_id="high",
            capabilities=["test"],
            io_schema={},
            tags=["python"],
            success_rate=0.95,
            price_per_task=10.0,
            avg_latency_ms=500.0,
        )

        low_rep = AgentManifest(
            agent_id="low",
            capabilities=["test"],
            io_schema={},
            tags=["python"],
            success_rate=0.70,
            price_per_task=10.0,
            avg_latency_ms=500.0,
        )

        need = {"tags": ["python"], "capabilities": ["test"]}

        scored_high = scorer.score_agent(high_rep, need)
        scored_low = scorer.score_agent(low_rep, need)

        assert scored_high.total_score > scored_low.total_score

    def test_cheaper_scores_better(self, scorer):
        """Cheaper agent gets better price score"""
        cheap = AgentManifest(
            agent_id="cheap",
            capabilities=["test"],
            io_schema={},
            tags=["python"],
            success_rate=0.90,
            price_per_task=5.0,
            avg_latency_ms=500.0,
        )

        expensive = AgentManifest(
            agent_id="expensive",
            capabilities=["test"],
            io_schema={},
            tags=["python"],
            success_rate=0.90,
            price_per_task=50.0,
            avg_latency_ms=500.0,
        )

        need = {"tags": ["python"], "capabilities": ["test"], "max_price": 100.0}

        scored_cheap = scorer.score_agent(cheap, need)
        scored_expensive = scorer.score_agent(expensive, need)

        assert (
            scored_cheap.score_breakdown["price"]
            > scored_expensive.score_breakdown["price"]
        )

    def test_faster_scores_better(self, scorer):
        """Faster agent gets better latency score"""
        fast = AgentManifest(
            agent_id="fast",
            capabilities=["test"],
            io_schema={},
            tags=["python"],
            success_rate=0.90,
            price_per_task=10.0,
            avg_latency_ms=200.0,
        )

        slow = AgentManifest(
            agent_id="slow",
            capabilities=["test"],
            io_schema={},
            tags=["python"],
            success_rate=0.90,
            price_per_task=10.0,
            avg_latency_ms=2000.0,
        )

        need = {"tags": ["python"], "capabilities": ["test"], "max_latency_ms": 5000.0}

        scored_fast = scorer.score_agent(fast, need)
        scored_slow = scorer.score_agent(slow, need)

        assert (
            scored_fast.score_breakdown["latency"]
            > scored_slow.score_breakdown["latency"]
        )

    def test_custom_weights(self, domain_fit_calc, recency_weighter):
        """Can use custom scoring weights"""
        # Heavy weight on price
        custom_weights = {
            "reputation": 0.1,
            "price": 0.6,  # Heavily weighted
            "latency": 0.1,
            "domain_fit": 0.1,
            "stake": 0.05,
            "recency": 0.05,
        }

        custom_scorer = AgentScorer(
            weights=custom_weights,
            domain_fit_calculator=domain_fit_calc,
            recency_weighter=recency_weighter,
        )

        assert abs(custom_scorer.weights["price"] - 0.6) < 0.01


class TestDiversityBonus:
    """Tests for diversity adjustments"""

    def test_adjust_for_diversity(self, scorer, sample_agents):
        """Diversity bonus boosts under-represented zones"""
        need = {"tags": ["python"], "capabilities": ["code_gen"]}

        scored = scorer.score_agents(sample_agents, need)
        adjusted = scorer.adjust_for_diversity(scored, diversity_bonus=0.2)

        # Find the EU agent (only one in that zone)
        eu_agent_original = next(s for s in scored if s.manifest.zone == "eu-west-1")
        eu_agent_adjusted = next(s for s in adjusted if s.manifest.zone == "eu-west-1")

        # EU agent should get bigger boost (it's alone in its zone)
        assert eu_agent_adjusted.total_score > eu_agent_original.total_score

    def test_no_diversity_bonus(self, scorer, sample_agents):
        """Zero diversity bonus doesn't change scores"""
        need = {"tags": ["python"], "capabilities": ["code_gen"]}

        scored = scorer.score_agents(sample_agents, need)
        adjusted = scorer.adjust_for_diversity(scored, diversity_bonus=0.0)

        for original, adj in zip(scored, adjusted):
            assert abs(original.total_score - adj.total_score) < 0.001


class TestTopKSelection:
    """Tests for top-K selection"""

    def test_select_top_k(self, scorer, sample_agents):
        """Can select top K agents"""
        need = {"tags": ["python"], "capabilities": ["code_gen"]}

        scored = scorer.score_agents(sample_agents, need)
        top_2 = scorer.select_top_k(scored, k=2)

        assert len(top_2) == 2
        # Should be sorted by score (descending)
        assert top_2[0].total_score >= top_2[1].total_score

    def test_select_more_than_available(self, scorer, sample_agents):
        """Requesting more than available returns all"""
        need = {"tags": ["python"], "capabilities": ["code_gen"]}

        scored = scorer.score_agents(sample_agents, need)
        top_100 = scorer.select_top_k(scored, k=100)

        assert len(top_100) == len(sample_agents)

    def test_select_zero(self, scorer, sample_agents):
        """Selecting 0 returns empty list"""
        need = {"tags": ["python"], "capabilities": ["code_gen"]}

        scored = scorer.score_agents(sample_agents, need)
        top_0 = scorer.select_top_k(scored, k=0)

        assert len(top_0) == 0


class TestTieBreaking:
    """Tests for tie-breaking in selection"""

    def test_tie_breaking_by_agent_id(self, scorer):
        """Ties broken by agent_id (lexicographic)"""
        # Create two agents with identical scores
        agent_a = AgentManifest(
            agent_id="agent-a",
            capabilities=["test"],
            io_schema={},
            tags=["python"],
            success_rate=0.90,
            price_per_task=10.0,
            avg_latency_ms=500.0,
        )

        agent_z = AgentManifest(
            agent_id="agent-z",
            capabilities=["test"],
            io_schema={},
            tags=["python"],
            success_rate=0.90,
            price_per_task=10.0,
            avg_latency_ms=500.0,
        )

        need = {"tags": ["python"], "capabilities": ["test"]}

        scored = scorer.score_agents([agent_z, agent_a], need)
        top_1 = scorer.select_top_k(scored, k=1)

        # agent-a should come first (lexicographically)
        assert top_1[0].manifest.agent_id == "agent-a"


class TestCompleteScoring:
    """Tests for complete scoring pipeline"""

    def test_score_and_select_pipeline(self, scorer, sample_agents):
        """Complete pipeline works end-to-end"""
        need = {
            "tags": ["python", "ml"],
            "capabilities": ["code_gen"],
            "max_price": 50.0,
            "max_latency_ms": 1000.0,
        }

        top_2 = scorer.score_and_select(
            manifests=sample_agents, need=need, k=2, diversity_bonus=0.1
        )

        assert len(top_2) == 2
        assert top_2[0].total_score >= top_2[1].total_score

        # All should have breakdown
        for scored in top_2:
            assert "reputation" in scored.score_breakdown
            assert "price" in scored.score_breakdown

    def test_empty_input(self, scorer):
        """Empty input returns empty output"""
        need = {"tags": ["python"]}

        result = scorer.score_and_select([], need, k=5)

        assert len(result) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
