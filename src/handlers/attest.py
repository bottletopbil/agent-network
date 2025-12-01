"""
ATTEST Handler: records attestations and triggers DECIDE at threshold.
Now includes commit-gate policy validation.
"""

import uuid
import logging
from plan_store import PlanStore, PlanOp, OpType
from verbs import DISPATCHER
from consensus import ConsensusAdapter
from policy.gates import GateEnforcer
from policy.eval_digest import create_eval_record
import time

logger = logging.getLogger(__name__)

plan_store: PlanStore = None  # Injected at startup
consensus_adapter: ConsensusAdapter = None  # Injected at startup

# K_plan threshold - number of attestations needed to trigger DECIDE
K_PLAN = 1  # For PoC, first attestation triggers DECIDE

async def handle_attest(envelope: dict):
    """
    Process ATTEST envelope:
    1. Record attestation in plan store
    2. Check if K_plan threshold reached
    3. Trigger DECIDE if threshold met
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    
    # Extract attestation details
    commit_id = payload.get("commit_id")
    task_id = payload.get("task_id")
    verdict = payload.get("verdict", "approved")
    
    if not commit_id:
        logger.error(f"[ATTEST] ERROR: No commit_id in attest payload")
        return
    
    attestation_id = payload.get("attestation_id", str(uuid.uuid4()))
    
    # ✅ COMMIT-GATE validation: Check actual execution vs claimed resources
    gate_enforcer = GateEnforcer()
    telemetry = payload.get("telemetry", {})
    
    decision = gate_enforcer.commit_gate_validate(envelope, telemetry)
    if not decision.allowed:
        logger.error(f"[ATTEST] Commit gate validation failed: {decision.reason}")
        # Record the failed attestation but mark it as rejected
        verdict = "rejected"
    else:
        logger.info(f"[ATTEST] Commit gate passed for {commit_id}")
    
    # Create policy evaluation record with digest
    policy_input = {
        "commit_id": commit_id,
        "task_id": task_id,
        "telemetry": telemetry,
        "attester": envelope["sender_pk_b64"]
    }
    policy_decision = {
        "allowed": decision.allowed,
        "reason": decision.reason,
        "gas_used": decision.gas_used
    }
    eval_record = create_eval_record(
        policy_input,
        policy_decision,
        decision.policy_hash or "unknown"
    )
    
    # Create ANNOTATE op to record the attestation
    op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=envelope["sender_pk_b64"],
        op_type=OpType.ANNOTATE,
        task_id=task_id or "unknown",
        payload={
            "annotation_type": "attestation",
            "attestation_id": attestation_id,
            "commit_id": commit_id,
            "attester": envelope["sender_pk_b64"],
            "verdict": verdict,
            "attested_at": time.time_ns(),
            "policy_eval_digest": eval_record["policy_eval_digest"],  # Include digest
            "policy_decision": eval_record["policy_decision"],
            "gas_used": decision.gas_used
        },
        timestamp_ns=time.time_ns()
    )
    
    await plan_store.append_op(op)
    logger.info(f"[ATTEST] Recorded attestation {attestation_id} for commit {commit_id} (verdict: {verdict})")
    
    # Check K_plan threshold
    # Count attestations for this commit
    all_ops = plan_store.get_ops_for_thread(thread_id)
    attestations = [
        op for op in all_ops
        if op.op_type == OpType.ANNOTATE 
        and op.payload.get("annotation_type") == "attestation"
        and op.payload.get("commit_id") == commit_id
    ]
    
    print(f"[ATTEST] {len(attestations)} attestation(s) for commit {commit_id} (threshold: {K_PLAN})")
    
    # Trigger DECIDE if threshold reached
    if len(attestations) >= K_PLAN and consensus_adapter:
        # Extract proposal/need info from payload
        proposal_id = payload.get("proposal_id", commit_id)
        need_id = payload.get("need_id", "default-need")
        
        decide_record = consensus_adapter.try_decide(
            need_id=need_id,
            proposal_id=proposal_id,
            epoch=1,
            lamport=envelope["lamport"],
            k_plan=len(attestations),
            decider_id=envelope["sender_pk_b64"],
            timestamp_ns=time.time_ns()
        )
        
        if decide_record:
            print(f"[ATTEST] ✓ DECIDE triggered for need {need_id} -> proposal {proposal_id}")
        else:
            print(f"[ATTEST] DECIDE already exists for need {need_id}")

# Register with dispatcher
DISPATCHER.register("ATTEST", handle_attest)
