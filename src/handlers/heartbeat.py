"""
HEARTBEAT Handler: Process heartbeat messages for lease management.
"""

import uuid
from plan_store import PlanStore, PlanOp, OpType
from verbs import DISPATCHER
import time

plan_store: PlanStore = None  # Injected at startup
lease_manager = None  # Injected: LeaseManager instance
heartbeat_protocol = None  # Injected: HeartbeatProtocol instance

async def handle_heartbeat(envelope: dict):
    """
    Process HEARTBEAT envelope:
    1. Validate lease exists
    2. Validate worker_id matches lease
    3. Update last_heartbeat via LeaseManager
    4. Notify HeartbeatProtocol
    5. Record progress
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    sender = envelope["sender_pk_b64"]
    
    # Extract heartbeat details
    lease_id = payload.get("lease_id")
    worker_id = payload.get("worker_id")
    progress = payload.get("progress")
    
    # Validation
    if not lease_id:
        print(f"[HEARTBEAT] ERROR: No lease_id in payload")
        return
    
    if not worker_id:
        print(f"[HEARTBEAT] ERROR: No worker_id in payload")
        return
    
    # Validate lease exists
    if lease_manager is None:
        print(f"[HEARTBEAT] WARNING: LeaseManager not available, skipping validation")
    else:
        lease = lease_manager.get_lease(lease_id)
        if lease is None:
            print(f"[HEARTBEAT] ERROR: Lease {lease_id} not found")
            return
        
        # Validate worker_id matches
        if lease.worker_id != worker_id:
            print(f"[HEARTBEAT] ERROR: Worker mismatch for lease {lease_id}: expected {lease.worker_id}, got {worker_id}")
            return
        
        # Update heartbeat timestamp
        success = lease_manager.heartbeat(lease_id)
        if not success:
            print(f"[HEARTBEAT] ERROR: Failed to update heartbeat for lease {lease_id}")
            return
    
    # Notify heartbeat protocol
    if heartbeat_protocol is not None:
        heartbeat_protocol.receive_heartbeat(lease_id)
    
    # Validate progress if provided
    if progress is not None:
        if not (0 <= progress <= 100):
            print(f"[HEARTBEAT] WARNING: Invalid progress {progress}, must be 0-100")
            progress = None
    
    # Record heartbeat as ANNOTATE op
    op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=sender,
        op_type=OpType.ANNOTATE,
        task_id=lease.task_id if lease_manager and lease_manager.get_lease(lease_id) else "unknown",
        payload={
            "annotation_type": "heartbeat",
            "lease_id": lease_id,
            "worker_id": worker_id,
            "progress": progress,
            "heartbeat_at": time.time_ns()
        },
        timestamp_ns=time.time_ns()
    )
    
    await plan_store.append_op(op)
    print(f"[HEARTBEAT] Received from {worker_id[:8]}... for lease {lease_id} (progress: {progress}%)")

# Register with dispatcher
DISPATCHER.register("HEARTBEAT", handle_heartbeat)
