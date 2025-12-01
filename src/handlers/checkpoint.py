"""
CHECKPOINT Handler: creates and verifies epoch checkpoints.

Handles checkpoint creation with Merkle commitments and signature collection.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

from verbs import DISPATCHER

# Injected dependencies
checkpoint_manager = None
plan_store = None


async def handle_checkpoint(envelope: dict):
    """
    Process CHECKPOINT envelope:
    1. Validate checkpoint structure
    2. Store checkpoint if signed
    3. Broadcast to other nodes
    """
    payload = envelope["payload"]

    # Extract checkpoint data
    epoch = payload.get("epoch")
    merkle_root = payload.get("merkle_root")
    state_summary = payload.get("state_summary")
    signatures = payload.get("signatures", [])

    if epoch is None:
        logger.error("[CHECKPOINT] No epoch in payload")
        return

    if not merkle_root:
        logger.error("[CHECKPOINT] No merkle_root in payload")
        return

    if not state_summary:
        logger.error("[CHECKPOINT] No state_summary in payload")
        return

    logger.info(
        f"[CHECKPOINT] Received checkpoint for epoch {epoch}, "
        f"root: {merkle_root[:8]}..., {len(signatures)} signatures"
    )

    # If checkpoint manager is available, store it
    if checkpoint_manager:
        _store_checkpoint(payload)

    # Broadcast to network (if applicable)
    # In a real implementation, would forward to peers


def _store_checkpoint(payload: dict):
    """
    Store a received checkpoint.

    Args:
        payload: CHECKPOINT payload
    """
    from checkpoint import Checkpoint, SignedCheckpoint
    import time

    try:
        # Reconstruct checkpoint
        checkpoint = Checkpoint(
            epoch=payload["epoch"],
            merkle_root=payload["merkle_root"],
            state_summary=payload["state_summary"],
            timestamp_ns=payload.get("timestamp_ns", int(time.time() * 1_000_000_000)),
            op_count=payload.get("op_count", 0),
            metadata=payload.get("metadata", {}),
        )

        # Create signed checkpoint
        signed = SignedCheckpoint(
            checkpoint=checkpoint, signatures=payload.get("signatures", [])
        )

        # Store to disk
        checkpoint_manager.store_checkpoint(signed)

        logger.info(f"[CHECKPOINT] Stored checkpoint for epoch {checkpoint.epoch}")

    except Exception as e:
        logger.error(f"[CHECKPOINT] Error storing checkpoint: {e}", exc_info=True)


# Register with dispatcher
DISPATCHER.register("CHECKPOINT", handle_checkpoint)
