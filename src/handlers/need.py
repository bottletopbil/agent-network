"""
NEED Handler: initiates a new task request.
"""

import uuid
from plan_store import PlanStore, PlanOp, OpType
from verbs import DISPATCHER
import time

plan_store: PlanStore = None  # Injected at startup

async def handle_need(envelope: dict):
    """
    Process NEED envelope:
    1. Create task in plan store
    2. Emit NEED event to audit
    3. (Agents will see this and may PROPOSE)
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    
    task_id = str(uuid.uuid4())
    
    # Add task to plan
    op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=envelope["sender_pk_b64"],
        op_type=OpType.ADD_TASK,
        task_id=task_id,
        payload={
            "type": payload.get("task_type", "generic"),
            "requires": payload.get("requires", []),
            "produces": payload.get("produces", [])
        },
        timestamp_ns=time.time_ns()
    )
    
    plan_store.append_op(op)
    print(f"[NEED] Created task {task_id} in thread {thread_id}")

# Register with dispatcher
DISPATCHER.register("NEED", handle_need)
