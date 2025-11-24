"""
DECIDE Handler: atomic decision recording via consensus.
"""

import uuid
from plan_store import PlanStore, PlanOp, OpType, TaskState
from verbs import DISPATCHER
from consensus import ConsensusAdapter
import time

plan_store: PlanStore = None  # Injected at startup
consensus_adapter: ConsensusAdapter = None  # Injected at startup

async def handle_decide(envelope: dict):
    """
    Process DECIDE envelope:
    1. Call consensus.try_decide() for atomic at-most-once semantics
    2. Update task state to DECIDED if consensus succeeds
    3. Record DECIDE metadata
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    
    # Extract decision details
    need_id = payload.get("need_id")
    proposal_id = payload.get("proposal_id")
    task_id = payload.get("task_id")
    epoch = payload.get("epoch", 1)
    k_plan = payload.get("k_plan", 1)
    
    if not need_id or not proposal_id:
        print(f"[DECIDE] ERROR: Missing need_id or proposal_id")
        return
    
    # Attempt atomic DECIDE via consensus
    if not consensus_adapter:
        print(f"[DECIDE] ERROR: No consensus adapter configured")
        return
    
    decide_record = consensus_adapter.try_decide(
        need_id=need_id,
        proposal_id=proposal_id,
        epoch=epoch,
        lamport=envelope["lamport"],
        k_plan=k_plan,
        decider_id=envelope["sender_pk_b64"],
        timestamp_ns=time.time_ns()
    )
    
    if decide_record is None:
        print(f"[DECIDE] CONFLICT: DECIDE already exists for need {need_id}")
        return
    
    print(f"[DECIDE] ✓ Atomic DECIDE recorded for need {need_id} -> proposal {proposal_id}")
    
    # Update task state to DECIDED (if task_id provided)
    if task_id:
        state_op = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id=thread_id,
            lamport=envelope["lamport"],
            actor_id=envelope["sender_pk_b64"],
            op_type=OpType.STATE,
            task_id=task_id,
            payload={"state": TaskState.DECIDED.value},
            timestamp_ns=time.time_ns()
        )
        plan_store.append_op(state_op)
        print(f"[DECIDE] Updated task {task_id} state to DECIDED")
    
    # Record DECIDE metadata as annotation
    decide_op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=envelope["sender_pk_b64"],
        op_type=OpType.ANNOTATE,
        task_id=task_id or need_id,
        payload={
            "annotation_type": "decide",
            "need_id": need_id,
            "proposal_id": proposal_id,
            "epoch": epoch,
            "k_plan": k_plan,
            "decider": envelope["sender_pk_b64"],
            "decided_at": time.time_ns()
        },
        timestamp_ns=time.time_ns()
    )
    plan_store.append_op(decide_op)

# Register with dispatcher
DISPATCHER.register("DECIDE", handle_decide)
