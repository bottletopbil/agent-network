"""
COMMIT Handler: records task completion with artifact validation.

Enhanced with cross-shard commitment protocol and THREE-GATE policy enforcement.
"""

import uuid
from plan_store import PlanStore, PlanOp, OpType
from verbs import DISPATCHER
from bus import get_gate_enforcer  # For commit_gate validation
import cas
import time
import logging

logger = logging.getLogger(__name__)

plan_store: PlanStore = None  # Injected at startup

# Cross-shard commitment protocol (optional, injected if using sharding)
commitment_protocol = None


async def handle_commit(envelope: dict):
    """
    Process COMMIT envelope:
    1. Validate with commit_gate (compare claimed vs actual resources)
    2. Validate artifact_hash exists in CAS
    3. Record commit in plan store if validation passes
    4. For cross-shard tasks, create and publish commitment artifact
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]

    # Extract telemetry data for commit_gate validation
    telemetry = payload.get("telemetry", {})

    # ✅ COMMIT_GATE: Validate actual execution against claimed resources
    gate_enforcer = get_gate_enforcer()
    decision = gate_enforcer.commit_gate_validate(envelope, telemetry)

    if not decision.allowed:
        logger.error(
            f"[COMMIT] Commit gate validation failed for task {payload.get('task_id')}: "
            f"{decision.reason}"
        )
        return  # Reject the commit

    logger.debug(f"[COMMIT] Commit gate passed (gas: {decision.gas_used})")

    # Extract commit details
    task_id = payload.get("task_id")
    artifact_hash = payload.get("artifact_hash")

    if not task_id:
        logger.error("[COMMIT] No task_id in commit payload")
        return

    if not artifact_hash:
        logger.error("[COMMIT] No artifact_hash in commit payload")
        return

    # Validate artifact exists in CAS
    if not cas.has_blob(artifact_hash):
        logger.error(f"[COMMIT] Artifact {artifact_hash} not found in CAS")
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
            "committed_at": time.time_ns(),
            "telemetry": telemetry,  # Include telemetry in commit record
        },
        timestamp_ns=time.time_ns(),
    )

    await plan_store.append_op(op)
    logger.info(
        f"[COMMIT] Recorded commit {commit_id} for task {task_id} "
        f"with artifact {artifact_hash[:8]}..."
    )

    # Handle cross-shard commitment if enabled
    if commitment_protocol and "shard_id" in payload:
        _handle_cross_shard_commitment(payload, artifact_hash)


def _handle_cross_shard_commitment(payload: dict, artifact_hash: str):
    """
    Handle cross-shard commitment creation and publishing.

    Args:
        payload: COMMIT payload containing shard info
        artifact_hash: Hash of the committed artifact
    """
    shard_id = payload["shard_id"]
    need_id = payload.get("need_id")
    dependencies = payload.get("commitment_dependencies", [])

    if not need_id:
        logger.warning("[COMMIT] No need_id for cross-shard commitment")
        return

    try:
        # Create commitment artifact
        commitment = commitment_protocol.create_commitment(
            shard_id=shard_id,
            need_id=need_id,
            artifact_ref=artifact_hash,
            dependencies=dependencies,
        )

        # Publish to commitment registry
        success = commitment_protocol.publish_commitment(commitment)

        if success:
            logger.info(
                f"[COMMIT] Published cross-shard commitment "
                f"{commitment.commitment_hash[:8]} for shard {shard_id}"
            )
        else:
            logger.warning(f"[COMMIT] Failed to publish commitment for shard {shard_id}")

    except Exception as e:
        logger.error(f"[COMMIT] Error creating cross-shard commitment: {e}")


# Register with dispatcher
DISPATCHER.register("COMMIT", handle_commit)
