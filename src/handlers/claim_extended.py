"""
CLAIM_EXTENDED Handler: extended claim with lease management and heartbeat tracking.
"""

import uuid
from plan_store import PlanStore, PlanOp, OpType, TaskState
from verbs import DISPATCHER
import time

plan_store: PlanStore = None  # Injected at startup

# Configuration
MIN_LEASE_TTL = 60  # Minimum lease time in seconds

# Lease registry (in-memory for now, could be persisted)
_lease_registry = {}  # {lease_id: lease_record}

async def handle_claim_extended(envelope: dict):
    """
    Process CLAIM_EXTENDED envelope:
    1. Validate lease_ttl meets minimum requirement
    2. Create lease record with heartbeat tracking
    3. Update task state to CLAIMED
    4. Record claim with cost and ETA
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    sender = envelope["sender_pk_b64"]
    
    # Extract claim details
    task_id = payload.get("task_id")
    worker_id = payload.get("worker_id", sender)
    lease_ttl = payload.get("lease_ttl")
    cost = payload.get("cost")
    eta = payload.get("eta")
    heartbeat_interval = payload.get("heartbeat_interval", 30)
    
    # Validation
    if not task_id:
        print(f"[CLAIM_EXTENDED] ERROR: No task_id in payload")
        return
    
    if not lease_ttl:
        print(f"[CLAIM_EXTENDED] ERROR: No lease_ttl in payload")
        return
    
    # Validate lease_ttl meets minimum
    if lease_ttl < MIN_LEASE_TTL:
        print(f"[CLAIM_EXTENDED] ERROR: lease_ttl {lease_ttl}s below minimum {MIN_LEASE_TTL}s")
        return
    
    # Validate heartbeat_interval
    if heartbeat_interval <= 0 or heartbeat_interval >= lease_ttl:
        print(f"[CLAIM_EXTENDED] ERROR: Invalid heartbeat_interval {heartbeat_interval}s (must be > 0 and < {lease_ttl}s)")
        return
    
    # Validate cost and eta if provided
    if cost is not None and cost <= 0:
        print(f"[CLAIM_EXTENDED] ERROR: Cost must be positive, got {cost}")
        return
    
    if eta is not None and eta <= 0:
        print(f"[CLAIM_EXTENDED] ERROR: ETA must be positive, got {eta}")
        return
    
    # Create lease record
    lease_id = str(uuid.uuid4())
    current_time = time.time_ns()
    
    lease_record = {
        "lease_id": lease_id,
        "task_id": task_id,
        "worker_id": worker_id,
        "ttl": lease_ttl,
        "created_at": current_time,
        "last_heartbeat": current_time,
        "heartbeat_interval": heartbeat_interval
    }
    
    _lease_registry[lease_id] = lease_record
    
    # Create ANNOTATE op to record the extended claim
    op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=sender,
        op_type=OpType.ANNOTATE,
        task_id=task_id,
        payload={
            "annotation_type": "claim_extended",
            "lease_id": lease_id,
            "worker_id": worker_id,
            "lease_ttl": lease_ttl,
            "heartbeat_interval": heartbeat_interval,
            "cost": cost,
            "eta": eta,
            "claimed_at": current_time
        },
        timestamp_ns=current_time
    )
    
    await plan_store.append_op(op)
    
    # Update task state to DECIDED
    state_op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"] + 1,
        actor_id=envelope["sender_pk_b64"],
        op_type=OpType.STATE,
        task_id=task_id,
        payload={"state": TaskState.DECIDED.value},
        timestamp_ns=time.time_ns()
    )
    
    await plan_store.append_op(state_op)
    
    print(f"[CLAIM_EXTENDED] Lease {lease_id} created for task {task_id} by {worker_id[:8]}... (TTL: {lease_ttl}s, HB: {heartbeat_interval}s)")

def get_lease(lease_id: str):
    """Get lease record by ID"""
    return _lease_registry.get(lease_id)

def get_all_leases():
    """Get all lease records"""
    return dict(_lease_registry)

# Register with dispatcher
DISPATCHER.register("CLAIM_EXTENDED", handle_claim_extended)
