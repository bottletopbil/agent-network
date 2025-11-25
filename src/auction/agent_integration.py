"""
Agent Integration: Utilities for agents to participate in auctions.
"""

from typing import List, Dict, Any


def estimate_cost(payload: Dict[str, Any], capabilities: List[str]) -> float:
    """
    Estimate cost for a task based on complexity and capabilities.
    
    Args:
        payload: Task payload with complexity and requirements
        capabilities: Agent's capabilities
    
    Returns:
        Estimated cost
    """
    # Base cost
    base_cost = 500.0
    
    # Complexity multiplier (1.0 = normal, 2.0 = double, etc.)
    complexity = payload.get("complexity", 1.0)
    cost = base_cost * complexity
    
    # Capability discount: -50 per relevant capability
    task_requirements = payload.get("requires", [])
    matching_capabilities = len(set(capabilities) & set(task_requirements))
    discount = matching_capabilities * 50
    
    # Apply discount but ensure minimum cost
    cost = max(cost - discount, 100.0)
    
    return cost


def estimate_eta(payload: Dict[str, Any], capabilities: List[str]) -> int:
    """
    Estimate time-to-completion in seconds.
    
    Args:
        payload: Task payload with complexity
        capabilities: Agent's capabilities
    
    Returns:
        Estimated time in seconds
    """
    # Base ETA: 1 hour
    base_eta = 3600
    
    # Complexity multiplier
    complexity = payload.get("complexity", 1.0)
    eta = base_eta * complexity
    
    # Capability speedup: 10% faster per relevant capability
    task_requirements = payload.get("requires", [])
    matching_capabilities = len(set(capabilities) & set(task_requirements))
    speedup_factor = 1.0 - (min(matching_capabilities * 0.1, 0.5))  # Max 50% speedup
    
    eta = eta * speedup_factor
    
    return int(eta)


class BidSubmitter:
    """
    Helper for agents to format and submit bids.
    
    Tracks bid history and manages submission logic.
    """
    
    def __init__(self, agent_id: str, reputation: float = 0.5, capabilities: List[str] = None):
        """
        Initialize bid submitter.
        
        Args:
            agent_id: Agent identifier
            reputation: Agent reputation score (0.0-1.0)
            capabilities: Agent's capabilities
        """
        self.agent_id = agent_id
        self.reputation = reputation
        self.capabilities = capabilities or []
        self.bid_history = []
    
    def create_bid(self, task_payload: Dict[str, Any], proposal_id: str = None) -> Dict[str, Any]:
        """
        Create a bid proposal for a task.
        
        Args:
            task_payload: Task requirements
            proposal_id: Optional proposal ID
        
        Returns:
            Bid proposal dictionary
        """
        import uuid
        
        cost = estimate_cost(task_payload, self.capabilities)
        eta = estimate_eta(task_payload, self.capabilities)
        
        bid = {
            "agent_id": self.agent_id,
            "proposal_id": proposal_id or str(uuid.uuid4()),
            "cost": cost,
            "eta": eta,
            "reputation": self.reputation,
            "capabilities": self.capabilities
        }
        
        return bid
    
    def record_bid(self, task_id: str, bid: Dict[str, Any]):
        """
        Record a submitted bid in history.
        
        Args:
            task_id: Task identifier
            bid: Bid proposal
        """
        import time
        
        self.bid_history.append({
            "task_id": task_id,
            "bid": bid,
            "timestamp": time.time()
        })
    
    def get_bid_history(self, task_id: str = None) -> List[Dict[str, Any]]:
        """
        Get bid history, optionally filtered by task.
        
        Args:
            task_id: Optional task filter
        
        Returns:
            List of bid records
        """
        if task_id:
            return [b for b in self.bid_history if b["task_id"] == task_id]
        return self.bid_history
