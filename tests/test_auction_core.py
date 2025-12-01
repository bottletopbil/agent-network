"""
Unit tests for Auction Core System.

Tests:
- Auction lifecycle (start, bid, close)
- Bid evaluation and scoring
- Winner selection and tie-breaking
- Timeout handling
- Exponential backoff
"""

import sys
import os
import time

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from auction.bidding import AuctionManager, AuctionConfig
from auction.selection import BidEvaluator
from auction.backoff import calculate_backoff, RandomizedBackoff


class TestAuctionLifecycle:
    """Test auction lifecycle management"""

    def test_start_auction(self):
        """Verify auction can be started"""
        manager = AuctionManager()

        auction = manager.start_auction("need-123", 1000)

        assert auction["need_id"] == "need-123"
        assert auction["budget"] == 1000
        assert auction["status"] == "open"
        assert auction["round"] == 1
        assert len(auction["bids"]) == 0

    def test_accept_bid(self):
        """Verify bids can be accepted"""
        manager = AuctionManager()
        manager.start_auction("need-456", 1000)

        proposal = {
            "proposal_id": "prop-1",
            "cost": 500,
            "eta": 3600,
            "reputation": 0.8,
            "capabilities": ["coding", "testing"],
        }

        success = manager.accept_bid("need-456", "agent-1", proposal)

        assert success is True

        # Verify bid recorded
        status = manager.get_auction_status("need-456")
        assert status["bid_count"] == 1
        assert len(status["bids"]) == 1
        assert status["bids"][0]["agent_id"] == "agent-1"
        assert status["bids"][0]["cost"] == 500

    def test_close_auction_with_winner(self):
        """Verify auction closes and selects winner"""
        manager = AuctionManager()
        manager.start_auction("need-789", 1000)

        # Add multiple bids
        manager.accept_bid(
            "need-789",
            "agent-1",
            {"cost": 600, "eta": 7200, "reputation": 0.7, "capabilities": ["coding"]},
        )

        manager.accept_bid(
            "need-789",
            "agent-2",
            {
                "cost": 400,  # Cheaper, should win
                "eta": 3600,
                "reputation": 0.8,
                "capabilities": ["coding", "testing"],
            },
        )

        winner = manager.close_auction("need-789")

        assert winner is not None
        assert winner["agent_id"] == "agent-2"
        assert winner["cost"] == 400

        # Verify status changed
        status = manager.get_auction_status("need-789")
        assert status["status"] == "closed"

    def test_bid_over_budget_rejected(self):
        """Verify bids over budget are rejected"""
        manager = AuctionManager()
        manager.start_auction("need-budget", 1000)

        proposal = {"cost": 1500, "eta": 3600, "reputation": 0.8}  # Over budget

        success = manager.accept_bid("need-budget", "agent-1", proposal)

        assert success is False

        status = manager.get_auction_status("need-budget")
        assert status["bid_count"] == 0

    def test_bid_to_closed_auction_rejected(self):
        """Verify bids to closed auctions are rejected"""
        manager = AuctionManager()
        manager.start_auction("need-closed", 1000)

        # Close auction
        manager.close_auction("need-closed")

        # Try to bid
        success = manager.accept_bid(
            "need-closed", "agent-1", {"cost": 500, "eta": 3600}
        )

        assert success is False


class TestBidEvaluation:
    """Test bid scoring and evaluation"""

    def test_score_bid(self):
        """Verify bid scoring calculation"""
        evaluator = BidEvaluator()

        proposal = {
            "cost": 500,  # 50% of budget
            "eta": 3600,  # 1 hour
            "reputation": 0.8,
            "capabilities": ["coding", "testing", "review"],
        }

        score = evaluator.score_bid(proposal, budget=1000)

        # Score should be between 0 and 100
        assert 0 <= score <= 100

        # With good cost, ETA, reputation, should score reasonably high
        assert score > 40  # At least moderate score

    def test_cheaper_bid_scores_higher(self):
        """Verify cheaper bids score higher (all else equal)"""
        evaluator = BidEvaluator()

        cheap_bid = {
            "cost": 300,
            "eta": 3600,
            "reputation": 0.7,
            "capabilities": ["coding"],
        }

        expensive_bid = {
            "cost": 800,
            "eta": 3600,
            "reputation": 0.7,
            "capabilities": ["coding"],
        }

        cheap_score = evaluator.score_bid(cheap_bid, 1000)
        expensive_score = evaluator.score_bid(expensive_bid, 1000)

        assert cheap_score > expensive_score

    def test_faster_bid_scores_higher(self):
        """Verify faster ETA scores higher (all else equal)"""
        evaluator = BidEvaluator()

        fast_bid = {
            "cost": 500,
            "eta": 1800,  # 30 minutes
            "reputation": 0.7,
            "capabilities": ["coding"],
        }

        slow_bid = {
            "cost": 500,
            "eta": 86400,  # 1 day
            "reputation": 0.7,
            "capabilities": ["coding"],
        }

        fast_score = evaluator.score_bid(fast_bid, 1000)
        slow_score = evaluator.score_bid(slow_bid, 1000)

        assert fast_score > slow_score


class TestWinnerSelection:
    """Test winner selection logic"""

    def test_select_winner_highest_score(self):
        """Verify highest scoring bid wins"""
        evaluator = BidEvaluator()

        bids = [
            {
                "agent_id": "agent-1",
                "cost": 600,
                "eta": 7200,
                "reputation": 0.6,
                "capabilities": ["coding"],
            },
            {
                "agent_id": "agent-2",
                "cost": 400,  # Better cost
                "eta": 3600,  # Better ETA
                "reputation": 0.8,  # Better reputation
                "capabilities": ["coding", "testing"],  # More capabilities
            },
            {
                "agent_id": "agent-3",
                "cost": 500,
                "eta": 5400,
                "reputation": 0.7,
                "capabilities": ["coding"],
            },
        ]

        winner = evaluator.select_winner(bids, budget=1000)

        assert winner is not None
        assert winner["agent_id"] == "agent-2"  # Best overall

    def test_select_winner_empty_bids(self):
        """Verify None returned for empty bids"""
        evaluator = BidEvaluator()

        winner = evaluator.select_winner([], budget=1000)

        assert winner is None

    def test_tie_breaking_by_reputation(self):
        """Verify reputation breaks ties"""
        evaluator = BidEvaluator()

        bids = [
            {
                "agent_id": "agent-1",
                "cost": 500,
                "eta": 3600,
                "reputation": 0.7,
                "capabilities": ["coding"],
                "timestamp": 1000,
            },
            {
                "agent_id": "agent-2",
                "cost": 500,
                "eta": 3600,
                "reputation": 0.9,  # Higher reputation
                "capabilities": ["coding"],
                "timestamp": 2000,
            },
        ]

        winner = evaluator.select_winner(bids, budget=1000)

        assert winner["agent_id"] == "agent-2"

    def test_tie_breaking_by_timestamp(self):
        """Verify timestamp breaks ties when reputation equal"""
        evaluator = BidEvaluator()

        bids = [
            {
                "agent_id": "agent-1",
                "cost": 500,
                "eta": 3600,
                "reputation": 0.8,
                "capabilities": ["coding"],
                "timestamp": 2000,
            },
            {
                "agent_id": "agent-2",
                "cost": 500,
                "eta": 3600,
                "reputation": 0.8,
                "capabilities": ["coding"],
                "timestamp": 1000,  # Earlier timestamp
            },
        ]

        winner = evaluator.select_winner(bids, budget=1000)

        assert winner["agent_id"] == "agent-2"


class TestTimeoutHandling:
    """Test auction timeout functionality"""

    def test_timeout_auction(self):
        """Verify auction can be timed out"""
        manager = AuctionManager()
        manager.start_auction("need-timeout", 1000)

        success = manager.timeout_auction("need-timeout")

        assert success is True

        status = manager.get_auction_status("need-timeout")
        assert status["status"] == "timeout"

    def test_timeout_nonexistent_auction(self):
        """Verify timeout returns False for nonexistent auction"""
        manager = AuctionManager()

        success = manager.timeout_auction("nonexistent")

        assert success is False

    def test_close_auction_no_bids(self):
        """Verify close returns None when no bids"""
        manager = AuctionManager()
        manager.start_auction("need-nobids", 1000)

        winner = manager.close_auction("need-nobids")

        assert winner is None

        status = manager.get_auction_status("need-nobids")
        assert status["status"] == "closed"


class TestRandomizedBackoff:
    """Test exponential backoff logic"""

    def test_backoff_grows_exponentially(self):
        """Verify backoff delays grow exponentially"""
        delays = [calculate_backoff(i, base=1.0, jitter=0) for i in range(5)]

        # Without jitter, should be: 1, 2, 4, 8, 16
        assert delays[0] == 1.0
        assert delays[1] == 2.0
        assert delays[2] == 4.0
        assert delays[3] == 8.0
        assert delays[4] == 16.0

    def test_backoff_caps_at_max(self):
        """Verify backoff respects maximum delay"""
        delay = calculate_backoff(10, base=1.0, max_delay=60.0, jitter=0)

        # 2^10 = 1024, but should cap at 60
        assert delay == 60.0

    def test_backoff_with_jitter(self):
        """Verify jitter is applied"""
        # Run multiple times to check variance
        delays = [calculate_backoff(3, base=1.0, jitter=0.5) for _ in range(10)]

        # All should be around 8.0 but vary due to jitter
        for delay in delays:
            assert 7.5 <= delay <= 8.5  # 8 ± 0.5

    def test_randomized_backoff_class(self):
        """Verify RandomizedBackoff stateful behavior"""
        backoff = RandomizedBackoff(base=1.0, max_delay=60.0, jitter=0)

        # First call
        delay1 = backoff.next()
        assert delay1 == 1.0
        assert backoff.current_attempt() == 1

        # Second call
        delay2 = backoff.next()
        assert delay2 == 2.0
        assert backoff.current_attempt() == 2

        # Third call
        delay3 = backoff.next()
        assert delay3 == 4.0
        assert backoff.current_attempt() == 3

    def test_randomized_backoff_reset(self):
        """Verify reset functionality"""
        backoff = RandomizedBackoff(base=1.0, jitter=0)

        # Advance a few times
        backoff.next()
        backoff.next()
        backoff.next()
        assert backoff.current_attempt() == 3

        # Reset
        backoff.reset()
        assert backoff.current_attempt() == 0

        # Next should be back to initial
        delay = backoff.next()
        assert delay == 1.0


class TestAuctionStatus:
    """Test auction status queries"""

    def test_get_auction_status(self):
        """Verify status includes time remaining"""
        config = AuctionConfig(bid_window=10)  # 10 second window
        manager = AuctionManager(config)

        manager.start_auction("need-status", 1000)

        # Immediately check status
        status = manager.get_auction_status("need-status")

        assert status is not None
        assert "time_remaining" in status
        assert status["time_remaining"] > 0
        assert status["time_remaining"] <= 10
        assert status["bid_count"] == 0

    def test_auction_status_nonexistent(self):
        """Verify None for nonexistent auction"""
        manager = AuctionManager()

        status = manager.get_auction_status("nonexistent")

        assert status is None
