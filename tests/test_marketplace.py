"""
Tests for Task Marketplace.

Verifies task listing, bid tracking, price analytics, and agent ratings.
"""

import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from marketplace.market import TaskMarketplace, TaskStatus, PriceTrend


class TestTaskPosting:
    """Test task posting functionality"""
    
    @pytest.fixture
    def marketplace(self):
        """Create temporary marketplace for testing"""
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        db_file.close()
        
        market = TaskMarketplace(Path(db_file.name))
        
        yield market
        
        os.unlink(db_file.name)
    
    def test_post_task_basic(self, marketplace):
        """Test posting a basic task"""
        task_id = marketplace.post_task(
            task_id="task1",
            description="Analyze code for bugs",
            capabilities_required=["code_analysis", "bug_detection"],
            budget=100.0,
            poster_id="user1"
        )
        
        assert task_id == "task1"
    
    def test_post_task_with_deadline(self, marketplace):
        """Test posting task with deadline"""
        import time
        deadline = time.time() + 3600  # 1 hour from now
        
        task_id = marketplace.post_task(
            task_id="task2",
            description="Test task",
            capabilities_required=["test"],
            budget=50.0,
            poster_id="user1",
            deadline=deadline
        )
        
        tasks = marketplace.list_available_tasks()
        assert len(tasks) == 1
        assert tasks[0]["deadline"] == deadline


class TestTaskListing:
    """Test task listing functionality"""
    
    @pytest.fixture
    def marketplace_with_tasks(self):
        """Create marketplace with sample tasks"""
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        db_file.close()
        
        market = TaskMarketplace(Path(db_file.name))
        
        # Post multiple tasks
        market.post_task(
            "task1",
            "Code analysis",
            ["code_analysis", "python"],
            100.0,
            "user1"
        )
        
        market.post_task(
            "task2",
            "Security audit",
            ["security", "audit"],
            150.0,
            "user2"
        )
        
        market.post_task(
            "task3",
            "Code review",
            ["code_analysis", "review"],
            75.0,
            "user1"
        )
        
        yield market
        
        os.unlink(db_file.name)
    
    def test_list_all_tasks(self, marketplace_with_tasks):
        """Test listing all available tasks"""
        tasks = marketplace_with_tasks.list_available_tasks()
        
        assert len(tasks) == 3
    
    def test_list_tasks_by_capability(self, marketplace_with_tasks):
        """Test filtering tasks by capability"""
        tasks = marketplace_with_tasks.list_available_tasks(
            capabilities=["code_analysis"]
        )
        
        assert len(tasks) == 2
        task_ids = [t["task_id"] for t in tasks]
        assert "task1" in task_ids
        assert "task3" in task_ids
    
    def test_list_tasks_by_budget(self, marketplace_with_tasks):
        """Test filtering tasks by maximum budget"""
        tasks = marketplace_with_tasks.list_available_tasks(max_budget=100.0)
        
        assert len(tasks) == 2
        for task in tasks:
            assert task["budget"] <= 100.0


class TestBidding:
    """Test bidding functionality"""
    
    @pytest.fixture
    def marketplace_with_task(self):
        """Create marketplace with a task"""
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        db_file.close()
        
        market = TaskMarketplace(Path(db_file.name))
        
        market.post_task(
            "task1",
            "Test task",
            ["test"],
            100.0,
            "user1"
        )
        
        yield market
        
        os.unlink(db_file.name)
    
    def test_submit_bid(self, marketplace_with_task):
        """Test submitting a bid"""
        bid_id = marketplace_with_task.submit_bid(
            bid_id="bid1",
            task_id="task1",
            agent_id="agent1",
            amount=80.0,
            estimated_time=2.0,
            message="I can complete this quickly"
        )
        
        assert bid_id == "bid1"
    
    def test_get_bid_history(self, marketplace_with_task):
        """Test getting bid history for a task"""
        # Submit multiple bids
        marketplace_with_task.submit_bid(
            "bid1", "task1", "agent1", 80.0, 2.0, "Bid 1"
        )
        marketplace_with_task.submit_bid(
            "bid2", "task1", "agent2", 70.0, 3.0, "Bid 2"
        )
        marketplace_with_task.submit_bid(
            "bid3", "task1", "agent3", 90.0, 1.5, "Bid 3"
        )
        
        bids = marketplace_with_task.get_bid_history("task1")
        
        assert len(bids) == 3
        # Should be ordered by amount (lowest first)
        assert bids[0]["amount"] == 70.0
        assert bids[1]["amount"] == 80.0
        assert bids[2]["amount"] == 90.0
    
    def test_accept_bid(self, marketplace_with_task):
        """Test accepting a bid"""
        # Submit bids
        marketplace_with_task.submit_bid(
            "bid1", "task1", "agent1", 80.0, 2.0, "Bid 1"
        )
        marketplace_with_task.submit_bid(
            "bid2", "task1", "agent2", 70.0, 3.0, "Bid 2"
        )
        
        # Accept first bid
        result = marketplace_with_task.accept_bid("bid1")
        
        assert result is True
        
        # Check bid statuses
        bids = marketplace_with_task.get_bid_history("task1")
        bid1 = [b for b in bids if b["bid_id"] == "bid1"][0]
        bid2 = [b for b in bids if b["bid_id"] == "bid2"][0]
        
        assert bid1["status"] == "accepted"
        assert bid2["status"] == "rejected"


class TestPriceTrends:
    """Test price trend analytics"""
    
    @pytest.fixture
    def marketplace_with_price_history(self):
        """Create marketplace with price history"""
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        db_file.close()
        
        market = TaskMarketplace(Path(db_file.name))
        
        # Post tasks to create price history
        market.post_task("task1", "Test 1", ["code_analysis"], 100.0, "user1")
        market.post_task("task2", "Test 2", ["code_analysis"], 120.0, "user1")
        market.post_task("task3", "Test 3", ["code_analysis"], 90.0, "user1")
        market.post_task("task4", "Test 4", ["security"], 150.0, "user1")
        market.post_task("task5", "Test 5", ["security"], 140.0, "user1")
        
        yield market
        
        os.unlink(db_file.name)
    
    def test_track_price_trends(self, marketplace_with_price_history):
        """Test tracking price trends"""
        trends = marketplace_with_price_history.track_price_trends()
        
        assert len(trends) == 2  # code_analysis and security
        
        # Find code_analysis trend
        code_trend = [t for t in trends if t.capability == "code_analysis"][0]
        
        assert code_trend.total_tasks == 3
        assert code_trend.avg_price == (100 + 120 + 90) / 3
        assert code_trend.min_price == 90.0
        assert code_trend.max_price == 120.0
    
    def test_track_specific_capability_trend(self, marketplace_with_price_history):
        """Test tracking trend for specific capability"""
        trends = marketplace_with_price_history.track_price_trends(
            capability="security"
        )
        
        assert len(trends) == 1
        assert trends[0].capability == "security"
        assert trends[0].total_tasks == 2


class TestAgentRatings:
    """Test agent rating functionality"""
    
    @pytest.fixture
    def marketplace(self):
        """Create temporary marketplace"""
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        db_file.close()
        
        market = TaskMarketplace(Path(db_file.name))
        
        yield market
        
        os.unlink(db_file.name)
    
    def test_rate_agent(self, marketplace):
        """Test rating an agent"""
        rating_id = marketplace.rate_agent(
            agent_id="agent1",
            rater_id="user1",
            rating=4.5,
            comment="Great work!"
        )
        
        assert rating_id is not None
        assert rating_id > 0
    
    def test_rate_agent_invalid_rating(self, marketplace):
        """Test that invalid ratings are rejected"""
        with pytest.raises(ValueError, match="between 0.0 and 5.0"):
            marketplace.rate_agent("agent1", "user1", 6.0)
        
        with pytest.raises(ValueError, match="between 0.0 and 5.0"):
            marketplace.rate_agent("agent1", "user1", -1.0)
    
    def test_get_agent_ratings(self, marketplace):
        """Test getting agent rating summary"""
        # Submit multiple ratings
        marketplace.rate_agent("agent1", "user1", 4.5, "Good")
        marketplace.rate_agent("agent1", "user2", 5.0, "Excellent")
        marketplace.rate_agent("agent1", "user3", 4.0, "Nice")
        
        ratings = marketplace.get_agent_ratings("agent1")
        
        assert ratings["agent_id"] == "agent1"
        assert ratings["total_ratings"] == 3
        assert ratings["avg_rating"] == (4.5 + 5.0 + 4.0) / 3
        assert ratings["min_rating"] == 4.0
        assert ratings["max_rating"] == 5.0
        assert len(ratings["recent_ratings"]) == 3
    
    def test_get_agent_ratings_no_ratings(self, marketplace):
        """Test getting ratings for agent with no ratings"""
        ratings = marketplace.get_agent_ratings("agent_new")
        
        assert ratings["total_ratings"] == 0
        assert ratings["avg_rating"] == 0.0
        assert len(ratings["recent_ratings"]) == 0
    
    def test_get_leaderboard(self, marketplace):
        """Test getting agent leaderboard"""
        # Rate multiple agents (need at least 3 ratings each for leaderboard)
        for i in range(1, 4):
            marketplace.rate_agent("agent1", f"user{i}", 4.5)
        
        for i in range(1, 4):
            marketplace.rate_agent("agent2", f"user{i}", 3.5)
        
        for i in range(1, 4):
            marketplace.rate_agent("agent3", f"user{i}", 5.0)
        
        leaderboard = marketplace.get_leaderboard(limit=10)
        
        assert len(leaderboard) == 3
        # Should be ordered by rating
        assert leaderboard[0]["agent_id"] == "agent3"  # 5.0
        assert leaderboard[0]["rank"] == 1
        assert leaderboard[1]["agent_id"] == "agent1"  # 4.5
        assert leaderboard[2]["agent_id"] == "agent2"  # 3.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
