"""
Remediation tests for ingress policy-bypass prevention (SEC-002).
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import bus as bus_module
import coordinator as coordinator_module
from bus import P2PBus
from bus.hybrid import HybridBus
from policy.gates import PolicyDecision, PolicyGate


class _AllowEnforcer:
    def ingress_validate(self, envelope):
        return PolicyDecision(
            allowed=True,
            gate=PolicyGate.INGRESS,
            reason="allowed",
        )


class _ErrorEnforcer:
    def ingress_validate(self, envelope):
        raise RuntimeError("simulated gate failure")


class _MockRouter:
    def __init__(self):
        self._handler = None

    def subscribe(self, topic, handler):
        self._handler = handler

    def publish(self, topic, payload):
        return None

    def get_stats(self):
        return {}

    def deliver(self, envelope):
        assert self._handler is not None
        self._handler(json.dumps(envelope).encode("utf-8"))


class _MockNATSBus:
    def __init__(self):
        self.subscriptions = {}

    def subscribe_envelopes(self, subject, handler):
        self.subscriptions.setdefault(subject, []).append(handler)

    def simulate_receive(self, subject, envelope):
        for handler in self.subscriptions.get(subject, []):
            handler(envelope)


class _MockP2PBus:
    def __init__(self):
        self.subscriptions = {}

    def subscribe_envelopes(self, subject, handler):
        self.subscriptions.setdefault(subject, []).append(handler)


def _valid_ingress_envelope(lamport=1):
    return {
        "id": f"env-{lamport}",
        "kind": "NEED",
        "thread_id": "thread-sec-002",
        "lamport": lamport,
        "sender_pk_b64": "agent-public-key",
        "payload": {"task_type": "classify"},
    }


@pytest.mark.asyncio
async def test_happy_path_valid_ingress_reaches_dispatch_once(monkeypatch):
    monkeypatch.setattr(bus_module, "get_gate_enforcer", lambda: _AllowEnforcer())

    dispatched = {"count": 0}

    async def fake_dispatch(envelope):
        dispatched["count"] += 1
        return True

    monkeypatch.setattr(coordinator_module.DISPATCHER, "dispatch", fake_dispatch)

    coordinator = coordinator_module.Coordinator.__new__(coordinator_module.Coordinator)
    await coordinator.handle_envelope(_valid_ingress_envelope())

    assert dispatched["count"] == 1


@pytest.mark.asyncio
async def test_failure_path_invalid_policy_hash_blocked_before_dispatch(monkeypatch):
    monkeypatch.setattr(bus_module, "get_gate_enforcer", lambda: _AllowEnforcer())

    dispatched = {"count": 0}

    async def fake_dispatch(envelope):
        dispatched["count"] += 1
        return True

    monkeypatch.setattr(coordinator_module.DISPATCHER, "dispatch", fake_dispatch)

    coordinator = coordinator_module.Coordinator.__new__(coordinator_module.Coordinator)

    # Presence of policy_engine_hash triggers baseline validate_envelope(),
    # and the mismatch must fail before dispatch.
    invalid = _valid_ingress_envelope()
    invalid["policy_engine_hash"] = "invalid-policy-hash"

    await coordinator.handle_envelope(invalid)

    assert dispatched["count"] == 0


def test_abuse_path_p2p_invalid_envelope_never_reaches_handler(monkeypatch):
    monkeypatch.setattr(bus_module, "get_gate_enforcer", lambda: _AllowEnforcer())

    router = _MockRouter()
    p2p_bus = P2PBus(gossipsub_router=router)

    received = []
    p2p_bus.subscribe_envelopes("thread-sec-002.need", lambda env: received.append(env))

    # Missing required ingress fields -> rejected.
    router.deliver({"kind": "NEED", "payload": {}})
    assert received == []

    # Valid ingress envelope is accepted.
    router.deliver(_valid_ingress_envelope(lamport=2))
    assert len(received) == 1


def test_idempotency_retry_repeated_malicious_envelope_no_state_mutation(monkeypatch):
    monkeypatch.setattr(bus_module, "get_gate_enforcer", lambda: _AllowEnforcer())

    hybrid = HybridBus(nats_bus=_MockNATSBus(), p2p_bus=_MockP2PBus())

    received = []
    hybrid.subscribe_envelopes("thread-sec-002.need", lambda env: received.append(env))

    malicious = {"kind": "NEED", "payload": {"exploit": True}}

    hybrid.nats_bus.simulate_receive("thread-sec-002.need", malicious)
    hybrid.nats_bus.simulate_receive("thread-sec-002.need", malicious)

    assert received == []
    assert hybrid.message_cache.size() == 0


def test_recovery_path_gate_error_fail_closed_and_process_recovers(monkeypatch):
    router = _MockRouter()
    p2p_bus = P2PBus(gossipsub_router=router)

    received = []
    p2p_bus.subscribe_envelopes("thread-sec-002.need", lambda env: received.append(env))

    envelope = _valid_ingress_envelope(lamport=3)

    # Gate failure: message rejected, process continues.
    monkeypatch.setattr(bus_module, "get_gate_enforcer", lambda: _ErrorEnforcer())
    router.deliver(envelope)
    assert received == []

    # Gate restored: same process now accepts valid ingress.
    monkeypatch.setattr(bus_module, "get_gate_enforcer", lambda: _AllowEnforcer())
    router.deliver(envelope)
    assert len(received) == 1
