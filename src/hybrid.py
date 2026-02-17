"""
Compatibility shim for legacy import path `bus.hybrid`.

Re-exports the hybrid bus implementation from `hybrid_bus.py`.
"""

from hybrid_bus import HybridBus, MessageCache

__all__ = ["HybridBus", "MessageCache"]
