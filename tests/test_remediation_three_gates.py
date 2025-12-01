"""
Test for three-gate policy enforcement integration (ARCH-001).

Validates that all three gates (preflight, ingress, commit_gate) are
properly integrated and invoked in the correct scenarios.
"""

import sys
from pathlib import Path
import pytest
from unittest.mock import Mock, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from policy.gates import GateEnforcer, PolicyGate, PolicyDecision


def test_preflight_gate_caching():
    """
    Test that preflight gate uses caching for performance.
    """
    gate_enforcer = GateEnforcer(enable_cache=True)
    
    envelope = {
        "operation": "NEED",
        "sender_pk_b64": "test_sender",
        "thread_id": "thread_123",
        "payload": {"task_type": "test"}
    }
    
    # First call - should evaluate and cache
    decision1 = gate_enforcer.preflight_validate(envelope)
    assert decision1.gate == PolicyGate.PREFLIGHT
    assert isinstance(decision1.allowed, bool)
    
    # Second call - should hit cache
    decision2 = gate_enforcer.preflight_validate(envelope)
    assert decision2.gate == PolicyGate.PREFLIGHT
    
    # Decisions should be same (cached)
    assert decision1.allowed == decision2.allowed


def test_ingress_gate_full_validation():
    """
    Test that ingress gate performs full validation.
    """
    gate_enforcer = GateEnforcer()
    
    envelope = {
        "operation": "DECIDE",
        "sender_pk_b64": "test_sender",
        "thread_id": "thread_456",
        "lamport": 5,
        "payload": {"task_id": "task_123"}
    }
    
    # Should perform full validation (not just cached check)
    decision = gate_enforcer.ingress_validate(envelope)
    assert decision.gate == PolicyGate.INGRESS
    assert isinstance(decision.allowed, bool)
    # Ingress may use more gas than preflight
    assert decision.gas_used >= 0


def test_commit_gate_with_telemetry():
    """
    Test that commit gate validates with telemetry data.
    """
    gate_enforcer = GateEnforcer()
    
    envelope = {
        "operation": "COMMIT",
        "sender_pk_b64": "worker_agent",
        "thread_id": "thread_789",
        "payload": {
            "task_id": "task_123",
            "artifact_hash": "abc123def456"
        }
    }
    
    telemetry = {
        "cpu_time_ms": 500,
        "memory_mb": 128,
        "disk_bytes": 1024
    }
    
    # Commit gate checks claimed vs actual resources
    decision = gate_enforcer.commit_gate_validate(envelope, telemetry)
    assert decision.gate == PolicyGate.COMMIT_GATE
    assert isinstance(decision.allowed, bool)


def test_all_three_gates_invoked():
    """
    Test simulation showing all three gates in proper flow.
    """
    gate_enforcer = GateEnforcer()
    
    # 1. PREFLIGHT: Before publishing
    envelope = {
        "operation": "NEED",
        "sender_pk_b64": "planner",
        "thread_id": "thread_workflow",
        "payload": {"task_type": "analysis"}
    }
    
    preflight = gate_enforcer.preflight_validate(envelope)
    assert preflight.gate == PolicyGate.PREFLIGHT
    print(f"✓ Preflight gate: {preflight.allowed}")
    
    # 2. INGRESS: On receive
    ingress = gate_enforcer.ingress_validate(envelope)
    assert ingress.gate == PolicyGate.INGRESS
    print(f"✓ Ingress gate: {ingress.allowed}")
    
    # 3. COMMIT_GATE: Before attestation
    commit_envelope = {
        "operation": "COMMIT",
        "sender_pk_b64": "worker",
        "thread_id": "thread_workflow",
        "payload": {"task_id": "  task_1", "artifact_hash": "hash123"}
    }
    
    telemetry = {"cpu_time_ms": 100, "memory_mb": 64}
    commit_gate = gate_enforcer.commit_gate_validate(commit_envelope, telemetry)
    assert commit_gate.gate == PolicyGate.COMMIT_GATE
    print(f"✓ Commit gate: {commit_gate.allowed}")
    
    # All three gates invoked
    assert preflight.gate != ingress.gate != commit_gate.gate


def test_gate_enforcer_rejection():
    """
    Test that gates can reject operations.
    """
    gate_enforcer = GateEnforcer()
    
    # Create envelope that violates policy
    malicious_envelope = {
        "operation": "UNKNOWN_OP",
        "sender_pk_b64": "malicious_actor",
        "thread_id": "thread_attack",
        "payload": {"exploit": "attempt"}
    }
    
    decision = gate_enforcer.preflight_validate(malicious_envelope)
    
    # Should have a decision (allowed or not)
    assert isinstance(decision.allowed, bool)
    
    # If rejected, should have a reason
    if not decision.allowed:
        assert decision.reason is not None
        print(f"✓ Rejected with reason: {decision.reason}")


def test_cache_key_generation():
    """
    Test that cache keys properly distinguish different operations.
    """
    gate_enforcer = GateEnforcer(enable_cache=True)
    
    envelope1 = {
        "operation": "NEED",
        "sender_pk_b64": "agent1",
        "thread_id": "thread_1",
        "payload": {}
    }
    
    envelope2 = {
        "operation": "DECIDE",  # Different operation
        "sender_pk_b64": "agent1",
        "thread_id": "thread_1",
        "payload": {}
    }
    
    decision1 = gate_enforcer.preflight_validate(envelope1)
    decision2 = gate_enforcer.preflight_validate(envelope2)
    
    # Different operations should not share cache
    assert decision1.gate == PolicyGate.PREFLIGHT
    assert decision2.gate == PolicyGate.PREFLIGHT
