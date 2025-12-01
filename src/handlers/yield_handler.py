"""
YIELD Handler: allows agents to voluntarily release claimed tasks.
"""

import uuid
from plan_store import PlanStore, PlanOp, OpType, TaskState
from verbs import DISPATCHER
from policy.enforcement import require_policy_validation
import time

plan_store: PlanStore = None  # Injected at startup


@require_policy_validation
async def handle_yield(envelope: dict):
    """
    Process YIELD envelope:
    1. Release the lease on the task
    2. Update task state back to DRAFT
    3. Allow re-claiming by other agents

    Error handling: Validates inputs and catches exceptions to prevent crashes.
    """
    import logging
    import sqlite3

    logger = logging.getLogger(__name__)

    try:
        # Validate envelope structure
        thread_id = envelope.get("thread_id")
        if not thread_id:
            logger.error("[YIELD] ERROR: Missing thread_id in envelope")
            return

        payload = envelope.get("payload")
        if not payload:
            logger.error(
                f"[YIELD] ERROR: Missing payload in envelope for thread {thread_id}"
            )
            return

        sender = envelope.get("sender_pk_b64")
        if not sender:
            logger.error(
                f"[YIELD] ERROR: Missing sender_pk_b64 in envelope for thread {thread_id}"
            )
            return

        lamport = envelope.get("lamport")
        if lamport is None:
            logger.error(
                f"[YIELD] ERROR: Missing lamport in envelope for thread {thread_id}"
            )
            return

        # Extract yield details
        task_id = payload.get("task_id")
        if not task_id:
            logger.error(
                f"[YIELD] ERROR: No task_id in yield payload for thread {thread_id}"
            )
            return

        reason = payload.get("reason", "voluntary_yield")

        # Create ANNOTATE op to record the yield
        op = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id=thread_id,
            lamport=lamport,
            actor_id=sender,
            op_type=OpType.ANNOTATE,
            task_id=task_id,
            payload={
                "annotation_type": "yield",
                "yielder": sender,
                "reason": reason,
                "yielded_at": time.time_ns(),
            },
            timestamp_ns=time.time_ns(),
        )

        await plan_store.append_op(op)

        # Update task state back to DRAFT to allow re-claiming
        state_op = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id=thread_id,
            lamport=lamport + 1,
            actor_id=sender,
            op_type=OpType.STATE,
            task_id=task_id,
            payload={"state": TaskState.DRAFT.value},
            timestamp_ns=time.time_ns(),
        )

        await plan_store.append_op(state_op)

        print(f"[YIELD] Task {task_id} yielded by {sender[:8]}... (reason: {reason})")

    except sqlite3.OperationalError as e:
        logger.error(
            f"[YIELD] Database error for task {task_id if 'task_id' in locals() else 'unknown'}: {e}"
        )
    except Exception as e:
        logger.error(f"[YIELD] Unexpected error processing yield: {e}", exc_info=True)


# Register with dispatcher
DISPATCHER.register("YIELD", handle_yield)
