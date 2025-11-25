"""
Tests for Raft consensus adapter using etcd.

Tests atomic DECIDE operations, conflict detection, idempotent retries,
and consistent bucket hashing.
"""
import pytest
import time
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from consensus.raft_adapter import RaftConsensusAdapter, DecideRecord


@pytest.fixture
def raft_adapter():
    """Create Raft adapter instance"""
    adapter = RaftConsensusAdapter()
    yield adapter
    adapter.close()


def test_single_decide_succeeds(raft_adapter):
    """Test that a single DECIDE operation succeeds"""
    need_id = f"need-test-{time.time_ns()}"
    
    result = raft_adapter.try_decide(
        need_id=need_id,
        proposal_id="prop-A",
        epoch=1,
        lamport=100,
        k_plan=3,
        decider_id="coordinator-1",
        timestamp_ns=time.time_ns()
    )
    
    assert result is not None
    assert isinstance(result, DecideRecord)
    assert result.need_id == need_id
    assert result.proposal_id == "prop-A"
    assert result.epoch == 1
    assert result.k_plan == 3


def test_conflicting_decide_fails(raft_adapter):
    """Test that conflicting DECIDE operations fail"""
    need_id = f"need-test-{time.time_ns()}"
    
    # First DECIDE
    r1 = raft_adapter.try_decide(
        need_id=need_id,
        proposal_id="prop-A",
        epoch=1,
        lamport=100,
        k_plan=3,
        decider_id="coordinator-1",
        timestamp_ns=time.time_ns()
    )
    assert r1 is not None
    
    # Second DECIDE with different proposal should fail
    r2 = raft_adapter.try_decide(
        need_id=need_id,
        proposal_id="prop-B",  # Different proposal
        epoch=1,
        lamport=101,
        k_plan=3,
        decider_id="coordinator-2",
        timestamp_ns=time.time_ns()
    )
    assert r2 is None  # Should fail due to conflict


def test_idempotent_retry(raft_adapter):
    """Test that retrying same DECIDE succeeds (idempotent)"""
    need_id = f"need-test-{time.time_ns()}"
    ts = time.time_ns()
    
    # First attempt
    r1 = raft_adapter.try_decide(
        need_id=need_id,
        proposal_id="prop-A",
        epoch=1,
        lamport=100,
        k_plan=3,
        decider_id="coordinator-1",
        timestamp_ns=ts
    )
    assert r1 is not None
    
    # Retry with same params (idempotent)
    r2 = raft_adapter.try_decide(
        need_id=need_id,
        proposal_id="prop-A",  # Same proposal
        epoch=1,  # Same epoch
        lamport=100,
        k_plan=3,
        decider_id="coordinator-1",
        timestamp_ns=ts
    )
    assert r2 is not None  # Should succeed (idempotent)


def test_get_decide(raft_adapter):
    """Test retrieving existing DECIDE"""
    need_id = f"need-test-{time.time_ns()}"
    
    # Create DECIDE
    raft_adapter.try_decide(
        need_id=need_id,
        proposal_id="prop-X",
        epoch=2,
        lamport=200,
        k_plan=5,
        decider_id="coordinator-3",
        timestamp_ns=time.time_ns()
    )
    
    # Retrieve it
    result = raft_adapter.get_decide(need_id)
    assert result is not None
    assert result.proposal_id == "prop-X"
    assert result.epoch == 2
    assert result.k_plan == 5


def test_get_decide_nonexistent(raft_adapter):
    """Test retrieving non-existent DECIDE returns None"""
    result = raft_adapter.get_decide("nonexistent-need")
    assert result is None


def test_bucket_hashing(raft_adapter):
    """Test bucket hashing is consistent and distributed"""
    # Test consistency
    bucket1 = raft_adapter.get_bucket_for_need("need-123")
    bucket2 = raft_adapter.get_bucket_for_need("need-123")
    assert bucket1 == bucket2, "Same need should hash to same bucket"
    
    # Test range
    assert 0 <= bucket1 < 256, "Bucket should be in range 0-255"
    
    # Test distribution across many needs
    buckets = [raft_adapter.get_bucket_for_need(f"need-{i}") for i in range(1000)]
    unique_buckets = set(buckets)
    
    # Should spread across many buckets (at least 100 for 1000 needs)
    assert len(unique_buckets) > 100, f"Poor distribution: only {len(unique_buckets)} buckets used"
    
    # Each bucket should be 0-255
    for bucket in buckets:
        assert 0 <= bucket < 256


def test_different_epochs_conflict(raft_adapter):
    """Test that different epochs still conflict (same need)"""
    need_id = f"need-test-{time.time_ns()}"
    
    # DECIDE with epoch 1
    r1 = raft_adapter.try_decide(
        need_id=need_id,
        proposal_id="prop-A",
        epoch=1,
        lamport=100,
        k_plan=3,
        decider_id="coordinator-1",
        timestamp_ns=time.time_ns()
    )
    assert r1 is not None
    
    # Try DECIDE with epoch 2 (should still conflict - at-most-once per need)
    r2 = raft_adapter.try_decide(
        need_id=need_id,
        proposal_id="prop-A",
        epoch=2,  # Different epoch
        lamport=200,
        k_plan=3,
        decider_id="coordinator-1",
        timestamp_ns=time.time_ns()
    )
    assert r2 is None  # Should conflict


def test_concurrent_decides_for_different_needs(raft_adapter):
    """Test that DECIDEs for different needs don't interfere"""
    ts = time.time_ns()
    
    # DECIDE for need-1
    r1 = raft_adapter.try_decide(
        need_id=f"need-1-{ts}",
        proposal_id="prop-A",
        epoch=1,
        lamport=100,
        k_plan=3,
        decider_id="coordinator-1",
        timestamp_ns=ts
    )
    
    # DECIDE for need-2
    r2 = raft_adapter.try_decide(
        need_id=f"need-2-{ts}",
        proposal_id="prop-B",
        epoch=1,
        lamport=101,
        k_plan=3,
        decider_id="coordinator-1",
        timestamp_ns=ts
    )
    
    # Both should succeed
    assert r1 is not None
    assert r2 is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
