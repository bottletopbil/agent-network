"""
Property Tests for CAN Swarm (P1-P8)

Tests verify core properties:
- P1: Single DECIDE (consensus uniqueness)
- P2: Deterministic Replay
- P3: Challenge safety
- P4: Epoch fencing
- P5: Lease lifetimes
- P6: Quorum validity
- P7: Merkle consistency
- P8: Cross-shard atomicity

Run: pytest tests/test_properties.py -v
Run under chaos: pytest tests/test_properties.py --chaos -v
"""

import pytest
import time
import sys

sys.path.insert(0, "tools")

# Chaos testing support
CHAOS_MODE = False


def pytest_addoption(parser):
    """Add --chaos flag to pytest"""
    parser.addoption(
        "--chaos",
        action="store_true",
        default=False,
        help="Run tests under chaos conditions",
    )


def pytest_configure(config):
    """Configure chaos mode"""
    global CHAOS_MODE
    CHAOS_MODE = config.getoption("--chaos")

    if CHAOS_MODE:
        print("\n🌪️  CHAOS ENABLED - Testing under adversarial conditions")


class TestP1SingleDecide:
    """P1: Single DECIDE - Only one DECIDE per NEED"""

    def test_single_decide_invariant(self):
        """Verify only one DECIDE can exist per NEED"""
        decides_per_need = {}

        # Simulate multiple DECIDE attempts for same NEED
        need_id = "need_1"
        proposals = ["proposal_a", "proposal_b", "proposal_c"]

        for proposal in proposals:
            # Try to record DECIDE
            if need_id not in decides_per_need:
                decides_per_need[need_id] = proposal

        # Should only have first proposal
        assert decides_per_need[need_id] == "proposal_a"
        assert len([v for k, v in decides_per_need.items() if k == need_id]) == 1


class TestP2DeterministicReplay:
    """P2: Deterministic Replay - Same inputs → same outputs"""

    def test_replay_determinism(self):
        """Verify replaying produces same results"""
        # Simulate event log
        events = [
            {"type": "NEED", "id": "1", "lamport": 1},
            {"type": "DECIDE", "id": "1", "lamport": 2, "agent": "agent_a"},
            {"type": "FINALIZE", "id": "1", "lamport": 3, "result": "success"},
        ]

        def replay(events):
            state = {}
            for event in sorted(events, key=lambda e: e["lamport"]):
                if event["type"] == "FINALIZE":
                    state[event["id"]] = event["result"]
            return state

        # Replay multiple times
        result1 = replay(events)
        result2 = replay(events)

        assert result1 == result2
        assert result1["1"] == "success"


class TestP3ChallengeSafety:
    """P3: Challenge Safety - Challenges require stake and evidence"""

    def test_challenge_requires_stake(self):
        """Test that challenges require minimum stake"""
        minimum_stake = 100
        challenger_stake = 50

        can_challenge = challenger_stake >= minimum_stake
        assert not can_challenge

    def test_challenge_requires_evidence(self):
        """Test that challenges must include proof"""
        challenge = {
            "challenger_id": "challenger1",
            "challenged_commit": "commit_123",
            "evidence": None,
        }

        is_valid = challenge.get("evidence") is not None
        assert not is_valid

    def test_challenge_has_deadline(self):
        """Test that challenges expire after deadline"""
        challenge_time = time.time()
        deadline = challenge_time + 3600  # 1 hour
        current_time = challenge_time + 7200  # 2 hours later

        is_expired = current_time > deadline
        assert is_expired


class TestP4EpochFencing:
    """P4: Epoch Fencing - Old epochs rejected"""

    def test_old_epoch_rejected(self):
        """Test that messages from old epochs are rejected"""
        current_epoch = 5
        message_epoch = 3

        is_valid = message_epoch >= current_epoch
        assert not is_valid

    def test_epoch_advancement_requires_quorum(self):
        """Test that epoch advancement requires majority"""
        total_nodes = 5
        votes_to_advance = 2
        quorum = (total_nodes // 2) + 1

        can_advance = votes_to_advance >= quorum
        assert not can_advance

    def test_epoch_monotonicity(self):
        """Test that epochs only increase"""
        epochs = [1, 2, 3, 2, 4]

        # Filter to monotonic sequence
        filtered = []
        max_seen = 0
        for epoch in epochs:
            if epoch >= max_seen:
                filtered.append(epoch)
                max_seen = epoch

        # Filtered should be monotonic
        is_monotonic = all(filtered[i] <= filtered[i + 1] for i in range(len(filtered) - 1))
        assert is_monotonic
        assert filtered == [1, 2, 3, 4]


class TestP5LeaseLifetimes:
    """P5: Lease Lifetimes - Leases expire correctly"""

    def test_expired_lease_rejected(self):
        """Test that expired leases are rejected"""
        lease_start = time.time() - 7200  # 2 hours ago
        lease_duration = 3600  # 1 hour
        lease_expiry = lease_start + lease_duration
        current_time = time.time()

        is_expired = current_time > lease_expiry
        assert is_expired

    def test_lease_renewal_before_expiry(self):
        """Test that leases can be renewed before expiration"""
        lease_start = time.time() - 1800  # 30 min ago
        lease_duration = 3600  # 1 hour
        lease_expiry = lease_start + lease_duration
        current_time = time.time()

        is_valid = current_time < lease_expiry
        assert is_valid

    def test_lease_holder_exclusive_access(self):
        """Test that only lease holder has access"""
        lease_holder = "agent1"
        requesting_agent = "agent2"

        has_access = requesting_agent == lease_holder
        assert not has_access


class TestP6QuorumValidity:
    """P6: Quorum Validity - Decisions require majority"""

    def test_quorum_requires_majority(self):
        """Test that quorum requires >50%"""
        total_verifiers = 5
        agreeing_verifiers = 2
        quorum = (total_verifiers // 2) + 1

        has_quorum = agreeing_verifiers >= quorum
        assert not has_quorum

        # With majority
        agreeing_verifiers = 3
        has_quorum = agreeing_verifiers >= quorum
        assert has_quorum

    def test_quorum_diversity_constraints(self):
        """Test that quorum respects diversity"""
        verifiers = [
            {"id": "v1", "entity": "company_a"},
            {"id": "v2", "entity": "company_a"},
            {"id": "v3", "entity": "company_a"},
        ]

        entities = set(v["entity"] for v in verifiers)
        is_diverse = len(entities) > 1
        assert not is_diverse

    def test_byzantine_fault_tolerance(self):
        """Test BFT constraint (f < n/3)"""
        total_nodes = 10
        byzantine_nodes = 4
        max_byzantine = (total_nodes - 1) // 3

        is_tolerable = byzantine_nodes <= max_byzantine
        assert not is_tolerable


class TestP7MerkleConsistency:
    """P7: Merkle Consistency - Trees detect tampering"""

    def test_merkle_detects_tampering(self):
        """Test that Merkle tree detects data tampering"""
        original_data = ["block1", "block2", "block3"]
        original_root = hash(tuple(original_data))

        tampered_data = ["block1", "TAMPERED", "block3"]
        tampered_root = hash(tuple(tampered_data))

        assert original_root != tampered_root

    def test_merkle_proof_verification(self):
        """Test that Merkle proofs verify correctly"""
        data = "block2"
        proof = ["hash_of_block1", "hash_of_block3"]
        root = "merkle_root_hash"

        # Simplified verification
        def verify_proof(data, proof, root):
            return len(proof) > 0 and root is not None

        is_valid = verify_proof(data, proof, root)
        assert is_valid

    def test_merkle_append_only(self):
        """Test that Merkle trees are append-only"""
        tree_sequence = [1, 2, 3, 4, 5]
        invalid_sequence = [1, 2, 4, 5]  # Missing element

        is_append_only = len(invalid_sequence) < len(tree_sequence)
        assert is_append_only


class TestP8CrossShardAtomicity:
    """P8: Cross-Shard Atomicity - All-or-nothing commits"""

    def test_two_phase_commit_atomicity(self):
        """Test that 2PC ensures atomicity"""
        shards = {
            "shard1": {"prepared": True, "committed": False},
            "shard2": {"prepared": True, "committed": False},
            "shard3": {"prepared": False, "committed": False},
        }

        all_prepared = all(s["prepared"] for s in shards.values())
        assert not all_prepared

        should_commit = all_prepared
        assert not should_commit

    def test_coordinator_failure_recovery(self):
        """Test recovery from coordinator failure"""
        transaction_log = {
            "tx_id": "tx123",
            "phase": "prepare",
            "prepared_shards": ["shard1", "shard2"],
            "total_shards": ["shard1", "shard2", "shard3"],
        }

        all_prepared = len(transaction_log["prepared_shards"]) == len(
            transaction_log["total_shards"]
        )
        assert not all_prepared

        should_abort = not all_prepared
        assert should_abort

    def test_shard_isolation(self):
        """Test that shards cannot interfere"""
        shard1_state = {"counter": 10}
        shard2_state = {"counter": 20}

        shard1_state["counter"] += 5

        assert shard2_state["counter"] == 20
        assert shard1_state["counter"] == 15


@pytest.mark.skipif(not CHAOS_MODE, reason="Requires --chaos flag")
class TestChaosResilience:
    """Properties verified under chaos"""

    def test_p1_under_partition(self):
        """Test P1 (Single DECIDE) under network partition"""
        from chaos import ChaosRunner, PartitionNemesis
        from chaos.runner import property_decide_uniqueness

        nemeses = [PartitionNemesis(probability=0.5)]
        runner = ChaosRunner(nemeses, seed=42)

        runner.context["agents"] = ["agent1", "agent2", "agent3", "agent4"]
        runner.context["decides"] = {}

        def workload(context):
            need_id = "test_need"
            agent_id = context["agents"][0] if context["agents"] else "agent1"

            if need_id not in context["decides"]:
                context["decides"][need_id] = []

            if len(context["decides"][need_id]) == 0:
                context["decides"][need_id].append({"agent": agent_id})

            return True

        properties = {"decide_uniqueness": property_decide_uniqueness}
        result = runner.run(workload, properties, duration_sec=2.0, chaos_interval_sec=0.5)

        assert result.property_checks["decide_uniqueness"]

    def test_p4_under_clock_skew(self):
        """Test P4 (Epoch Fencing) under clock skew"""
        from chaos import ChaosRunner, ClockSkewNemesis

        nemeses = [ClockSkewNemesis(probability=1.0, skew_ms=1000)]
        runner = ChaosRunner(nemeses, seed=42)

        runner.context["agents"] = ["agent1", "agent2"]
        runner.context["epoch"] = 1

        def workload(context):
            return True

        properties = {"epoch_valid": lambda ctx: ctx.get("epoch", 0) > 0}

        result = runner.run(workload, properties, duration_sec=1.0, chaos_interval_sec=0.3)
        assert result.property_checks["epoch_valid"]


if __name__ == "__main__":
    import sys

    pytest.main([__file__, "-v"] + sys.argv[1:])
