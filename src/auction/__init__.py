"""
Auction module: Market-style bidding and winner selection.
"""

from .bidding import AuctionManager, AuctionConfig
from .selection import BidEvaluator
from .backoff import calculate_backoff, RandomizedBackoff

__all__ = [
    "AuctionManager",
    "AuctionConfig",
    "BidEvaluator",
    "calculate_backoff",
    "RandomizedBackoff",
]
