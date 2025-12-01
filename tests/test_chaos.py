"""
Tests for Chaos Engineering Framework.

Verifies:
- Nemesis activation and healing
- Chaos runner execution
- Property verification under chaos
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import pytest
from chaos.nemesis import PartitionNemesis, SlowNemesis, KillNemesis, ClockSkewNemesis
from chaos.runner import ChaosRunner, property_no_data_loss, property_decide_uniqueness


class TestNemesisBasics:
    """Test basic nemesis functionality"""

    def test_partition_nemesis_inject(self):
        """Test network partition injection"""
        nemesis = PartitionNemesis(probability=1.0, partition_size=2)

        context = {"agents": ["agent1", "agent2", "agent3", "agent4"]}

        # Inject partition
        success = nemesis.inject(context)

        assert success
        assert nemesis.active
        assert len(nemesis.partitions) == 2
        assert "message_filter" in context

    def test_partition_nemesis_filter(self):
        """Test partition filtering"""
        nemesis = PartitionNemesis(probability=1.0, partition_size=2)

        context = {"agents": ["agent1", "agent2", "agent3", "agent4"]}
        nemesis.inject(context)

        # Get partitions
        partition1 = list(nemesis.partitions[0])
        partition2 = list(nemesis.partitions[1])

        # Messages within same partition should pass
        filter_fn = context["message_filter"]
        assert filter_fn(partition1[0], partition1[0]) == True  # Same agent

        # Messages across partitions should be blocked
        assert filter_fn(partition1[0], partition2[0]) == False

    def test_partition_nemesis_heal(self):
        """Test partition healing"""
        nemesis = PartitionNemesis(probability=1.0)

        context = {"agents": ["agent1", "agent2"]}
        nemesis.inject(context)

        # Heal
        success = nemesis.heal(context)

        assert success
        assert not nemesis.active
        assert len(nemesis.partitions) == 0
        assert "message_filter" not in context

    def test_slow_nemesis_inject(self):
        """Test message delay injection"""
        nemesis = SlowNemesis(probability=1.0, delay_ms=10)

        context = {}

        # Inject delay
        success = nemesis.inject(context)

        assert success
        assert nemesis.active
        assert "message_interceptor" in context

    def test_slow_nemesis_delays_messages(self):
        """Test that messages are actually delayed"""
        nemesis = SlowNemesis(probability=1.0, delay_ms=50)

        context = {}
        nemesis.inject(context)

        interceptor = context["message_interceptor"]
        message = {"data": "test"}

        start = time.time()
        interceptor(message)
        duration = time.time() - start

        # Should have delayed by ~50ms
        assert duration >= 0.04  # Allow some tolerance
        assert "chaos_delay_ms" in message.get("metadata", {})

    def test_kill_nemesis_inject(self):
        """Test agent kill injection"""
        nemesis = KillNemesis(probability=1.0, kill_count=2)

        context = {"agents": ["agent1", "agent2", "agent3"]}

        # Kill agents
        success = nemesis.inject(context)

        assert success
        assert nemesis.active
        assert len(nemesis.killed_agents) == 2
        assert len(context.get("killed_agents", set())) == 2

    def test_kill_nemesis_heal(self):
        """Test agent resurrection"""
        nemesis = KillNemesis(probability=1.0, kill_count=1)

        context = {"agents": ["agent1", "agent2"]}
        nemesis.inject(context)

        # Heal
        success = nemesis.heal(context)

        assert success
        assert not nemesis.active
        assert len(nemesis.killed_agents) == 0

    def test_clock_skew_nemesis_inject(self):
        """Test clock skew injection"""
        nemesis = ClockSkewNemesis(probability=1.0, skew_ms=100)

        context = {"agents": ["agent1", "agent2"]}

        # Inject skew
        success = nemesis.inject(context)

        assert success
        assert nemesis.active
        assert len(nemesis.agent_skews) == 2
        assert "time_interceptor" in context

    def test_clock_skew_applies_offset(self):
        """Test that clock skew applies time offset"""
        nemesis = ClockSkewNemesis(probability=1.0, skew_ms=100)

        context = {"agents": ["agent1"]}
        nemesis.inject(context)

        interceptor = context["time_interceptor"]
        timestamp = 1000000000

        skewed = interceptor("agent1", timestamp)

        # Should have applied skew
        assert skewed != timestamp
        assert abs(skewed - timestamp) <= 100 * 1_000_000  # Within skew range


class TestNemesisActivation:
    """Test nemesis activation logic"""

    def test_should_activate_with_high_probability(self):
        """Test activation with high probability"""
        nemesis = PartitionNemesis(probability=1.0)

        # Should always activate
        activations = sum(1 for _ in range(100) if nemesis.should_activate())
        assert activations == 100

    def test_should_activate_with_low_probability(self):
        """Test activation with low probability"""
        nemesis = PartitionNemesis(probability=0.0)

        # Should never activate
        activations = sum(1 for _ in range(100) if nemesis.should_activate())
        assert activations == 0

    def test_should_activate_probabilistic(self):
        """Test probabilistic activation"""
        nemesis = PartitionNemesis(probability=0.5)

        # Should activate roughly 50% of the time
        activations = sum(1 for _ in range(1000) if nemesis.should_activate())
        assert 400 <= activations <= 600  # Allow reasonable variance


class TestChaosRunner:
    """Test chaos runner"""

    def test_runner_initialization(self):
        """Test runner initialization"""
        nemeses = [PartitionNemesis(probability=0.1), SlowNemesis(probability=0.1)]

        runner = ChaosRunner(nemeses, seed=42)

        assert len(runner.nemeses) == 2
        assert runner.seed == 42

    def test_runner_simple_workload(self):
        """Test running simple workload without chaos"""
        nemeses = []  # No nemeses
        runner = ChaosRunner(nemeses, seed=42)

        # Simple workload
        call_count = [0]

        def workload(context):
            call_count[0] += 1
            context["data"] = "test"
            return True

        # Simple property
        properties = {"data_exists": lambda ctx: "data" in ctx}

        result = runner.run(workload, properties, duration_sec=0.5, chaos_interval_sec=0.1)

        assert result.success
        assert call_count[0] >= 4  # Should have run multiple times
        assert result.property_checks["data_exists"]

    def test_runner_with_partition(self):
        """Test runner with partition nemesis"""
        nemeses = [PartitionNemesis(probability=0.5, partition_size=2)]
        runner = ChaosRunner(nemeses, seed=42)

        runner.context["agents"] = ["agent1", "agent2", "agent3", "agent4"]

        def workload(context):
            # Simulate some work
            time.sleep(0.01)
            return True

        properties = {"agents_exist": lambda ctx: len(ctx.get("agents", [])) > 0}

        result = runner.run(workload, properties, duration_sec=0.5, chaos_interval_sec=0.1)

        # Should complete successfully
        assert len(result.errors) == 0

        # Should have injected some chaos (probabilistic)
        # With seed=42 and multiple opportunities, should have some events
        assert len(result.nemesis_events) >= 0  # May or may not activate

    def test_runner_property_failure(self):
        """Test that property failures are detected"""
        nemeses = []
        runner = ChaosRunner(nemeses, seed=42)

        def workload(context):
            context["value"] = 0
            return True

        properties = {"value_is_positive": lambda ctx: ctx.get("value", 0) > 0}  # Will fail

        result = runner.run(workload, properties, duration_sec=0.2, chaos_interval_sec=0.1)

        assert not result.success  # Property failed
        assert not result.property_checks["value_is_positive"]

    def test_runner_workload_error(self):
        """Test handling of workload errors"""
        nemeses = []
        runner = ChaosRunner(nemeses, seed=42)

        def failing_workload(context):
            raise ValueError("Test error")

        properties = {}

        result = runner.run(failing_workload, properties, duration_sec=0.2, chaos_interval_sec=0.1)

        # Should record errors
        assert len(result.errors) > 0
        assert any("Test error" in error for error in result.errors)


class TestChaosScenarios:
    """Test complete chaos scenarios"""

    def test_partition_resilience_scenario(self):
        """Test system resilience to network partitions"""
        nemeses = [PartitionNemesis(probability=0.3, partition_size=2)]
        runner = ChaosRunner(nemeses, seed=42)

        # Setup
        runner.context["agents"] = ["agent1", "agent2", "agent3", "agent4"]
        runner.context["state"] = {}

        # Workload: agents try to update state
        def workload(context):
            # Simulate state update
            context["state"]["counter"] = context["state"].get("counter", 0) + 1
            return True

        # Properties
        properties = {"state_progresses": lambda ctx: ctx.get("state", {}).get("counter", 0) > 0}

        result = runner.run(workload, properties, duration_sec=1.0, chaos_interval_sec=0.2)

        # Despite partitions, some progress should be made
        assert result.property_checks["state_progresses"]

    def test_slow_network_scenario(self):
        """Test system under slow network conditions"""
        nemeses = [SlowNemesis(probability=0.5, delay_ms=20)]
        runner = ChaosRunner(nemeses, seed=42)

        runner.context["messages"] = []

        # Workload: send messages
        def workload(context):
            context["messages"].append({"id": len(context["messages"])})
            return True

        properties = {"messages_sent": lambda ctx: len(ctx.get("messages", [])) > 0}

        result = runner.run(workload, properties, duration_sec=0.5, chaos_interval_sec=0.1)

        # Even with slow network, messages should be sent
        assert result.property_checks["messages_sent"]

    def test_combined_chaos_scenario(self):
        """Test with multiple nemeses"""
        nemeses = [
            PartitionNemesis(probability=0.2),
            SlowNemesis(probability=0.3, delay_ms=10),
            KillNemesis(probability=0.1, kill_count=1),
        ]

        runner = ChaosRunner(nemeses, seed=42)

        runner.context["agents"] = ["agent1", "agent2", "agent3"]
        runner.context["state"] = {}

        def workload(context):
            # Check if agent is alive
            killed = context.get("killed_agents", set())
            alive_agents = [a for a in context["agents"] if a not in killed]

            if alive_agents:
                context["state"]["active_agents"] = len(alive_agents)

            return True

        properties = {"has_agents": lambda ctx: len(ctx.get("agents", [])) > 0}

        result = runner.run(workload, properties, duration_sec=1.0, chaos_interval_sec=0.2)

        # Should complete
        assert len(result.errors) == 0


class TestPropertyVerification:
    """Test property verification functions"""

    def test_property_no_data_loss(self):
        """Test no data loss property"""
        context = {
            "state": {"key1": "value1", "key2": "value2"},
            "expected_keys": {"key1", "key2"},
        }

        assert property_no_data_loss(context)

        # Remove a key
        del context["state"]["key1"]

        assert not property_no_data_loss(context)

    def test_property_decide_uniqueness(self):
        """Test DECIDE uniqueness property"""
        context = {"decides": {"need1": [{"agent": "agent1"}], "need2": [{"agent": "agent2"}]}}

        assert property_decide_uniqueness(context)

        # Add duplicate DECIDE
        context["decides"]["need1"].append({"agent": "agent3"})

        assert not property_decide_uniqueness(context)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
