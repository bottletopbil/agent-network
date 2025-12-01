"""
Tests for Deterministic Simulator.

Verifies:
- Audit log loading
- Deterministic replay
- Chaos injection (clock skew and message reordering)
- FINALIZE verification
"""

import sys
import os
import tempfile
import json
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from simulator import DeterministicSimulator, SimulationResult


def create_test_audit_log(thread_id: str = "test-thread") -> str:
    """Create a temporary audit log for testing"""
    log_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl")

    events = [
        {
            "thread_id": thread_id,
            "kind": "BUS.PUBLISH",
            "payload": {
                "kind": "NEED",
                "lamport": 1,
                "timestamp_ns": 1000000000,
                "payload": {"need_id": "need_1", "task": "analyze_code"},
            },
        },
        {
            "thread_id": thread_id,
            "kind": "BUS.PUBLISH",
            "payload": {
                "kind": "DECIDE",
                "lamport": 2,
                "timestamp_ns": 2000000000,
                "payload": {
                    "need_id": "need_1",
                    "agent_id": "agent_1",
                    "decision": "accepted",
                },
            },
        },
        {
            "thread_id": thread_id,
            "kind": "BUS.PUBLISH",
            "payload": {
                "kind": "FINALIZE",
                "lamport": 3,
                "timestamp_ns": 3000000000,
                "payload": {
                    "need_id": "need_1",
                    "agent_id": "agent_1",
                    "result": "success",
                },
            },
        },
    ]

    for event in events:
        log_file.write(json.dumps(event) + "\n")

    log_file.close()
    return log_file.name


class TestSimulatorLoading:
    """Test audit log loading functionality"""

    def test_load_audit_log_basic(self):
        """Test loading a basic audit log"""
        log_path = create_test_audit_log()

        try:
            sim = DeterministicSimulator()
            envelopes = sim.load_audit_log(log_path)

            # Should load 3 envelopes
            assert len(envelopes) == 3
            assert envelopes[0]["kind"] == "NEED"
            assert envelopes[1]["kind"] == "DECIDE"
            assert envelopes[2]["kind"] == "FINALIZE"
        finally:
            os.unlink(log_path)

    def test_load_audit_log_with_thread_filter(self):
        """Test filtering by thread ID"""
        log_path = create_test_audit_log("thread-1")

        try:
            sim = DeterministicSimulator()

            # Load with matching thread_id
            envelopes = sim.load_audit_log(log_path, thread_id="thread-1")
            assert len(envelopes) == 3

            # Load with non-matching thread_id
            sim.reset()
            envelopes = sim.load_audit_log(log_path, thread_id="thread-2")
            assert len(envelopes) == 0
        finally:
            os.unlink(log_path)

    def test_load_nonexistent_file(self):
        """Test error handling for missing file"""
        sim = DeterministicSimulator()

        with pytest.raises(FileNotFoundError):
            sim.load_audit_log("/nonexistent/path.jsonl")

    def test_load_malformed_json(self):
        """Test handling of malformed JSON"""
        log_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl")
        log_file.write('{"valid": "json"}\n')
        log_file.write("{invalid json\n")
        log_file.write('{"another": "valid"}\n')
        log_file.close()

        try:
            sim = DeterministicSimulator()
            envelopes = sim.load_audit_log(log_file.name)

            # Should have 1 warning for malformed line
            assert len(sim.warnings) == 1
            assert "Invalid JSON" in sim.warnings[0]
        finally:
            os.unlink(log_file.name)


class TestDeterministicReplay:
    """Test deterministic replay functionality"""

    def test_replay_basic(self):
        """Test basic envelope replay"""
        log_path = create_test_audit_log()

        try:
            sim = DeterministicSimulator(seed=42)
            envelopes = sim.load_audit_log(log_path)
            result = sim.replay_envelopes(validate_policy=False)

            assert result.success
            assert result.envelopes_processed == 3
            assert len(result.decide_events) == 1
            assert len(result.finalize_events) == 1

            # Check state
            assert "need_1" in result.final_state["needs"]
            assert "need_1" in result.final_state["decisions"]
            assert "need_1" in result.final_state["finalizations"]
        finally:
            os.unlink(log_path)

    def test_replay_empty_envelopes(self):
        """Test replay with no envelopes"""
        sim = DeterministicSimulator()
        result = sim.replay_envelopes([])

        assert not result.success
        assert result.envelopes_processed == 0
        assert "No envelopes" in result.errors[0]

    def test_replay_lamport_ordering(self):
        """Test that replay sorts by Lamport clock"""
        # Create envelopes out of order
        envelopes = [
            {"kind": "NEED", "lamport": 3, "payload": {"need_id": "3"}},
            {"kind": "NEED", "lamport": 1, "payload": {"need_id": "1"}},
            {"kind": "NEED", "lamport": 2, "payload": {"need_id": "2"}},
        ]

        sim = DeterministicSimulator()
        result = sim.replay_envelopes(envelopes, validate_policy=False)

        assert result.success
        # State should reflect sorted order
        assert result.final_state["lamport"] == 3

    def test_replay_duplicate_decide(self):
        """Test that duplicate DECIDE is caught"""
        envelopes = [
            {"kind": "NEED", "lamport": 1, "payload": {"need_id": "need_1"}},
            {
                "kind": "DECIDE",
                "lamport": 2,
                "payload": {"need_id": "need_1", "agent_id": "agent_1"},
            },
            {
                "kind": "DECIDE",
                "lamport": 3,
                "payload": {"need_id": "need_1", "agent_id": "agent_2"},  # Duplicate!
            },
        ]

        sim = DeterministicSimulator()
        result = sim.replay_envelopes(envelopes, validate_policy=False)

        assert not result.success
        assert any("Duplicate DECIDE" in error for error in result.errors)


class TestChaosInjection:
    """Test chaos injection capabilities"""

    def test_inject_clock_skew(self):
        """Test clock skew injection"""
        envelopes = [
            {"kind": "NEED", "lamport": 1, "timestamp_ns": 1000000000},
            {"kind": "DECIDE", "lamport": 2, "timestamp_ns": 2000000000},
        ]

        sim = DeterministicSimulator(seed=42)
        skewed = sim.inject_clock_skew(100, envelopes)  # ±100ms

        # Timestamps should be modified
        assert skewed[0]["timestamp_ns"] != envelopes[0]["timestamp_ns"]
        assert skewed[1]["timestamp_ns"] != envelopes[1]["timestamp_ns"]

        # Lamport clocks should be unchanged
        assert skewed[0]["lamport"] == envelopes[0]["lamport"]
        assert skewed[1]["lamport"] == envelopes[1]["lamport"]

    def test_inject_clock_skew_does_not_go_negative(self):
        """Test that clock skew doesn't create negative timestamps"""
        envelopes = [
            {
                "kind": "NEED",
                "lamport": 1,
                "timestamp_ns": 100000,
            },  # Very small timestamp
        ]

        sim = DeterministicSimulator(seed=42)
        skewed = sim.inject_clock_skew(1000, envelopes)  # Large skew

        # Should not go negative
        assert skewed[0]["timestamp_ns"] >= 0

    def test_inject_message_reorder(self):
        """Test message reordering within same Lamport groups"""
        # Create messages with some having the same Lamport clock
        envelopes = [
            {"kind": "NEED", "lamport": 1, "payload": {"id": 1}},
            {"kind": "DECIDE", "lamport": 2, "payload": {"id": 2}},
            {"kind": "DECIDE", "lamport": 2, "payload": {"id": 3}},  # Same Lamport
            {"kind": "FINALIZE", "lamport": 3, "payload": {"id": 4}},
            {"kind": "FINALIZE", "lamport": 3, "payload": {"id": 5}},  # Same Lamport
            {"kind": "NEED", "lamport": 4, "payload": {"id": 6}},
        ]

        sim = DeterministicSimulator(seed=42)
        reordered = sim.inject_message_reorder(
            probability=1.0, max_distance=10, envelopes=envelopes  # Always reorder
        )

        # Lamport order should be preserved
        lamports = [env["lamport"] for env in reordered]
        assert lamports == sorted(lamports)

        # But within same Lamport, order may change
        # All messages should still be present
        assert len(reordered) == len(envelopes)

    def test_reorder_respects_causality(self):
        """Test that reordering respects Lamport causality"""
        envelopes = [
            {"kind": "NEED", "lamport": 1, "payload": {"id": 1}},
            {"kind": "DECIDE", "lamport": 2, "payload": {"id": 2}},
            {"kind": "FINALIZE", "lamport": 3, "payload": {"id": 3}},
        ]

        sim = DeterministicSimulator(seed=42)
        reordered = sim.inject_message_reorder(
            probability=1.0,  # Try to reorder everything
            max_distance=10,
            envelopes=envelopes,
        )

        # Lamport order should still be monotonic
        lamports = [env["lamport"] for env in reordered]
        assert lamports == sorted(lamports)


class TestFinalizeVerification:
    """Test FINALIZE verification"""

    def test_verify_finalize_match_exact(self):
        """Test exact FINALIZE match"""
        envelope1 = {
            "kind": "FINALIZE",
            "lamport": 3,
            "timestamp_ns": 3000000000,
            "payload": {
                "need_id": "need_1",
                "agent_id": "agent_1",
                "result": "success",
            },
        }

        envelope2 = envelope1.copy()

        sim = DeterministicSimulator()
        matches, diffs = sim.verify_finalize_match(envelope1, envelope2)

        assert matches
        assert len(diffs) == 0

    def test_verify_finalize_critical_field_mismatch(self):
        """Test mismatch in critical fields"""
        envelope1 = {
            "kind": "FINALIZE",
            "payload": {
                "need_id": "need_1",
                "agent_id": "agent_1",
                "result": "success",
            },
        }

        envelope2 = {
            "kind": "FINALIZE",
            "payload": {
                "need_id": "need_1",
                "agent_id": "agent_1",
                "result": "failure",  # Different result!
            },
        }

        sim = DeterministicSimulator()
        matches, diffs = sim.verify_finalize_match(envelope1, envelope2)

        assert not matches
        assert any("result" in diff for diff in diffs)

    def test_verify_finalize_strict_mode(self):
        """Test strict mode checking Lamport and timestamp"""
        envelope1 = {
            "kind": "FINALIZE",
            "lamport": 3,
            "timestamp_ns": 3000000000,
            "payload": {
                "need_id": "need_1",
                "agent_id": "agent_1",
                "result": "success",
            },
        }

        envelope2 = {
            "kind": "FINALIZE",
            "lamport": 4,  # Different Lamport
            "timestamp_ns": 3000000000,
            "payload": {
                "need_id": "need_1",
                "agent_id": "agent_1",
                "result": "success",
            },
        }

        sim = DeterministicSimulator()

        # Strict mode should fail
        matches, diffs = sim.verify_finalize_match(envelope1, envelope2, strict=True)
        assert not matches
        assert any("Lamport" in diff for diff in diffs)

        # Non-strict mode should pass (critical fields match)
        matches, diffs = sim.verify_finalize_match(envelope1, envelope2, strict=False)
        assert matches

    def test_verify_non_finalize_envelope(self):
        """Test verification with non-FINALIZE envelope"""
        envelope1 = {"kind": "NEED", "payload": {}}
        envelope2 = {"kind": "FINALIZE", "payload": {}}

        sim = DeterministicSimulator()
        matches, diffs = sim.verify_finalize_match(envelope1, envelope2)

        assert not matches
        assert "not FINALIZE" in diffs[0]


class TestSimulatorState:
    """Test simulator state management"""

    def test_reset(self):
        """Test simulator reset"""
        log_path = create_test_audit_log()

        try:
            sim = DeterministicSimulator()
            sim.load_audit_log(log_path)
            sim.replay_envelopes(validate_policy=False)

            # State should have data
            assert len(sim.envelopes) > 0
            assert sim.state["lamport"] > 0

            # Reset
            sim.reset()

            # State should be cleared
            assert len(sim.envelopes) == 0
            assert sim.state["lamport"] == 0
            assert len(sim.state["needs"]) == 0
        finally:
            os.unlink(log_path)

    def test_get_state(self):
        """Test getting state (should be a copy)"""
        sim = DeterministicSimulator()
        sim.state["test_key"] = "test_value"

        state = sim.get_state()
        state["test_key"] = "modified"

        # Original state should be unchanged
        assert sim.state["test_key"] == "test_value"


class TestEndToEndSimulation:
    """Test complete simulation workflows"""

    def test_deterministic_replays_match(self):
        """Test that multiple replays produce the same result"""
        log_path = create_test_audit_log()

        try:
            # First replay
            sim1 = DeterministicSimulator(seed=42)
            envelopes = sim1.load_audit_log(log_path)
            result1 = sim1.replay_envelopes(validate_policy=False)

            # Second replay with same seed
            sim2 = DeterministicSimulator(seed=42)
            sim2.load_audit_log(log_path)
            result2 = sim2.replay_envelopes(validate_policy=False)

            # Results should match
            assert result1.success == result2.success
            assert result1.envelopes_processed == result2.envelopes_processed
            assert len(result1.decide_events) == len(result2.decide_events)
            assert len(result1.finalize_events) == len(result2.finalize_events)

            # Final states should match
            assert result1.final_state == result2.final_state
        finally:
            os.unlink(log_path)

    def test_chaos_injection_workflow(self):
        """Test complete chaos injection workflow"""
        log_path = create_test_audit_log()

        try:
            sim = DeterministicSimulator(seed=42)
            envelopes = sim.load_audit_log(log_path)

            # Normal replay
            result_normal = sim.replay_envelopes(validate_policy=False)

            # Inject chaos
            skewed = sim.inject_clock_skew(100, envelopes)
            reordered = sim.inject_message_reorder(0.2, 2, skewed)

            # Replay with chaos
            sim.reset()
            result_chaos = sim.replay_envelopes(reordered, validate_policy=False)

            # Both should succeed (system is resilient)
            assert result_normal.success
            assert result_chaos.success

            # FINALIZE should match despite chaos
            if result_normal.finalize_events and result_chaos.finalize_events:
                matches, diffs = sim.verify_finalize_match(
                    result_normal.finalize_events[0],
                    result_chaos.finalize_events[0],
                    strict=False,
                )
                assert matches
        finally:
            os.unlink(log_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
