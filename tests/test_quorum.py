"""
Tests for quorum tracking and K_plan calculation.
"""
import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from consensus.quorum import QuorumTracker, QuorumState


def test_quorum_tracking():
    """Test that quorum is reached after K attestations"""
    tracker = QuorumTracker()
    
    # First attestation (K=3)
    result = tracker.record_attestation(
        need_id="need-1",
        proposal_id="prop-A",
        verifier_id="v1",
        k_plan=3
    )
    assert result is False  # Not yet quorum
    assert tracker.get_attestation_count("need-1", "prop-A") == 1
    
    # Second attestation
    result = tracker.record_attestation(
        need_id="need-1",
        proposal_id="prop-A",
        verifier_id="v2",
        k_plan=3
    )
    assert result is False  # Still not quorum
    assert tracker.get_attestation_count("need-1", "prop-A") == 2
    
    # Third attestation completes quorum
    result = tracker.record_attestation(
        need_id="need-1",
        proposal_id="prop-A",
        verifier_id="v3",
        k_plan=3
    )
    assert result is True  # Quorum reached!
    assert tracker.check_quorum("need-1", "prop-A") is True
    assert tracker.get_attestation_count("need-1", "prop-A") == 3


def test_quorum_only_triggers_once():
    """Test that quorum completion only triggers once"""
    tracker = QuorumTracker()
    
    # Reach quorum
    tracker.record_attestation("need-1", "prop-A", "v1", k_plan=2)
    result2 = tracker.record_attestation("need-1", "prop-A", "v2", k_plan=2)
    assert result2 is True  # Quorum completed
    
    # Fourth attestation doesn't trigger quorum again
    result3 = tracker.record_attestation("need-1", "prop-A", "v3", k_plan=2)
    assert result3 is False  # Already had quorum
    
    # Fifth attestation also doesn't trigger
    result4 = tracker.record_attestation("need-1", "prop-A", "v4", k_plan=2)
    assert result4 is False


def test_k_plan_calculation():
    """Test K_plan calculation with various active verifier counts"""
    tracker = QuorumTracker()
    
    # With few verifiers, K should be low
    k = tracker.get_k_plan(active_verifiers=5, alpha=0.3, k_target=5)
    assert k == 1  # floor(5 × 0.3) = 1
    
    # With 10 verifiers
    k = tracker.get_k_plan(active_verifiers=10, alpha=0.3, k_target=5)
    assert k == 3  # floor(10 × 0.3) = 3
    
    # With 15 verifiers
    k = tracker.get_k_plan(active_verifiers=15, alpha=0.3, k_target=5)
    assert k == 4  # floor(15 × 0.3) = 4
    
    # Capped by k_target
    k = tracker.get_k_plan(active_verifiers=20, alpha=0.3, k_target=5)
    assert k == 5  # min(5, floor(20 × 0.3)=6) = 5
    
    # With 100 verifiers, still capped
    k = tracker.get_k_plan(active_verifiers=100, alpha=0.3, k_target=5)
    assert k == 5  # min(5, 30) = 5
    
    # Different alpha
    k = tracker.get_k_plan(active_verifiers=10, alpha=0.5, k_target=5)
    assert k == 5  # min(5, floor(10 × 0.5)=5) = 5


def test_separate_proposals():
    """Test that different proposals don't interfere"""
    tracker = QuorumTracker()
    
    # Different proposals for same NEED
    tracker.record_attestation("need-1", "prop-A", "v1", k_plan=2)
    tracker.record_attestation("need-1", "prop-B", "v2", k_plan=2)
    
    # They don't interfere
    assert tracker.check_quorum("need-1", "prop-A") is False
    assert tracker.check_quorum("need-1", "prop-B") is False
    
    # Complete quorum for prop-A
    tracker.record_attestation("need-1", "prop-A", "v3", k_plan=2)
    assert tracker.check_quorum("need-1", "prop-A") is True
    assert tracker.check_quorum("need-1", "prop-B") is False  # Still not reached


def test_different_needs_separate():
    """Test that different NEEDs have separate quorum tracking"""
    tracker = QuorumTracker()
    
    # Attestations for different NEEDs
    tracker.record_attestation("need-1", "prop-A", "v1", k_plan=2)
    tracker.record_attestation("need-2", "prop-X", "v1", k_plan=2)
    
    # Each is separate
    assert tracker.get_attestation_count("need-1", "prop-A") == 1
    assert tracker.get_attestation_count("need-2", "prop-X") == 1
    
    # Complete quorum for need-1
    tracker.record_attestation("need-1", "prop-A", "v2", k_plan=2)
    assert tracker.check_quorum("need-1", "prop-A") is True
    assert tracker.check_quorum("need-2", "prop-X") is False


def test_duplicate_attestation():
    """Test that duplicate attestations from same verifier don't count twice"""
    tracker = QuorumTracker()
    
    # First attestation
    tracker.record_attestation("need-1", "prop-A", "v1", k_plan=3)
    assert tracker.get_attestation_count("need-1", "prop-A") == 1
    
    # Duplicate from same verifier (Sets handle this automatically)
    tracker.record_attestation("need-1", "prop-A", "v1", k_plan=3)
    assert tracker.get_attestation_count("need-1", "prop-A") == 1  # Still 1
    
    # Different verifier
    tracker.record_attestation("need-1", "prop-A", "v2", k_plan=3)
    assert tracker.get_attestation_count("need-1", "prop-A") == 2


def test_quorum_state_class():
    """Test QuorumState class directly"""
    state = QuorumState(
        need_id="need-1",
        proposal_id="prop-A",
        k_plan_required=2
    )
    
    assert state.has_quorum() is False
    
    # First attestation
    completed = state.add_attestation("v1")
    assert completed is False
    assert state.has_quorum() is False
    
    # Second attestation completes quorum
    completed = state.add_attestation("v2")
    assert completed is True
    assert state.has_quorum() is True
    
    # Third attestation doesn't complete quorum (already complete)
    completed = state.add_attestation("v3")
    assert completed is False
    assert state.has_quorum() is True


def test_k_plan_minimum():
    """Test that K_plan has minimum of 1"""
    tracker = QuorumTracker()
    
    # Even with 0 active verifiers, K should be at least 1
    k = tracker.get_k_plan(active_verifiers=0, alpha=0.3, k_target=5)
    assert k == 1
    
    # With 1 verifier
    k = tracker.get_k_plan(active_verifiers=1, alpha=0.3, k_target=5)
    assert k == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
