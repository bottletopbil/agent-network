"""
Unit tests for Consensus Adapter with Redis.

Tests:
- At-most-once DECIDE semantics
- Idempotent retry support
- Conflict detection for different proposals
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from consensus import ConsensusAdapter
import time


class TestAtMostOnceDecide:
    """Test at-most-once DECIDE semantics"""

    def test_at_most_once_decide(self):
        """First DECIDE succeeds, second with different proposal fails"""
        adapter = ConsensusAdapter()
        adapter.redis.flushdb()  # Clean slate

        # First DECIDE succeeds
        d1 = adapter.try_decide(
            need_id="need-123",
            proposal_id="prop-A",
            epoch=1,
            lamport=42,
            k_plan=1,
            decider_id="alice",
            timestamp_ns=time.time_ns(),
        )
        assert d1 is not None
        assert d1.need_id == "need-123"
        assert d1.proposal_id == "prop-A"

        # Second DECIDE for same NEED fails (different proposal)
        d2 = adapter.try_decide(
            need_id="need-123",
            proposal_id="prop-B",  # Different proposal
            epoch=1,
            lamport=43,
            k_plan=1,
            decider_id="bob",
            timestamp_ns=time.time_ns(),
        )
        assert d2 is None


class TestIdempotentRetry:
    """Test idempotent retry support"""

    def test_idempotent_retry(self):
        """Same DECIDE can be retried successfully"""
        adapter = ConsensusAdapter()
        adapter.redis.flushdb()  # Clean slate

        # First DECIDE
        ts = time.time_ns()
        d1 = adapter.try_decide(
            need_id="need-456",
            proposal_id="prop-X",
            epoch=1,
            lamport=42,
            k_plan=1,
            decider_id="alice",
            timestamp_ns=ts,
        )
        assert d1 is not None

        # Idempotent retry succeeds (same proposal and epoch)
        d2 = adapter.try_decide(
            need_id="need-456",
            proposal_id="prop-X",  # Same as d1
            epoch=1,
            lamport=42,
            k_plan=1,
            decider_id="alice",
            timestamp_ns=ts,
        )
        assert d2 is not None
        assert d2.proposal_id == "prop-X"


class TestDifferentProposals:
    """Test conflict detection for different proposals"""

    def test_different_proposals(self):
        """Verify conflicts are rejected"""
        adapter = ConsensusAdapter()
        adapter.redis.flushdb()  # Clean slate

        # First DECIDE with proposal A
        d1 = adapter.try_decide(
            need_id="need-789",
            proposal_id="prop-A",
            epoch=1,
            lamport=10,
            k_plan=2,
            decider_id="alice",
            timestamp_ns=time.time_ns(),
        )
        assert d1 is not None

        # Try different proposal B - should fail
        d2 = adapter.try_decide(
            need_id="need-789",
            proposal_id="prop-B",
            epoch=1,
            lamport=20,
            k_plan=3,
            decider_id="bob",
            timestamp_ns=time.time_ns(),
        )
        assert d2 is None

        # Try different proposal C - should also fail
        d3 = adapter.try_decide(
            need_id="need-789",
            proposal_id="prop-C",
            epoch=1,
            lamport=30,
            k_plan=4,
            decider_id="charlie",
            timestamp_ns=time.time_ns(),
        )
        assert d3 is None

        # Verify original DECIDE is still there
        existing = adapter.get_decide("need-789")
        assert existing is not None
        assert existing.proposal_id == "prop-A"
        assert existing.decider_id == "alice"


class TestGetDecide:
    """Test fetching existing DECIDE records"""

    def test_get_decide_exists(self):
        """Fetch existing DECIDE"""
        adapter = ConsensusAdapter()
        adapter.redis.flushdb()

        # Create DECIDE
        ts = time.time_ns()
        adapter.try_decide(
            need_id="need-get-test",
            proposal_id="prop-123",
            epoch=5,
            lamport=100,
            k_plan=3,
            decider_id="dave",
            timestamp_ns=ts,
        )

        # Fetch it
        record = adapter.get_decide("need-get-test")
        assert record is not None
        assert record.need_id == "need-get-test"
        assert record.proposal_id == "prop-123"
        assert record.epoch == 5
        assert record.lamport == 100
        assert record.k_plan == 3
        assert record.decider_id == "dave"
        assert record.timestamp_ns == ts

    def test_get_decide_nonexistent(self):
        """Fetch nonexistent DECIDE returns None"""
        adapter = ConsensusAdapter()
        adapter.redis.flushdb()

        record = adapter.get_decide("nonexistent-need")
        assert record is None
