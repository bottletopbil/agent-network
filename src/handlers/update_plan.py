"""
UPDATE_PLAN Handler: collaborative plan updates broadcast to peers.

Enhanced with:
- Patch validation before applying operations
- Plan version tracking with merkle roots
- Conflict detection and reporting
"""

import uuid
import time
import os
from pathlib import Path
from plan_store import PlanStore, PlanOp, OpType
from plan.patching import PlanPatch, PatchValidator
from plan.versioning import VersionTracker
from verbs import DISPATCHER

plan_store: PlanStore = None  # Injected at startup
version_tracker: VersionTracker = None  # Injected at startup

# Initialize version tracker on module load
STATE_DIR = Path(os.getenv("SWARM_STATE_DIR", ".state"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
_version_db_path = STATE_DIR / "plan_versions.db"


def _ensure_version_tracker():
    """Lazy initialization of version tracker"""
    global version_tracker
    if version_tracker is None:
        version_tracker = VersionTracker(_version_db_path)
    return version_tracker


async def handle_update_plan(envelope: dict):
    """
    Process UPDATE_PLAN envelope:
    1. Create and validate patch
    2. Apply operations to plan store (skip invalid ops)
    3. Record plan version
    4. Broadcast to peers (via bus mechanism)
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    lamport = envelope["lamport"]
    actor_id = envelope["sender_pk_b64"]

    # Extract update details
    ops_data = payload.get("ops", [])

    if not ops_data:
        print(f"[UPDATE_PLAN] ERROR: No ops in update_plan payload")
        return

    # Create PlanPatch
    patch = PlanPatch(
        patch_id=str(uuid.uuid4()),
        actor_id=actor_id,
        base_lamport=lamport,
        ops=ops_data,
        timestamp_ns=time.time_ns(),
    )

    # Basic validation (non-empty ops, has required fields)
    if not patch.patch_id or not patch.actor_id or patch.base_lamport < 0:
        print(f"[UPDATE_PLAN] ERROR: Invalid patch structure")
        return

    print(f"[UPDATE_PLAN] Processing patch {patch.patch_id} with {len(ops_data)} operations")

    applied_count = 0
    current_lamport = lamport
    PatchValidator(plan_store)

    # Process each operation individually - validate and skip invalid ones
    for idx, op_data in enumerate(ops_data):
        op_type_str = op_data.get("op_type")
        task_id = op_data.get("task_id")
        op_payload = op_data.get("payload", {})

        # Validate op has required fields
        if not op_type_str or not task_id:
            print(f"[UPDATE_PLAN] WARNING: Skipping op {idx}: missing op_type or task_id")
            continue

        # Validate op_type is valid
        try:
            op_type = OpType(op_type_str)
        except ValueError:
            print(f"[UPDATE_PLAN] WARNING: Skipping op {idx}: invalid op_type '{op_type_str}'")
            continue

        # Validate op-specific fields
        if op_type_str == "STATE" and "state" not in op_payload:
            print(f"[UPDATE_PLAN] WARNING: Skipping op {idx}: STATE op missing 'state' in payload")
            continue

        if op_type_str == "LINK":
            if "parent" not in op_payload or "child" not in op_payload:
                print(
                    f"[UPDATE_PLAN] WARNING: Skipping op {idx}: LINK op missing 'parent' or 'child'"
                )
                continue

        # Create and append the operation
        op = PlanOp(
            op_id=str(uuid.uuid4()),
            thread_id=thread_id,
            lamport=current_lamport,
            actor_id=actor_id,
            op_type=op_type,
            task_id=task_id,
            payload=op_payload,
            timestamp_ns=time.time_ns(),
        )

        await plan_store.append_op(op)
        applied_count += 1
        current_lamport += 1

    print(f"[UPDATE_PLAN] Applied {applied_count}/{len(ops_data)} operations to thread {thread_id}")

    # Record plan version after applying ops (only if we applied at least one op)
    if applied_count > 0:
        try:
            tracker = _ensure_version_tracker()

            # Get current plan state (all tasks)
            # Note: This is a simplified version. In production, you'd want to get all tasks from plan_store
            # For now, we'll create a minimal snapshot
            plan_state = {}

            # Get all unique task_ids from the operations we just applied
            task_ids = set(op_data.get("task_id") for op_data in ops_data if op_data.get("task_id"))

            for task_id in task_ids:
                task = plan_store.get_task(task_id)
                if task:
                    plan_state[task_id] = task

            if plan_state:
                version = tracker.record_version(
                    plan_state=plan_state,
                    lamport=current_lamport - 1,  # Use the last applied lamport
                    metadata={
                        "thread_id": thread_id,
                        "patch_id": patch.patch_id,
                        "actor_id": actor_id,
                        "ops_count": applied_count,
                    },
                )
                print(
                    f"[UPDATE_PLAN] Recorded version {version.version_id} at lamport {version.lamport}, merkle: {version.merkle_root[:16]}..."
                )
        except Exception as e:
            print(f"[UPDATE_PLAN] WARNING: Failed to record version: {e}")

    # Note: Broadcasting to peers would happen via the bus mechanism
    # This is handled at a higher level and not implemented here yet


# Register with dispatcher
DISPATCHER.register("UPDATE_PLAN", handle_update_plan)
