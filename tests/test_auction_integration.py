"""
Unit tests for Agent Bidding Integration.

Tests:
- NEED triggers auction
- Planner submits bid
- Best bid wins
- Rejected bid backoff
"""

import sys
import os
import tempfile
from pathlib import Path
import asyncio

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from auction.bidding import AuctionManager, AuctionConfig
from auction.agent_integration import estimate_cost, estimate_eta, BidSubmitter
from plan_store import PlanStore
import handlers.need


class TestAgentIntegrationHelpers:
    """Test agent integration utilities"""

    def test_estimate_cost(self):
        """Verify cost estimation logic"""
        payload = {"complexity": 1.0, "requires": ["planning", "execution"]}
        capabilities = ["planning", "execution"]

        cost = estimate_cost(payload, capabilities)

        # Base 500, complexity 1.0, 2 matching caps = -100 discount
        assert cost == 400.0

    def test_estimate_eta(self):
        """Verify ETA estimation logic"""
        payload = {"complexity": 1.0, "requires": ["planning"]}
        capabilities = ["planning", "execution"]

        eta = estimate_eta(payload, capabilities)

        # Base 3600, complexity 1.0, 1 matching cap = 10% speedup
        assert eta == 3240  # 3600 * 0.9

    def test_bid_submitter(self):
        """Verify BidSubmitter creates bids correctly"""
        submitter = BidSubmitter(
            agent_id="test-agent", reputation=0.9, capabilities=["planning"]
        )

        payload = {"complexity": 1.0, "requires": ["planning"]}
        bid = submitter.create_bid(payload)

        assert bid["agent_id"] == "test-agent"
        assert bid["reputation"] == 0.9
        assert "cost" in bid
        assert "eta" in bid
        assert "proposal_id" in bid


class TestNeedTriggersAuction:
    """Test NEED handler triggers auction"""

    @pytest.mark.asyncio
    async def test_need_triggers_auction(self):
        """Verify NEED handler starts auction"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)

        # Create auction manager with short window for testing
        config = AuctionConfig(bid_window=0.5)  # 0.5 seconds
        manager = AuctionManager(config)

        # Inject dependencies
        handlers.need.plan_store = store
        handlers.need.auction_manager = manager

        # Create NEED envelope
        envelope = {
            "kind": "NEED",
            "thread_id": "test-thread",
            "lamport": 1,
            "sender_pk_b64": "test-sender",
            "payload": {
                "task_type": "generic",
                "budget": 1000,
                "requires": [],
                "produces": [],
            },
        }

        # Handle asynchronously
        # Create task but don't await (auction waits internally)
        task = asyncio.create_task(handlers.need.handle_need(envelope))

        # Give it time to start auction
        await asyncio.sleep(0.1)

        # Should have auction running
        auctions = manager.get_all_auctions()
        assert len(auctions) > 0

        # Wait for handler to complete
        await task

        # Auction should be closed or timed out
        task_id = list(auctions.keys())[0]
        status = manager.get_auction_status(task_id)
        assert status["status"] in ["closed", "timeout"]

    @pytest.mark.asyncio
    async def test_need_without_auction_manager(self):
        """Verify NEED works without auction manager"""
        db_path = Path(tempfile.mktemp())
        store = PlanStore(db_path)

        # No auction manager
        handlers.need.plan_store = store
        handlers.need.auction_manager = None

        envelope = {
            "kind": "NEED",
            "thread_id": "test-thread-no-auction",
            "lamport": 1,
            "sender_pk_b64": "test-sender",
            "payload": {"task_type": "generic"},
        }

        # Should not raise error
        await handlers.need.handle_need(envelope)

        # Task should be created
        ops = store.get_ops_for_thread("test-thread-no-auction")
        assert len(ops) == 1


class TestPlannerSubmitsBid:
    """Test planner agent bidding"""

    def test_planner_can_handle(self):
        """Verify planner can handle appropriate tasks"""
        from agents.planner import PlannerAgent

        agent = PlannerAgent("test-planner", "test-key")

        # Can handle
        assert agent.can_handle({"task_type": "planning"})
        assert agent.can_handle({"task_type": "generic"})
        assert agent.can_handle({"task_type": "worker"})

        # Cannot handle
        assert not agent.can_handle({"task_type": "specialized"})

    def test_planner_creates_bid(self):
        """Verify planner creates bid with cost/ETA"""
        from agents.planner import PlannerAgent

        agent = PlannerAgent("test-planner", "test-key")

        payload = {"task_type": "planning", "complexity": 1.0, "requires": []}
        bid = agent.bid_submitter.create_bid(payload)

        assert "cost" in bid
        assert "eta" in bid
        assert bid["reputation"] == 0.8
        assert "planning" in bid["capabilities"]


class TestBestBidWins:
    """Test winner selection in full flow"""

    @pytest.mark.asyncio
    async def test_best_bid_wins(self):
        """Verify best bid is selected as winner"""
        config = AuctionConfig(bid_window=0.5)
        manager = AuctionManager(config)

        # Start auction
        task_id = "task-best-bid"
        manager.start_auction(task_id, 1000)

        # Submit multiple bids
        manager.accept_bid(
            task_id,
            "agent-expensive",
            {"cost": 900, "eta": 7200, "reputation": 0.6, "capabilities": []},
        )

        manager.accept_bid(
            task_id,
            "agent-best",
            {
                "cost": 400,  # Best cost
                "eta": 3600,  # Good ETA
                "reputation": 0.9,  # Best reputation
                "capabilities": ["planning", "execution"],  # Most capabilities
            },
        )

        manager.accept_bid(
            task_id,
            "agent-slow",
            {
                "cost": 500,
                "eta": 10800,  # Slow
                "reputation": 0.7,
                "capabilities": ["planning"],
            },
        )

        # Wait for window
        await asyncio.sleep(0.6)

        # Close and get winner
        winner = manager.close_auction(task_id)

        assert winner is not None
        assert winner["agent_id"] == "agent-best"


class TestRejectedBidBackoff:
    """Test backoff logic for rejected bids"""

    @pytest.mark.asyncio
    async def test_rejected_bid_backoff(self):
        """Verify backoff applied on rejection"""
        from agents.planner import PlannerAgent

        agent = PlannerAgent("test-planner", "test-key")

        # Get initial backoff
        delay1 = agent.backoff.next()
        assert delay1 >= 0.5  # Base 1.0 ± 0.5 jitter
        assert delay1 <= 1.5

        # Second backoff should be higher
        delay2 = agent.backoff.next()
        assert delay2 > delay1  # Should grow

        # Reset
        agent.backoff.reset()
        delay3 = agent.backoff.next()
        assert delay3 <= 1.5  # Back to initial range
