"""
Feature flag for toggling between Redis and Raft consensus.

Set RAFT_CONSENSUS=true environment variable to use Raft.
"""
import os


def use_raft_consensus() -> bool:
    """
    Check if Raft consensus should be used.
    
    Returns:
        True if RAFT_CONSENSUS env var is 'true', False otherwise
    """
    return os.getenv('RAFT_CONSENSUS', 'false').lower() == 'true'
