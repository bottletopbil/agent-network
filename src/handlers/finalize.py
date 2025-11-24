"""
FINALIZE Handler: marks task completion.
"""

import uuid
from plan_store import PlanStore, PlanOp, OpType, TaskState
from verbs import DISPATCHER
import time

plan_store: PlanStore = None  # Injected at startup

async def handle_finalize(envelope: dict):
    """
    Process FINALIZE envelope:
    1. Update task state to FINAL
    2. Record completion metadata
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    
    # Extract finalization details
    task_id = payload.get("task_id")
    
    if not task_id:
        print(f"[FINALIZE] ERROR: No task_id in finalize payload")
        return
    
    # Update task state to FINAL
    state_op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=envelope["sender_pk_b64"],
        op_type=OpType.STATE,
        task_id=task_id,
        payload={"state": TaskState.FINAL.value},
        timestamp_ns=time.time_ns()
    )
    plan_store.append_op(state_op)
    
    print(f"[FINALIZE] Updated task {task_id} state to FINAL")
    
    # Record completion metadata
    finalize_op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=envelope["sender_pk_b64"],
        op_type=OpType.ANNOTATE,
        task_id=task_id,
        payload={
            "annotation_type": "finalize",
            "finalized_by": envelope["sender_pk_b64"],
            "finalized_at": time.time_ns(),
            "metadata": payload.get("metadata", {})
        },
        timestamp_ns=time.time_ns()
    )
    plan_store.append_op(finalize_op)
    
    print(f"[FINALIZE] Task {task_id} marked as complete")

# Register with dispatcher
DISPATCHER.register("FINALIZE", handle_finalize)
