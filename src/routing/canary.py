"""
Canary Testing System

Tests agents with small micro-tasks before assigning full work.
Validates agent capability and measures actual performance.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Callable
import asyncio
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class CanaryTest:
    """
    Micro-task for testing agent capability.

    A small, representative task extracted from the full NEED.
    """

    micro_task: Dict[str, Any]  # Simplified task payload
    expected_output: Optional[Dict[str, Any]] = None  # Expected result (if known)
    timeout_ms: int = 5000  # Maximum wait time

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "micro_task": self.micro_task,
            "expected_output": self.expected_output,
            "timeout_ms": self.timeout_ms,
        }


@dataclass
class CanaryResult:
    """
    Result from running a canary test.

    Captures performance metrics and quality assessment.
    """

    agent_id: str
    latency_ms: float
    quality_score: float  # 0.0 - 1.0
    passed: bool
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "agent_id": self.agent_id,
            "latency_ms": self.latency_ms,
            "quality_score": self.quality_score,
            "passed": self.passed,
            "output": self.output,
            "error": self.error,
        }


class CanaryRunner:
    """
    Executes canary tests on agents.

    Sends micro-tasks, collects results, and scores quality.
    """

    def __init__(self, min_quality: float = 0.6, default_timeout_ms: int = 5000):
        """
        Initialize canary runner.

        Args:
            min_quality: Minimum quality score to pass (0.0 - 1.0)
            default_timeout_ms: Default timeout for tests
        """
        self.min_quality = min_quality
        self.default_timeout_ms = default_timeout_ms

        # Agent communication handlers (to be set by caller)
        self.send_task_handler: Optional[Callable] = None
        self.receive_result_handler: Optional[Callable] = None

    def create_micro_task(self, need: Dict[str, Any]) -> CanaryTest:
        """
        Extract a micro-task from a full NEED.

        Strategy:
        - If NEED has examples, use first example
        - If NEED has test cases, use first test case
        - Otherwise, create minimal version of NEED

        Args:
            need: Full task NEED payload

        Returns:
            Canary test with micro-task
        """
        # Check for pre-defined examples
        if "examples" in need and need["examples"]:
            example = need["examples"][0]
            return CanaryTest(
                micro_task=example.get("input", {}),
                expected_output=example.get("output"),
                timeout_ms=need.get("timeout_ms", self.default_timeout_ms),
            )

        # Check for test cases
        if "test_cases" in need and need["test_cases"]:
            test = need["test_cases"][0]
            return CanaryTest(
                micro_task=test.get("input", {}),
                expected_output=test.get("expected_output"),
                timeout_ms=need.get("timeout_ms", self.default_timeout_ms),
            )

        # Create minimal micro-task
        micro_task = {
            "task_type": need.get("task_type", "unknown"),
            "description": f"Micro-test: {need.get('description', '')[:100]}",
            "input": self._extract_minimal_input(need),
        }

        return CanaryTest(
            micro_task=micro_task,
            expected_output=None,
            timeout_ms=need.get("timeout_ms", self.default_timeout_ms),
        )

    def _extract_minimal_input(self, need: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract minimal input from NEED.

        Args:
            need: Full NEED payload

        Returns:
            Minimal input for micro-task
        """
        # Look for input schema
        if "input_schema" in need:
            schema = need["input_schema"]
            # Create minimal valid input based on schema
            return self._minimal_from_schema(schema)

        # Fallback: empty input
        return {}

    def _minimal_from_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create minimal input satisfying a schema.

        Args:
            schema: JSON schema

        Returns:
            Minimal valid input
        """
        result = {}

        # Get required fields
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for field in required:
            if field in properties:
                field_schema = properties[field]
                field_type = field_schema.get("type", "string")

                # Generate minimal value based on type
                if field_type == "string":
                    result[field] = "test"
                elif field_type == "number" or field_type == "integer":
                    result[field] = 0
                elif field_type == "boolean":
                    result[field] = False
                elif field_type == "array":
                    result[field] = []
                elif field_type == "object":
                    result[field] = {}

        return result

    async def run_canary(self, agent_id: str, canary_test: CanaryTest) -> CanaryResult:
        """
        Run canary test on an agent.

        Args:
            agent_id: Agent to test
            canary_test: Test to run

        Returns:
            Canary result with performance metrics
        """
        logger.info(f"Running canary test on {agent_id}")

        start_time = time.time()

        try:
            # Send micro-task to agent
            if self.send_task_handler:
                await self.send_task_handler(agent_id, canary_test.micro_task)
            else:
                # Simulated mode for testing
                await asyncio.sleep(0.1)

            # Wait for result with timeout
            timeout_seconds = canary_test.timeout_ms / 1000.0

            try:
                if self.receive_result_handler:
                    output = await asyncio.wait_for(
                        self.receive_result_handler(agent_id), timeout=timeout_seconds
                    )
                else:
                    # Simulated result
                    await asyncio.sleep(0.1)
                    output = {"status": "success", "result": "simulated"}

                # Calculate latency
                latency_ms = (time.time() - start_time) * 1000

                # Score quality
                quality_score = self._score_output(output, canary_test.expected_output)

                # Determine if passed
                passed = quality_score >= self.min_quality

                return CanaryResult(
                    agent_id=agent_id,
                    latency_ms=latency_ms,
                    quality_score=quality_score,
                    passed=passed,
                    output=output,
                    error=None,
                )

            except asyncio.TimeoutError:
                latency_ms = (time.time() - start_time) * 1000
                logger.warning(f"Canary test timeout for {agent_id}")

                return CanaryResult(
                    agent_id=agent_id,
                    latency_ms=latency_ms,
                    quality_score=0.0,
                    passed=False,
                    output=None,
                    error="Timeout",
                )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Canary test error for {agent_id}: {e}")

            return CanaryResult(
                agent_id=agent_id,
                latency_ms=latency_ms,
                quality_score=0.0,
                passed=False,
                output=None,
                error=str(e),
            )

    def _score_output(self, output: Any, expected: Optional[Any]) -> float:
        """
        Score output quality.

        Args:
            output: Agent's output
            expected: Expected output (if known)

        Returns:
            Quality score from 0.0 to 1.0
        """
        if expected is None:
            # No expected output, check if output is valid
            return self._score_validity(output)

        # Compare output to expected
        return self._score_correctness(output, expected)

    def _score_validity(self, output: Any) -> float:
        """
        Score output validity when expected output is unknown.

        Args:
            output: Agent's output

        Returns:
            Validity score from 0.0 to 1.0
        """
        if output is None:
            return 0.0

        # Check if output is well-formed
        if isinstance(output, dict):
            # Dictionary output is generally valid
            if "error" in output or "status" in output:
                # Structured response
                return 0.8 if output.get("status") != "error" else 0.3
            return 0.7

        if isinstance(output, (str, list, int, float, bool)):
            # Other types are acceptable
            return 0.6

        return 0.5  # Unknown type, neutral score

    def _score_correctness(self, output: Any, expected: Any) -> float:
        """
        Score output correctness against expected.

        Args:
            output: Agent's output
            expected: Expected output

        Returns:
            Correctness score from 0.0 to 1.0
        """
        # Exact match
        if output == expected:
            return 1.0

        # Type mismatch
        if type(output) != type(expected):
            return 0.2

        # Partial match for dictionaries
        if isinstance(output, dict) and isinstance(expected, dict):
            matching_keys = set(output.keys()) & set(expected.keys())
            total_keys = set(output.keys()) | set(expected.keys())

            if not total_keys:
                return 0.5

            # Key overlap
            key_score = len(matching_keys) / len(total_keys)

            # Value match for common keys
            value_matches = sum(1 for k in matching_keys if output.get(k) == expected.get(k))
            value_score = value_matches / len(matching_keys) if matching_keys else 0

            # Weighted combination
            return 0.4 * key_score + 0.6 * value_score

        # Partial match for strings (simple similarity)
        if isinstance(output, str) and isinstance(expected, str):
            # Simple string similarity
            if expected.lower() in output.lower() or output.lower() in expected.lower():
                return 0.6
            return 0.3

        # Other partial matches
        return 0.4

    async def run_canaries(
        self, agent_ids: List[str], canary_test: CanaryTest
    ) -> List[CanaryResult]:
        """
        Run canary test on multiple agents concurrently.

        Args:
            agent_ids: Agents to test
            canary_test: Test to run

        Returns:
            List of canary results
        """
        tasks = [self.run_canary(agent_id, canary_test) for agent_id in agent_ids]

        results = await asyncio.gather(*tasks)

        return list(results)


# Global runner instance
_global_runner: Optional[CanaryRunner] = None


def get_canary_runner(min_quality: float = 0.6, default_timeout_ms: int = 5000) -> CanaryRunner:
    """Get or create global canary runner"""
    global _global_runner
    if _global_runner is None:
        _global_runner = CanaryRunner(
            min_quality=min_quality, default_timeout_ms=default_timeout_ms
        )
    return _global_runner


def reset_canary_runner() -> None:
    """Reset global runner (for testing)"""
    global _global_runner
    _global_runner = None
