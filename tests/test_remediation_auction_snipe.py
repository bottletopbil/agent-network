"""
Test for auction anti-sniping (ECON-007).

Validates that bid window extends when bids arrive in final 5 seconds.
"""

import sys
from pathlib import Path
import pytest
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_late_bid_extends_auction_window():
    """
    Test that bid in final 5 seconds extends auction window by 5 seconds.
    """
    from auction.bidding import AuctionManager
    
    manager = AuctionManager()
    
    # Start auction with 10 second window
    task_id = "task_snipe_test"
    auction = manager.start_auction(
        task_id=task_id,
        min_bid=100,
        duration_seconds=10
    )
    
    original_deadline = auction["deadline"]
    
    # Wait until last 3 seconds (simulating late bid)
    time.sleep(7)
    
    # Submit bid in final 3 seconds
    result = manager.accept_bid(
        task_id=task_id,
        agent_id="sniper",
        bid_amount=150
    )
    
    assert result["accepted"], "Bid should be accepted"
    
    # Check that deadline was extended
    updated_auction = manager.get_auction(task_id)
    new_deadline = updated_auction["deadline"]
    
    # Should extend by 5 seconds
    assert new_deadline > original_deadline, "Deadline should be extended"
    assert new_deadline - original_deadline >= 4, "Should extend by approximately 5 seconds"


def test_multiple_late_bids_extend_multiple_times():
    """
    Test that multiple late bids can extend window multiple times.
    """
    from auction.bidding import AuctionManager
    
    manager = AuctionManager()
    
    task_id = "task_multi_extend"
    auction = manager.start_auction(
        task_id=task_id,
        min_bid=100,
        duration_seconds=8
    )
    
    original_deadline = auction["deadline"]
    
    # Wait 6 seconds (2s remaining)
    time.sleep(6)
    
    # First late bid - should extend
    manager.accept_bid(task_id, "bidder1", 120)
    deadline_after_first = manager.get_auction(task_id)["deadline"]
    
    assert deadline_after_first > original_deadline
    
    # Wait 5 more seconds
    time.sleep(5)
    
    # Second late bid - should extend again
    manager.accept_bid(task_id, "bidder2", 140)
    deadline_after_second = manager.get_auction(task_id)["deadline"]
    
    assert deadline_after_second > deadline_after_first


def test_max_extensions_limit():
    """
    Test that auction cannot be extended indefinitely.
    """
    from auction.bidding import AuctionManager
    
    manager = AuctionManager()
    
    task_id = "task_max_extend"
    auction = manager.start_auction(
        task_id=task_id,
        min_bid=100,
        duration_seconds=6
    )
    
    # Try to trigger many extensions
    extensions_count = 0
    
    for i in range(5):  # Try 5 times
        time.sleep(4)  # Wait near end
        result = manager.accept_bid(task_id, f"bidder{i}", 100 + (i * 10))
        
        if result.get("extended"):
            extensions_count += 1
    
    # Should have max_extensions limit (e.g., 3)
    assert extensions_count <= 3, "Should not extend more than max_extensions"


def test_early_bid_does_not_extend():
    """
    Test that bids early in auction don't trigger extension.
    """
    from auction.bidding import AuctionManager
    
    manager = AuctionManager()
    
    task_id = "task_early_bid"
    auction = manager.start_auction(
        task_id=task_id,
        min_bid=100,
        duration_seconds=20
    )
    
    original_deadline = auction["deadline"]
    
    # Submit bid early (plenty of time left)
    time.sleep(2)
    
    manager.accept_bid(task_id, "early_bidder", 150)
    
    updated_auction = manager.get_auction(task_id)
    new_deadline = updated_auction["deadline"]
    
    # Deadline should not change significantly (maybe small drift)
    assert abs(new_deadline - original_deadline) < 2, "Early bid should not extend deadline"


def test_extension_logged():
    """
    Test that bid window extension is logged.
    """
    from auction.bidding import AuctionManager
    from unittest.mock import patch
    
    manager = AuctionManager()
    
    task_id = "task_log_test"
    manager.start_auction(
        task_id=task_id,
        min_bid=100,
        duration_seconds=8
    )
    
    time.sleep(6)  # Wait until final seconds
    
    with patch('auction.bidding.logger') as mock_logger:
        manager.accept_bid(task_id, "late_bidder", 150)
        
        # Check that extension was logged
        # Should have info or warning about extension
        assert mock_logger.info.called or mock_logger.warning.called
