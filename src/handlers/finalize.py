"""
FINALIZE Handler: marks task completion.

Enhanced with cross-shard dependency checking for distributed workflows.
"""

import uuid
from plan_store import PlanStore, PlanOp, OpType, TaskState
from verbs import DISPATCHER
import time
import logging

logger = logging.getLogger(__name__)

plan_store: PlanStore = None  # Injected at startup

# Cross-shard dependency DAG (optional, injected if using sharding)
dependency_dag = None

async def handle_finalize(envelope: dict):
    """
    Process FINALIZE envelope:
    1. Check cross-shard dependencies (if applicable)
    2. Update task state to FINAL
    3. Record completion metadata
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    
    # Extract finalization details
    task_id = payload.get("task_id")
    
    if not task_id:
        logger.error("[FINALIZE] No task_id in finalize payload")
        return
    
    # Check cross-shard dependencies if enabled
    if dependency_dag and "shard_id" in payload:
        if not _check_cross_shard_dependencies(payload):
            logger.warning(
                f"[FINALIZE] Blocked finalization of task {task_id} "
                f"due to incomplete cross-shard dependencies"
            )
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
    await plan_store.append_op(state_op)
    
    logger.info(f"[FINALIZE] Updated task {task_id} state to FINAL")
    
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
    await plan_store.append_op(finalize_op)
    
    logger.info(f"[FINALIZE] Task {task_id} marked as complete")
    
    # Mark shard as complete in dependency DAG
    if dependency_dag and "shard_id" in payload:
        shard_id = payload["shard_id"]
        newly_ready = dependency_dag.mark_shard_complete(shard_id)
        if newly_ready:
            logger.info(
                f"[FINALIZE] Shard {shard_id} completion unblocked "
                f"{len(newly_ready)} dependent shards: {newly_ready}"
            )


def _check_cross_shard_dependencies(payload: dict) -> bool:
    """
    Check if all cross-shard dependencies are satisfied.
    
    Args:
        payload: FINALIZE payload containing shard info
        
    Returns:
        True if dependencies satisfied or no dependencies
    """
    shard_id = payload.get("shard_id")
    if shard_id is None:
        return True
    
    # Check if this shard has any blocking dependencies
    blocking = dependency_dag.get_blocking_shards(shard_id)
    
    if blocking:
        logger.debug(
            f"Shard {shard_id} blocked by {len(blocking)} dependencies: {blocking}"
        )
        return False
    
    return True


# Register with dispatcher
DISPATCHER.register("FINALIZE", handle_finalize)

