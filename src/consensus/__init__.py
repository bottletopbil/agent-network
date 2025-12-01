# Consensus module for distributed DECIDE operations

# Import from existing consensus.py (Redis-based)
try:
    from ..consensus import ConsensusAdapter
except ImportError:
    # Consensus adapter may not be initialized yet
    ConsensusAdapter = None

__all__ = ["ConsensusAdapter"]
