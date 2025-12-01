"""
INVALIDATE Handler: process challenge verdicts and slash dishonest verifiers.

Handles:
- Marking results as invalid
- Slashing attesting verifiers
- Reopening tasks for re-execution
- Escalating K_result requirements
"""

import json
import time
from typing import Dict, Any, List
import logging

from plan_store import PlanStore
from economics.slashing import SlashingRules
from economics.payout import PayoutDistributor

logger = logging.getLogger(__name__)


def handle_invalidate(
    envelope: Dict[str, Any],
    plan_store: PlanStore,
    slashing_rules: SlashingRules,
    payout_distributor: PayoutDistributor,
) -> None:
    """
    Handle INVALIDATE message.

    Process:
    1. Mark result as invalid
    2. Slash attesting verifiers (50% stake each)
    3. Distribute slashed amounts (50% challenger, 40% honest, 10% burn)
    4. Block payout for the task
    5. Reopen task for re-execution
    6. Escalate K_result requirement

    INVALIDATE Payload:
    {
        "task_id": str,
        "challenge_id": str,
        "slashed_verifiers": List[str],  # Account IDs of dishonest verifiers
        "honest_verifiers": List[str],   # Account IDs of honest verifiers (optional)
        "challenger": str,               # Account ID of challenger
        "evidence_hash": str,            # CAS hash of challenge evidence
        "new_k_result": int,             # Escalated K_result value
        "reason": str                    # Human-readable invalidation reason
    }

    Args:
        envelope: INVALIDATE envelope (dict)
        plan_store: PlanStore instance
        slashing_rules: SlashingRules instance
        payout_distributor: PayoutDistributor instance
    """
    payload = envelope.get("payload", {})

    # Extract required fields
    task_id = payload.get("task_id")
    challenge_id = payload.get("challenge_id")
    slashed_verifiers = payload.get("slashed_verifiers", [])
    honest_verifiers = payload.get("honest_verifiers", [])
    challenger = payload.get("challenger")
    evidence_hash = payload.get("evidence_hash")
    new_k_result = payload.get("new_k_result")
    reason = payload.get("reason", "Challenge upheld")

    # Validate required fields
    if not task_id:
        logger.error("INVALIDATE missing task_id")
        return

    if not challenge_id:
        logger.error(f"INVALIDATE for task {task_id} missing challenge_id")
        return

    if not slashed_verifiers:
        logger.warning(f"INVALIDATE for task {task_id} has no slashed_verifiers")

    if not challenger:
        logger.error(f"INVALIDATE for task {task_id} missing challenger")
        return

    if not evidence_hash:
        logger.error(f"INVALIDATE for task {task_id} missing evidence_hash")
        return

    if new_k_result is None:
        logger.error(f"INVALIDATE for task {task_id} missing new_k_result")
        return

    logger.info(f"Processing INVALIDATE for task {task_id}, challenge {challenge_id}")
    logger.info(
        f"Slashing {len(slashed_verifiers)} verifiers, rewarding challenger {challenger}"
    )

    # 1. Mark task result as invalid in plan store
    # (This is a metadata annotation on the task)
    try:
        task = plan_store.get_task(task_id)
        if task:
            # Annotate task with invalidation
            plan_store.annotate_task(
                task_id,
                {
                    "invalidated": True,
                    "invalidation_reason": reason,
                    "challenge_id": challenge_id,
                },
            )
            logger.info(f"Marked task {task_id} as invalidated")
    except Exception as e:
        logger.error(f"Failed to mark task {task_id} as invalid: {e}")

    # 2. Slash attesting verifiers
    if slashed_verifiers:
        try:
            slash_result = slashing_rules.slash_verifiers(
                verifiers=slashed_verifiers,
                challenge_evidence=evidence_hash,
                challenger=challenger,
                honest_verifiers=honest_verifiers,
                timestamp_ns=time.time_ns(),
            )

            logger.info(
                f"Slashing complete: total={slash_result['total_slashed']}, "
                f"challenger_payout={slash_result['challenger_payout']}, "
                f"honest_payout={slash_result['honest_payout']}, "
                f"burned={slash_result['burned']}"
            )
        except Exception as e:
            logger.error(f"Failed to slash verifiers for task {task_id}: {e}")

    # 3. Block payout for this task
    try:
        payout_distributor.mark_invalidated(task_id)
        logger.info(f"Blocked payout for task {task_id}")
    except Exception as e:
        logger.error(f"Failed to block payout for task {task_id}: {e}")

    # 4. Reopen task for re-execution
    # (Set task state back to OPEN with escalated K_result)
    try:
        task = plan_store.get_task(task_id)
        if task:
            # Update task state and annotations
            plan_store.annotate_task(
                task_id,
                {
                    "state": "OPEN",
                    "k_result": new_k_result,
                    "previous_attempt": "invalidated",
                    "challenge_id": challenge_id,
                },
            )
            logger.info(f"Reopened task {task_id} with K_result={new_k_result}")
    except Exception as e:
        logger.error(f"Failed to reopen task {task_id}: {e}")

    logger.info(f"INVALIDATE processing complete for task {task_id}")


def calculate_k_escalation(
    current_k: int,
    challenge_count: int,
    active_verifiers: int,
    upheld_challenges: int = 1,
) -> int:
    """
    Calculate escalated K_result value.

    Rules:
    - If single challenge upheld: K_result += 2
    - If multiple challenges on same task: K_result = min(active_verifiers, 2 × K_result)

    Args:
        current_k: Current K_result value
        challenge_count: Number of challenges on this task
        active_verifiers: Number of active verifiers in pool
        upheld_challenges: Number of upheld challenges (default 1)

    Returns:
        New K_result value
    """
    if upheld_challenges == 0:
        return current_k

    if challenge_count == 1:
        # Single challenge upheld: K += 2
        return current_k + 2
    else:
        # Multiple challenges: K = min(active_verifiers, 2 × K)
        escalated = 2 * current_k
        return min(active_verifiers, escalated)
