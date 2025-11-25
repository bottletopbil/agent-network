"""
RECONCILE Handler: Process partition heal and epoch advancement.

Handles RECONCILE messages that signal network partition recovery.
Advances epoch and marks orphaned branches based on conflict resolution.
"""
import uuid
from plan_store import PlanStore
from verbs import DISPATCHER
from consensus.epochs import epoch_manager
from consensus.merge import MergeHandler
import time


plan_store: PlanStore = None  # Injected at startup


async def handle_reconcile(envelope: dict):
    """
    Process RECONCILE envelope after partition heal.
    
    Steps:
    1. Extract partition reconciliation details
    2. Advance epoch to fence out stale decisions
    3. Mark orphaned branches from losing partitions
    4. Log reconciliation summary
    
    Args:
        envelope: RECONCILE message envelope with:
            - thread_id: Thread being reconciled
            - summary: Reconciliation summary
            - orphaned_branches: List of DECIDEs that lost
    """
    thread_id = envelope.get("thread_id")
    payload = envelope.get("payload", {})
    
    summary = payload.get("summary", {})
    orphaned_branches = payload.get("orphaned_branches", [])
    
    # Advance epoch to fence out old decisions
    reason = payload.get("reason", "partition_heal")
    new_epoch = epoch_manager.advance_epoch(reason=reason)
    
    # Log reconciliation
    print(f"[RECONCILE] Thread {thread_id}, advanced to epoch {new_epoch}")
    print(f"[RECONCILE] Orphaning {len(orphaned_branches)} branches")
    
    # Mark orphaned branches in plan store
    if plan_store is None:
        print(f"[RECONCILE] WARNING: Plan store not available, cannot mark orphaned")
        return
    
    merge_handler = MergeHandler()
    
    for branch in orphaned_branches:
        merge_handler.mark_orphaned(
            decide=branch,
            winning_epoch=new_epoch,
            plan_store=plan_store
        )
    
    # Log summary details if available
    if summary:
        print(f"[RECONCILE] Summary: {summary}")


# Register with dispatcher
DISPATCHER.register("RECONCILE", handle_reconcile)
