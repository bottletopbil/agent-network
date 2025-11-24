"""
COMMIT Handler: records task completion with artifact validation.
"""

import uuid
from plan_store import PlanStore, PlanOp, OpType
from verbs import DISPATCHER
import cas
import time

plan_store: PlanStore = None  # Injected at startup

async def handle_commit(envelope: dict):
    """
    Process COMMIT envelope:
    1. Validate artifact_hash exists in CAS
    2. Record commit in plan store if validation passes
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    
    # Extract commit details
    task_id = payload.get("task_id")
    artifact_hash = payload.get("artifact_hash")
    
    if not task_id:
        print(f"[COMMIT] ERROR: No task_id in commit payload")
        return
    
    if not artifact_hash:
        print(f"[COMMIT] ERROR: No artifact_hash in commit payload")
        return
    
    # Validate artifact exists in CAS
    if not cas.has_blob(artifact_hash):
        print(f"[COMMIT] ERROR: Artifact {artifact_hash} not found in CAS")
        return
    
    commit_id = payload.get("commit_id", str(uuid.uuid4()))
    
    # Create ANNOTATE op to record the commit
    op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=envelope["sender_pk_b64"],
        op_type=OpType.ANNOTATE,
        task_id=task_id,
        payload={
            "annotation_type": "commit",
            "commit_id": commit_id,
            "artifact_hash": artifact_hash,
            "committer": envelope["sender_pk_b64"],
            "committed_at": time.time_ns()
        },
        timestamp_ns=time.time_ns()
    )
    
    plan_store.append_op(op)
    print(f"[COMMIT] Recorded commit {commit_id} for task {task_id} with artifact {artifact_hash[:8]}...")

# Register with dispatcher
DISPATCHER.register("COMMIT", handle_commit)
