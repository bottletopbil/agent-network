"""
Bid Selection: Multi-criteria bid evaluation and winner selection.
"""

from typing import List, Optional


class BidEvaluator:
    """
    Evaluate and rank bids using multiple criteria.
    
    Scoring weights:
    - Cost: 40%
    - ETA: 30%
    - Reputation: 20%
    - Capabilities: 10%
    """
    
    # Scoring weights
    WEIGHT_COST = 0.4
    WEIGHT_ETA = 0.3
    WEIGHT_REPUTATION = 0.2
    WEIGHT_CAPABILITIES = 0.1
    
    def score_bid(self, proposal: dict, budget: float) -> float:
        """
        Score a bid using multiple criteria.
        
        Args:
            proposal: Bid proposal with cost, eta, reputation, capabilities
            budget: Maximum budget for normalization
        
        Returns:
            Composite score (0-100)
        """
        cost = proposal.get("cost", budget)
        eta = proposal.get("eta", 0)
        reputation = proposal.get("reputation", 0.5)
        capabilities = proposal.get("capabilities", [])
        
        # Normalize cost (cheaper is better)
        # Score of 1.0 means free, 0.0 means at budget
        cost_score = 1.0 - min(cost / budget, 1.0) if budget > 0 else 0.0
        
        # Normalize ETA (faster is better)
        # Assume max ETA of 1 week (604800 seconds) for normalization
        max_eta = 604800
        eta_score = 1.0 - min(eta / max_eta, 1.0)
        
        # Reputation already 0-1
        rep_score = min(max(reputation, 0.0), 1.0)
        
        # Capabilities (more is better)
        # Assume max 10 capabilities for normalization
        max_capabilities = 10
        cap_score = min(len(capabilities) / max_capabilities, 1.0)
        
        # Composite score
        composite = (
            cost_score * self.WEIGHT_COST +
            eta_score * self.WEIGHT_ETA +
            rep_score * self.WEIGHT_REPUTATION +
            cap_score * self.WEIGHT_CAPABILITIES
        )
        
        # Scale to 0-100
        return composite * 100
    
    def select_winner(self, bids: List[dict], budget: float) -> Optional[dict]:
        """
        Select winning bid from list.
        
        Args:
            bids: List of bid proposals
            budget: Maximum budget
        
        Returns:
            Winning bid or None if no valid bids
        """
        if not bids:
            return None
        
        # Score all bids
        scored_bids = []
        for bid in bids:
            score = self.score_bid(bid, budget)
            scored_bids.append((score, bid))
        
        # Sort by score (descending)
        scored_bids.sort(key=lambda x: x[0], reverse=True)
        
        # Get highest score
        max_score = scored_bids[0][0]
        
        # Find all bids with max score (ties)
        tied_bids = [bid for score, bid in scored_bids if score == max_score]
        
        # Handle ties
        if len(tied_bids) > 1:
            return self.handle_ties(tied_bids)
        
        return tied_bids[0]
    
    def handle_ties(self, bids: List[dict]) -> dict:
        """
        Break ties using reputation and timestamp.
        
        Args:
            bids: List of tied bids
        
        Returns:
            Winning bid
        """
        # First tiebreaker: highest reputation
        bids_by_rep = sorted(bids, key=lambda b: b.get("reputation", 0), reverse=True)
        max_rep = bids_by_rep[0].get("reputation", 0)
        
        # Filter to highest reputation
        top_rep_bids = [b for b in bids_by_rep if b.get("reputation", 0) == max_rep]
        
        # Second tiebreaker: earliest timestamp
        if len(top_rep_bids) > 1:
            return min(top_rep_bids, key=lambda b: b.get("timestamp", float('inf')))
        
        return top_rep_bids[0]
