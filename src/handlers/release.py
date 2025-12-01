"""
RELEASE Handler: system-initiated lease expiration and task scavenging.
"""

import uuid
from plan_store import PlanStore, PlanOp, OpType, TaskState
from verbs import DISPATCHER
import time

plan_store: PlanStore = None  # Injected at startup

async def handle_release(envelope: dict):
    """
    Process RELEASE envelope (system-initiated):
    1. Expire the lease (timeout or heartbeat_miss)
    2. Scavenge task by updating state to DRAFT
    3. Notify coordinator of the release event
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    
    # Extract release details
    task_id = payload.get("task_id")
    lease_id = payload.get("lease_id")
    reason = payload.get("reason", "timeout")
    
    if not task_id:
        print(f"[RELEASE] ERROR: No task_id in release payload")
        return
    
    if not lease_id:
        print(f"[RELEASE] ERROR: No lease_id in release payload")
        return
    
    # Validate reason
    valid_reasons = ["timeout", "heartbeat_miss"]
    if reason not in valid_reasons:
        print(f"[RELEASE] WARNING: Invalid reason '{reason}', using 'timeout'")
        reason = "timeout"
    
    # Create ANNOTATE op to record the release
    op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=envelope["sender_pk_b64"],
        op_type=OpType.ANNOTATE,
        task_id=task_id,
        payload={
            "annotation_type": "release",
            "lease_id": lease_id,
            "reason": reason,
            "released_at": time.time_ns(),
            "system_initiated": True
        },
        timestamp_ns=time.time_ns()
    )
    
    await plan_store.append_op(op)
    
    # Scavenge task by updating state to DRAFT
    state_op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"] + 1,
        actor_id=envelope["sender_pk_b64"],
        op_type=OpType.STATE,
        task_id=task_id,
        payload={"state": TaskState.DRAFT.value},
        timestamp_ns=time.time_ns()
    )
    
    await plan_store.append_op(state_op)
    print(f"[RELEASE] Lease {lease_id} released for task {task_id} (reason: {reason})")

# Register with dispatcher
DISPATCHER.register("RELEASE", handle_release)
