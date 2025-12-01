"""
CLAIM Handler: records task claims with lease TTL.
"""

import uuid
from plan_store import PlanStore, PlanOp, OpType
from verbs import DISPATCHER
import time

plan_store: PlanStore = None  # Injected at startup

async def handle_claim(envelope: dict):
    """
    Process CLAIM envelope:
    1. Record claim with lease TTL
    2. Store claim as ANNOTATE op
    3. Track claimer and lease expiration
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    
    # Extract claim details
    task_id = payload.get("task_id")
    if not task_id:
        print(f"[CLAIM] ERROR: No task_id in claim payload")
        return
    
    claim_id = payload.get("claim_id", str(uuid.uuid4()))
    lease_ttl = payload.get("lease_ttl", 300)  # Default 5 minutes
    
    # Create ANNOTATE op to record the claim
    op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=envelope["sender_pk_b64"],
        op_type=OpType.ANNOTATE,
        task_id=task_id,
        payload={
            "annotation_type": "claim",
            "claim_id": claim_id,
            "claimer": envelope["sender_pk_b64"],
            "lease_ttl": lease_ttl,
            "claimed_at": time.time_ns()
        },
        timestamp_ns=time.time_ns()
    )
    
    await plan_store.append_op(op)
    print(f"[CLAIM] Recorded claim {claim_id} for task {task_id} by {envelope['sender_pk_b64'][:8]}... (lease: {lease_ttl}s)")

# Register with dispatcher
DISPATCHER.register("CLAIM", handle_claim)
