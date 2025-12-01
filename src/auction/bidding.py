"""
Auction Bidding: Auction lifecycle and bid management.
"""

import time
import threading
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AuctionConfig:
    """Configuration for auction behavior"""
    bid_window: int = 30  # seconds
    max_rounds: int = 3
    min_bid_increment: float = 0.01  # 1%


class AuctionManager:
    """
    Manage auction lifecycle and bid collection.
    
    Responsibilities:
    - Start auctions for tasks
    - Accept bids from agents
    - Close auctions and select winners
    - Handle timeouts
    """
    
    def __init__(self, config: Optional[AuctionConfig] = None):
        """
        Initialize auction manager.
        
        Args:
            config: Optional auction configuration
        """
        self.config = config or AuctionConfig()
        self._auctions: Dict[str, dict] = {}
        self._lock = threading.Lock()
    
    def start_auction(self, need_id: str, budget: float) -> dict:
        """
        Start an auction for a task.
        
        Args:
            need_id: Task/need identifier
            budget: Maximum budget for task
        
        Returns:
            Auction state dictionary
        """
        with self._lock:
            auction = {
                "need_id": need_id,
                "budget": budget,
                "bids": [],
                "start_time": time.time_ns(),
                "status": "open",
                "round": 1
            }
            self._auctions[need_id] = auction
            return auction.copy()
    
    def accept_bid(self, need_id: str, agent_id: str, proposal: dict) -> bool:
        """
        Accept a bid for an auction.
        
        Args:
            need_id: Auction identifier
            agent_id: Agent submitting bid
            proposal: Bid proposal with cost, eta, etc.
        
        Returns:
            True if bid accepted, False otherwise
        """
        with self._lock:
            # Check auction exists and is open
            if need_id not in self._auctions:
                print(f"[AUCTION] Auction {need_id} not found")
                return False
            
            auction = self._auctions[need_id]
            
            if auction["status"] != "open":
                print(f"[AUCTION] Auction {need_id} is not open (status: {auction['status']})")
                return False
            
            # Check bid window hasn't expired
            current_time = time.time_ns()
            elapsed_seconds = (current_time - auction["start_time"]) / 1_000_000_000
            
            if elapsed_seconds > self.config.bid_window:
                print(f"[AUCTION] Bid window expired for auction {need_id}")
                return False
            
            # Validate bid within budget
            cost = proposal.get("cost", 0)
            if cost > auction["budget"]:
                print(f"[AUCTION] Bid cost {cost} exceeds budget {auction['budget']}")
                return False
            
            # Anti-sniping: Check if bid is in final 5 seconds
            time_until_close = self.config.bid_window - elapsed_seconds
            
            if time_until_close < 5.0:
                # Initialize extensions counter if not present
                if "extensions" not in auction:
                    auction["extensions"] = 0
                
                # Check if we can still extend
                max_extensions = 3
                if auction["extensions"] < max_extensions:
                    # Extend auction by 5 seconds
                    extension_ns = 5 * 1_000_000_000
                    auction["start_time"] -= extension_ns  # Move start back = extend deadline
                    auction["extensions"] += 1
                    
                    logger.info(
                        f"[AUCTION] Bid window extended for {need_id} due to late bid "
                        f"(extension {auction['extensions']}/{max_extensions})"
                    )
                    print(
                        f"[AUCTION] Bid window extended by 5s for {need_id} "
                        f"(extension {auction['extensions']}/{max_extensions})"
                    )
                else:
                    logger.warning(
                        f"[AUCTION] Max extensions ({max_extensions}) reached for {need_id}, "
                        "no further extensions allowed"
                    )
            
            # Create bid record
            bid = {
                "agent_id": agent_id,
                "proposal_id": proposal.get("proposal_id", ""),
                "cost": cost,
                "eta": proposal.get("eta", 0),
                "reputation": proposal.get("reputation", 0.5),
                "capabilities": proposal.get("capabilities", []),
                "timestamp": current_time
            }
            
            auction["bids"].append(bid)
            print(f"[AUCTION] Accepted bid from {agent_id} for {need_id} (cost: {cost}, eta: {proposal.get('eta')})")
            return True
    
    def close_auction(self, need_id: str) -> Optional[dict]:
        """
        Close auction and select winner.
        
        Args:
            need_id: Auction identifier
        
        Returns:
            Winning bid or None if no valid bids
        """
        with self._lock:
            if need_id not in self._auctions:
                print(f"[AUCTION] Auction {need_id} not found")
                return None
            
            auction = self._auctions[need_id]
            auction["status"] = "closed"
            
            if not auction["bids"]:
                print(f"[AUCTION] No bids for auction {need_id}")
                return None
            
            # Import here to avoid circular dependency
            from .selection import BidEvaluator
            
            evaluator = BidEvaluator()
            winner = evaluator.select_winner(auction["bids"], auction["budget"])
            
            if winner:
                print(f"[AUCTION] Winner selected for {need_id}: {winner['agent_id']} (cost: {winner['cost']})")
            else:
                print(f"[AUCTION] No valid winner for {need_id}")
            
            return winner
    
    def timeout_auction(self, need_id: str) -> bool:
        """
        Mark auction as timed out (no bids received).
        
        Args:
            need_id: Auction identifier
        
        Returns:
            True if auction exists, False otherwise
        """
        with self._lock:
            if need_id not in self._auctions:
                return False
            
            self._auctions[need_id]["status"] = "timeout"
            print(f"[AUCTION] Auction {need_id} timed out")
            return True
    
    def get_auction_status(self, need_id: str) -> Optional[dict]:
        """
        Get current auction status.
        
        Args:
            need_id: Auction identifier
        
        Returns:
            Auction state with time remaining and bid count
        """
        with self._lock:
            if need_id not in self._auctions:
                return None
            
            auction = self._auctions[need_id].copy()
            
            # Calculate time remaining
            current_time = time.time_ns()
            elapsed_seconds = (current_time - auction["start_time"]) / 1_000_000_000
            time_remaining = max(0, self.config.bid_window - elapsed_seconds)
            
            auction["time_remaining"] = time_remaining
            auction["bid_count"] = len(auction["bids"])
            
            return auction
    
    def get_all_auctions(self) -> Dict[str, dict]:
        """Get all auctions (for testing/debugging)."""
        with self._lock:
            return {k: v.copy() for k, v in self._auctions.items()}
