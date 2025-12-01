"""
PROPOSE Handler: stores task proposals.
"""

import uuid
from plan_store import PlanStore, PlanOp, OpType
from verbs import DISPATCHER
import time

plan_store: PlanStore = None  # Injected at startup

async def handle_propose(envelope: dict):
    """
    Process PROPOSE envelope:
    1. Store proposal as ANNOTATE op in plan store
    2. Proposal includes plan details and proposer info
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    
    # Extract proposal details
    proposal_id = payload.get("proposal_id", str(uuid.uuid4()))
    
    # Create ANNOTATE op to store the proposal
    op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=envelope["sender_pk_b64"],
        op_type=OpType.ANNOTATE,
        task_id=payload.get("need_id", "global"),  # Link to NEED or global proposals
        payload={
            "annotation_type": "proposal",
            "proposal_id": proposal_id,
            "plan": payload.get("plan", []),
            "proposer": envelope["sender_pk_b64"],
            "metadata": payload.get("metadata", {})
        },
        timestamp_ns=time.time_ns()
    )
    
    await plan_store.append_op(op)
    print(f"[PROPOSE] Stored proposal {proposal_id} in thread {thread_id}")

# Register with dispatcher
DISPATCHER.register("PROPOSE", handle_propose)
