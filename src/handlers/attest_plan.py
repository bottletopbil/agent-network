"""
ATTEST_PLAN Handler: verifier attestation for proposals with quorum-based DECIDE.
"""

import uuid
from plan_store import PlanStore, PlanOp, OpType
from verbs import DISPATCHER
from consensus.quorum import quorum_tracker
from consensus.raft_adapter import RaftConsensusAdapter
from consensus.feature_flag import use_raft_consensus
from consensus import ConsensusAdapter
import time

plan_store: PlanStore = None  # Injected at startup
verifier_pool = None  # Optional: Injected if available
raft_adapter: RaftConsensusAdapter = None  # Injected at startup (etcd)
consensus_adapter: ConsensusAdapter = None  # Injected at startup (Redis)

async def handle_attest_plan(envelope: dict):
    """
    Process ATTEST_PLAN envelope:
    1. Validate verifier is in pool (if pool available)
    2. Record attestation in QuorumTracker
    3. Check if quorum (K_plan) reached
    4. If quorum reached, trigger DECIDE via Raft/Redis
    5. Emit DECIDE message on success
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    sender = envelope["sender_pk_b64"]
    
    # Extract attestation details
    need_id = payload.get("need_id")
    proposal_id = payload.get("proposal_id")
    verdict = payload.get("verdict", "approve")
    
    # Validation
    if not need_id:
        print(f"[ATTEST_PLAN] ERROR: No need_id in payload")
        return
    
    if not proposal_id:
        print(f"[ATTEST_PLAN] ERROR: No proposal_id in payload")
        return
    
    # Validate verdict value
    if verdict not in ["approve", "reject"]:
        print(f"[ATTEST_PLAN] ERROR: Invalid verdict '{verdict}', must be 'approve' or 'reject'")
        return
    
    # Skip if not approve (only approvals count toward quorum)
    if verdict != "approve":
        print(f"[ATTEST_PLAN] Rejection from {sender[:8]}... for proposal {proposal_id} (not counted)")
        return
    
    # Validate verifier is in pool (if pool available)
    if verifier_pool is not None:
        try:
            verifier = verifier_pool.get_verifier(sender)
            if verifier is None:
                print(f"[ATTEST_PLAN] ERROR: Verifier {sender[:8]}... not in pool")
                return
            if not verifier.active:
                print(f"[ATTEST_PLAN] ERROR: Verifier {sender[:8]}... is inactive")
                return
        except Exception as e:
            # Graceful degradation if pool check fails
            print(f"[ATTEST_PLAN] WARNING: Pool validation failed: {e}")
    
    # Get active verifier count for K_plan calculation
    try:
        if verifier_pool is not None:
            active_verifiers = len(verifier_pool.get_active_verifiers(min_stake=100))
        else:
            # Default if pool not available
            active_verifiers = 10
    except Exception:
        active_verifiers = 10
    
    # Calculate K_plan dynamically based on active verifiers
    k_plan = quorum_tracker.get_k_plan(
        active_verifiers=active_verifiers,
        alpha=0.3,
        k_target=5
    )
    
    # Record attestation in QuorumTracker
    quorum_reached = quorum_tracker.record_attestation(
        need_id=need_id,
        proposal_id=proposal_id,
        verifier_id=sender,
        k_plan=k_plan
    )
    
    # Create ANNOTATE op to record the attestation
    op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=sender,
        op_type=OpType.ANNOTATE,
        task_id=need_id,
        payload={
            "annotation_type": "attest_plan",
            "proposal_id": proposal_id,
            "verifier": sender,
            "verdict": verdict,
            "attested_at": time.time_ns()
        },
        timestamp_ns=time.time_ns()
    )
    
    await plan_store.append_op(op)
    
    # Get current attestation count
    attestation_count = quorum_tracker.get_attestation_count(need_id, proposal_id)
    
    print(f"[ATTEST_PLAN] Recorded approval from {sender[:8]}... for proposal {proposal_id} ({attestation_count}/{k_plan})")
    
    # If quorum reached, trigger DECIDE
    if quorum_reached:
        print(f"[ATTEST_PLAN] ✓ Quorum reached for proposal {proposal_id} ({k_plan}/{k_plan} approvals)")
        
        # Attempt DECIDE via consensus (Raft or Redis)
        epoch = envelope.get("epoch", 1)
        
        if use_raft_consensus():
            if not raft_adapter:
                print(f"[ATTEST_PLAN] ERROR: Raft adapter not configured")
                return
            
            decide_record = raft_adapter.try_decide(
                need_id=need_id,
                proposal_id=proposal_id,
                epoch=epoch,
                lamport=envelope["lamport"],
                k_plan=k_plan,
                decider_id="quorum-system",
                timestamp_ns=time.time_ns()
            )
        else:
            if not consensus_adapter:
                print(f"[ATTEST_PLAN] ERROR: Redis adapter not configured")
                return
            
            decide_record = consensus_adapter.try_decide(
                need_id=need_id,
                proposal_id=proposal_id,
                epoch=epoch,
                lamport=envelope["lamport"],
                k_plan=k_plan,
                decider_id="quorum-system",
                timestamp_ns=time.time_ns()
            )
        
        if decide_record is None:
            consensus_type = "Raft" if use_raft_consensus() else "Redis"
            print(f"[ATTEST_PLAN] CONFLICT ({consensus_type}): DECIDE already exists for need {need_id}")
            return
        
        consensus_type = "Raft" if use_raft_consensus() else "Redis"
        print(f"[ATTEST_PLAN] ✓ DECIDE recorded ({consensus_type}): need {need_id} → proposal {proposal_id}")
        
        # TODO: Emit DECIDE message on message bus
        # This would publish a DECIDE envelope to notify other agents
        # For now, just logging the successful DECIDE

def get_attestation_count(need_id: str, proposal_id: str) -> int:
    """Get attestation count for a proposal"""
    return quorum_tracker.get_attestation_count(need_id, proposal_id)

def check_quorum(need_id: str, proposal_id: str) -> bool:
    """Check if quorum has been reached for a proposal"""
    return quorum_tracker.check_quorum(need_id, proposal_id)

# Register with dispatcher
DISPATCHER.register("ATTEST_PLAN", handle_attest_plan)
