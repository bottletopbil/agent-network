"""
PROPOSE_EXTENDED Handler: extended proposal with ballot validation and patches.
"""

import uuid
from plan_store import PlanStore, PlanOp, OpType
from verbs import DISPATCHER
import time

plan_store: PlanStore = None  # Injected at startup

# Track ballots per proposer to ensure uniqueness
_ballot_registry = {}  # {sender_pk_b64: set(ballot_ids)}

async def handle_propose_extended(envelope: dict):
    """
    Process PROPOSE_EXTENDED envelope:
    1. Validate ballot is unique per proposer
    2. Validate patch contains valid plan operations
    3. Record proposal with cost and ETA
    4. Store for future attestation
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    sender = envelope["sender_pk_b64"]
    
    # Extract proposal details
    need_id = payload.get("need_id")
    proposal_id = payload.get("proposal_id", str(uuid.uuid4()))
    ballot = payload.get("ballot")
    patch = payload.get("patch", [])
    cost = payload.get("cost")
    eta = payload.get("eta")
    
    # Validation
    if not need_id:
        print(f"[PROPOSE_EXTENDED] ERROR: No need_id in payload")
        return
    
    if not ballot:
        print(f"[PROPOSE_EXTENDED] ERROR: No ballot in payload")
        return
    
    # Check ballot uniqueness per proposer
    if sender not in _ballot_registry:
        _ballot_registry[sender] = set()
    
    if ballot in _ballot_registry[sender]:
        print(f"[PROPOSE_EXTENDED] ERROR: Duplicate ballot '{ballot}' from {sender[:8]}...")
        return
    
    # Validate patch is not empty
    if not patch:
        print(f"[PROPOSE_EXTENDED] ERROR: Empty patch in proposal")
        return
    
    # Validate each patch operation
    valid_ops = []
    for idx, op_data in enumerate(patch):
        op_type_str = op_data.get("op_type")
        task_id = op_data.get("task_id")
        
        if not op_type_str or not task_id:
            print(f"[PROPOSE_EXTENDED] WARNING: Skipping invalid patch op at index {idx}")
            continue
        
        # Validate op_type
        try:
            OpType(op_type_str)
            valid_ops.append(op_data)
        except ValueError:
            print(f"[PROPOSE_EXTENDED] WARNING: Invalid op_type '{op_type_str}' at index {idx}")
            continue
    
    if not valid_ops:
        print(f"[PROPOSE_EXTENDED] ERROR: No valid operations in patch")
        return
    
    # Validate cost and eta
    if cost is not None and cost <= 0:
        print(f"[PROPOSE_EXTENDED] ERROR: Cost must be positive, got {cost}")
        return
    
    if eta is not None and eta <= 0:
        print(f"[PROPOSE_EXTENDED] ERROR: ETA must be positive, got {eta}")
        return
    
    # Register ballot
    _ballot_registry[sender].add(ballot)
    
    # Create ANNOTATE op to record the extended proposal
    op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=sender,
        op_type=OpType.ANNOTATE,
        task_id=need_id,
        payload={
            "annotation_type": "proposal_extended",
            "proposal_id": proposal_id,
            "ballot": ballot,
            "patch": valid_ops,
            "cost": cost,
            "eta": eta,
            "proposer": sender,
            "proposed_at": time.time_ns()
        },
        timestamp_ns=time.time_ns()
    )
    
    await plan_store.append_op(op)
    print(f"[PROPOSE_EXTENDED] Recorded proposal {proposal_id} with ballot '{ballot}' (cost: {cost}, eta: {eta}s)")

# Register with dispatcher
DISPATCHER.register("PROPOSE_EXTENDED", handle_propose_extended)
