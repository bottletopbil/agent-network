"""
Plan management: CRDT store, versioning, and synchronization.
"""

from plan.automerge_store import AutomergePlanStore
from plan.sync_protocol import SyncManager, PeerState
from plan.peer_discovery import PeerDiscovery, PeerInfo
from plan.patching import PlanPatch, PatchValidator
from plan.versioning import PlanVersion, VersionTracker

__all__ = [
    "AutomergePlanStore",
    "SyncManager",
    "PeerState",
    "PeerDiscovery",
    "PeerInfo",
    "PlanPatch",
    "PatchValidator",
    "PlanVersion",
    "VersionTracker",
]
