"""
YIELD Handler: allows agents to voluntarily release claimed tasks.
"""

import uuid
from plan_store import PlanStore, PlanOp, OpType, TaskState
from verbs import DISPATCHER
import time

plan_store: PlanStore = None  # Injected at startup

async def handle_yield(envelope: dict):
    """
    Process YIELD envelope:
    1. Release the lease on the task
    2. Update task state back to DRAFT
    3. Allow re-claiming by other agents
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    
    # Extract yield details
    task_id = payload.get("task_id")
    if not task_id:
        print(f"[YIELD] ERROR: No task_id in yield payload")
        return
    
    reason = payload.get("reason", "voluntary_yield")
    
    # Create ANNOTATE op to record the yield
    op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=envelope["sender_pk_b64"],
        op_type=OpType.ANNOTATE,
        task_id=task_id,
        payload={
            "annotation_type": "yield",
            "yielder": envelope["sender_pk_b64"],
            "reason": reason,
            "yielded_at": time.time_ns()
        },
        timestamp_ns=time.time_ns()
    )
    
    plan_store.append_op(op)
    
    # Update task state back to DRAFT to allow re-claiming
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
    
    plan_store.append_op(state_op)
    print(f"[YIELD] Task {task_id} yielded by {envelope['sender_pk_b64'][:8]}... (reason: {reason})")

# Register with dispatcher
DISPATCHER.register("YIELD", handle_yield)
