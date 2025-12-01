"""
Tests for Canary Testing System

Tests micro-task creation, canary execution, winner selection, and timeout handling.
"""

import pytest
import sys
from pathlib import Path
import asyncio

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from routing.canary import (
    CanaryTest,
    CanaryRunner,
    CanaryResult,
    get_canary_runner,
    reset_canary_runner,
)
from routing.winner_selection import (
    WinnerSelector,
    get_winner_selector,
    reset_winner_selector,
)


# Test Fixtures


@pytest.fixture
def canary_runner():
    """Fresh canary runner"""
    reset_canary_runner()
    return get_canary_runner(min_quality=0.6, default_timeout_ms=1000)


@pytest.fixture
def winner_selector():
    """Fresh winner selector"""
    reset_winner_selector()
    return get_winner_selector(min_quality_threshold=0.6)


# Micro-Task Creation Tests


class TestMicroTaskCreation:
    """Tests for micro-task extraction"""

    def test_create_from_examples(self, canary_runner):
        """Extract micro-task from NEED with examples"""
        need = {
            "task_type": "code_gen",
            "description": "Generate Python code",
            "examples": [
                {
                    "input": {"prompt": "write hello world"},
                    "output": {"code": "print('hello world')"},
                }
            ],
        }

        canary_test = canary_runner.create_micro_task(need)

        assert canary_test.micro_task == {"prompt": "write hello world"}
        assert canary_test.expected_output == {"code": "print('hello world')"}

    def test_create_from_test_cases(self, canary_runner):
        """Extract micro-task from NEED with test cases"""
        need = {
            "task_type": "data_analysis",
            "description": "Analyze data",
            "test_cases": [
                {"input": {"data": [1, 2, 3]}, "expected_output": {"mean": 2.0}}
            ],
        }

        canary_test = canary_runner.create_micro_task(need)

        assert canary_test.micro_task == {"data": [1, 2, 3]}
        assert canary_test.expected_output == {"mean": 2.0}

    def test_create_from_schema(self, canary_runner):
        """Create minimal micro-task from schema"""
        need = {
            "task_type": "translation",
            "description": "Translate text",
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "target_lang": {"type": "string"},
                },
                "required": ["text"],
            },
        }

        canary_test = canary_runner.create_micro_task(need)

        assert "input" in canary_test.micro_task
        assert "text" in canary_test.micro_task["input"]

    def test_timeout_from_need(self, canary_runner):
        """Timeout is extracted from NEED"""
        need = {
            "task_type": "test",
            "timeout_ms": 3000,
            "examples": [{"input": {}, "output": {}}],
        }

        canary_test = canary_runner.create_micro_task(need)

        assert canary_test.timeout_ms == 3000


# Canary Execution Tests


class TestCanaryExecution:
    """Tests for canary test execution"""

    @pytest.mark.asyncio
    async def test_run_canary_success(self, canary_runner):
        """Successful canary test execution"""
        agent_id = "test-agent"
        canary_test = CanaryTest(
            micro_task={"prompt": "test"},
            expected_output={"result": "success"},
            timeout_ms=1000,
        )

        # Mock handlers (simulated mode)
        canary_runner.send_task_handler = None  # Will use simulation
        canary_runner.receive_result_handler = None

        result = await canary_runner.run_canary(agent_id, canary_test)

        assert result.agent_id == agent_id
        assert result.latency_ms > 0
        assert 0.0 <= result.quality_score <= 1.0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_run_canary_with_custom_handler(self, canary_runner):
        """Canary test with custom result handler"""
        agent_id = "test-agent"
        canary_test = CanaryTest(
            micro_task={"prompt": "test"},
            expected_output={"result": "test"},
            timeout_ms=1000,
        )

        # Custom handler that returns expected output
        async def custom_handler(aid):
            await asyncio.sleep(0.05)
            return {"result": "test"}

        canary_runner.send_task_handler = None
        canary_runner.receive_result_handler = custom_handler

        result = await canary_runner.run_canary(agent_id, canary_test)

        assert result.passed
        assert result.quality_score == 1.0  # Exact match

    @pytest.mark.asyncio
    async def test_run_canary_partial_match(self, canary_runner):
        """Canary test with partial output match"""
        agent_id = "test-agent"
        canary_test = CanaryTest(
            micro_task={"prompt": "test"},
            expected_output={"a": 1, "b": 2, "c": 3},
            timeout_ms=1000,
        )

        # Handler returns partial match
        async def partial_handler(aid):
            await asyncio.sleep(0.05)
            return {"a": 1, "b": 2, "d": 4}  # c missing, d extra

        canary_runner.receive_result_handler = partial_handler

        result = await canary_runner.run_canary(agent_id, canary_test)

        # Should have some quality score (not 0, not 1)
        assert 0.0 < result.quality_score < 1.0

    @pytest.mark.asyncio
    async def test_multiple_canaries_concurrent(self, canary_runner):
        """Run canaries on multiple agents concurrently"""
        agent_ids = ["agent-1", "agent-2", "agent-3"]
        canary_test = CanaryTest(
            micro_task={"prompt": "test"}, expected_output=None, timeout_ms=1000
        )

        results = await canary_runner.run_canaries(agent_ids, canary_test)

        assert len(results) == 3
        result_agent_ids = {r.agent_id for r in results}
        assert result_agent_ids == set(agent_ids)


# Timeout Handling Tests


class TestTimeoutHandling:
    """Tests for timeout handling"""

    @pytest.mark.asyncio
    async def test_timeout_triggers(self, canary_runner):
        """Timeout is triggered for slow agents"""
        agent_id = "slow-agent"
        canary_test = CanaryTest(
            micro_task={"prompt": "test"},
            expected_output=None,
            timeout_ms=100,  # Very short timeout
        )

        # Handler that takes longer than timeout
        async def slow_handler(aid):
            await asyncio.sleep(0.5)  # 500ms > 100ms timeout
            return {"result": "too slow"}

        canary_runner.receive_result_handler = slow_handler

        result = await canary_runner.run_canary(agent_id, canary_test)

        assert result.error == "Timeout"
        assert result.quality_score == 0.0
        assert not result.passed

    @pytest.mark.asyncio
    async def test_timeout_fast_enough(self, canary_runner):
        """Agent completes before timeout"""
        agent_id = "fast-agent"
        canary_test = CanaryTest(
            micro_task={"prompt": "test"},
            expected_output=None,
            timeout_ms=1000,  # Generous timeout
        )

        # Fast handler
        async def fast_handler(aid):
            await asyncio.sleep(0.01)  # 10ms << 1000ms
            return {"result": "fast"}

        canary_runner.receive_result_handler = fast_handler

        result = await canary_runner.run_canary(agent_id, canary_test)

        assert result.error is None
        assert result.passed or result.quality_score > 0
        assert (
            result.latency_ms < 200
        )  # Should be reasonably fast (accounting for overhead)


# Winner Selection Tests


class TestWinnerSelection:
    """Tests for winner selection from canary results"""

    def test_select_best_quality(self, winner_selector):
        """Select agent with best quality score"""
        results = [
            CanaryResult("agent-1", 100.0, 0.9, True),
            CanaryResult("agent-2", 150.0, 0.7, True),
            CanaryResult("agent-3", 200.0, 0.5, False),  # Below threshold
        ]

        winner = winner_selector.select_winner(results)

        assert winner == "agent-1"  # Best quality (0.9)

    def test_latency_tiebreaker(self, winner_selector):
        """Latency breaks ties in quality"""
        results = [
            CanaryResult("agent-slow", 200.0, 0.9, True),
            CanaryResult("agent-fast", 50.0, 0.9, True),  # Same quality, faster
        ]

        winner = winner_selector.select_winner(results)

        assert winner == "agent-fast"  # Faster latency

    def test_minimum_threshold(self, winner_selector):
        """Agents below threshold are excluded"""
        results = [
            CanaryResult("agent-1", 100.0, 0.5, True),  # Below 0.6 threshold
            CanaryResult("agent-2", 150.0, 0.4, False),
        ]

        winner = winner_selector.select_winner(results)

        assert winner is None  # No one meets threshold

    def test_select_winner_with_score(self, winner_selector):
        """Select winner returns combined score"""
        results = [
            CanaryResult("agent-1", 100.0, 0.9, True),
            CanaryResult("agent-2", 150.0, 0.7, True),
        ]

        winner_tuple = winner_selector.select_winner_with_score(results)

        assert winner_tuple is not None
        agent_id, score = winner_tuple
        assert agent_id == "agent-1"
        assert 0.0 <= score <= 1.0

    def test_rank_all_agents(self, winner_selector):
        """Rank all qualified agents"""
        results = [
            CanaryResult("agent-1", 100.0, 0.9, True),
            CanaryResult("agent-2", 150.0, 0.7, True),
            CanaryResult("agent-3", 200.0, 0.8, True),
            CanaryResult("agent-4", 300.0, 0.5, False),  # Below threshold
        ]

        ranked = winner_selector.rank_all(results)

        # Should have 3 qualified agents (excluding agent-4)
        assert len(ranked) == 3

        # Should be sorted by score (descending)
        scores = [score for _, score in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_stats_calculation(self, winner_selector):
        """Get statistics from results"""
        results = [
            CanaryResult("agent-1", 100.0, 0.9, True),
            CanaryResult("agent-2", 150.0, 0.7, True),
            CanaryResult("agent-3", 200.0, 0.4, False),
        ]

        stats = winner_selector.get_stats(results)

        assert stats["total"] == 3
        assert stats["passed"] == 2
        assert stats["qualified"] == 2  # Above 0.6 threshold
        assert 0.0 <= stats["pass_rate"] <= 1.0


# Quality Scoring Tests


class TestQualityScoring:
    """Tests for output quality scoring"""

    def test_exact_match(self, canary_runner):
        """Exact match gives perfect score"""
        output = {"result": "success", "value": 42}
        expected = {"result": "success", "value": 42}

        score = canary_runner._score_correctness(output, expected)

        assert score == 1.0

    def test_type_mismatch(self, canary_runner):
        """Type mismatch gives low score"""
        output = "string result"
        expected = {"result": "dict"}

        score = canary_runner._score_correctness(output, expected)

        assert score < 0.5

    def test_partial_dict_match(self, canary_runner):
        """Partial dictionary match gives intermediate score"""
        output = {"a": 1, "b": 2}
        expected = {"a": 1, "c": 3}

        score = canary_runner._score_correctness(output, expected)

        # Should be between 0 and 1 (not perfect, not terrible)
        assert 0.0 < score < 1.0

    def test_validity_scoring(self, canary_runner):
        """Validity scoring when no expected output"""
        # Well-formed dict
        score1 = canary_runner._score_validity({"status": "success"})
        assert score1 > 0.5

        # None
        score2 = canary_runner._score_validity(None)
        assert score2 == 0.0

        # Simple types
        score3 = canary_runner._score_validity("result")
        assert score3 > 0.0


# Integration Tests


class TestCanaryIntegration:
    """Integration tests for complete canary workflow"""

    @pytest.mark.asyncio
    async def test_complete_workflow(self, canary_runner, winner_selector):
        """Complete canary test workflow"""
        # Step 1: Create micro-task from NEED
        need = {
            "task_type": "test",
            "examples": [{"input": {"x": 1}, "output": {"y": 2}}],
        }

        canary_test = canary_runner.create_micro_task(need)

        # Step 2: Run canaries on multiple agents
        agent_ids = ["agent-a", "agent-b", "agent-c"]

        # Mock different agent behaviors
        agent_outputs = {
            "agent-a": {"y": 2},  # Perfect match
            "agent-b": {"y": 2.1},  # Close match
            "agent-c": {"z": 3},  # Wrong output
        }

        async def mock_handler(aid):
            await asyncio.sleep(0.01)
            return agent_outputs.get(aid, {})

        canary_runner.receive_result_handler = mock_handler

        results = await canary_runner.run_canaries(agent_ids, canary_test)

        # Step 3: Select winner
        winner = winner_selector.select_winner(results)

        assert winner == "agent-a"  # Should select perfect match


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
