"""
CHALLENGE Handler: Process challenge submissions against task results.

Validates:
- Challenge window is still open
- Proof schema is valid
- Challenger bond is posted (via ledger)
- Queues challenge for verification
"""

import uuid
import time
import os
from pathlib import Path
from typing import Optional

from challenges.proofs import (
    ProofType,
    ProofSchema,
)
from challenges.window import ChallengeWindow
from challenges.bonds import BondCalculator, ComplexityLevel
from challenges.abuse_detection import AbuseDetector
from verbs import DISPATCHER


# Module-level state (injected at startup)
challenge_window: Optional[ChallengeWindow] = None
ledger = None  # Will be injected from economics.ledger
bond_calculator = BondCalculator()
abuse_detector = AbuseDetector()

# Initialize challenge window manager
STATE_DIR = Path(os.getenv("SWARM_STATE_DIR", ".state"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
_window_db_path = STATE_DIR / "challenge_windows.db"


def _ensure_challenge_window():
    """Lazy initialization of challenge window manager"""
    global challenge_window
    if challenge_window is None:
        challenge_window = ChallengeWindow(_window_db_path)
    return challenge_window


# Simple in-memory queue for challenges (would be Redis/queue in production)
_challenge_queue = []


async def handle_challenge(envelope: dict):
    """
    Process CHALLENGE envelope:
    1. Check abuse and rate limits
    2. Validate challenge window is still open
    3. Calculate required bond
    4. Validate challenger has sufficient balance
    5. Validate proof schema
    6. Create bond escrow
    7. Queue challenge for verification

    Challenge payload:
    - task_id: Task being challenged
    - commit_id: Commit being challenged
    - proof_type: Type of proof (ProofType enum value)
    - evidence_hash: Hash of evidence in CAS
    - complexity: Complexity level (SIMPLE/MODERATE/COMPLEX)
    - size_bytes: Size of proof
    - gas_estimate: Estimated gas for verification
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    challenger_id = envelope["sender_pk_b64"]
    lamport = envelope["lamport"]

    # Extract challenge details
    task_id = payload.get("task_id")
    commit_id = payload.get("commit_id")
    proof_type_str = payload.get("proof_type")
    evidence_hash = payload.get("evidence_hash")
    complexity_str = payload.get("complexity", "SIMPLE")
    size_bytes = payload.get("size_bytes", 0)
    gas_estimate = payload.get("gas_estimate", 0)

    # Validate required fields
    if not task_id:
        print(f"[CHALLENGE] ERROR: Missing task_id")
        return

    if not commit_id:
        print(f"[CHALLENGE] ERROR: Missing commit_id")
        return

    if not proof_type_str:
        print(f"[CHALLENGE] ERROR: Missing proof_type")
        return

    if not evidence_hash:
        print(f"[CHALLENGE] ERROR: Missing evidence_hash")
        return

    # Validate proof type
    try:
        proof_type = ProofType(proof_type_str)
    except ValueError:
        print(f"[CHALLENGE] ERROR: Invalid proof_type '{proof_type_str}'")
        return

    # Validate complexity level
    try:
        complexity = ComplexityLevel[complexity_str]
    except (KeyError, ValueError):
        print(f"[CHALLENGE] ERROR: Invalid complexity '{complexity_str}'")
        return

    # Check abuse and rate limits
    is_allowed, error_msg = abuse_detector.check_rate_limit(challenger_id)
    if not is_allowed:
        print(f"[CHALLENGE] ERROR: {error_msg}")
        return

    is_spam, spam_msg = abuse_detector.check_spam_pattern(challenger_id)
    if is_spam:
        print(f"[CHALLENGE] WARNING: {spam_msg}")
        # Could choose to reject or just warn

    # Check if low quality challenger
    if abuse_detector.is_low_quality_challenger(challenger_id):
        reputation = abuse_detector.calculate_reputation_impact(challenger_id)
        print(
            f"[CHALLENGE] WARNING: Low quality challenger (reputation: {reputation:.2f})"
        )
        # Could require higher bond or reject

    # Record challenge attempt
    abuse_detector.record_challenge(challenger_id)

    # Check challenge window
    window_manager = _ensure_challenge_window()

    if not window_manager.is_window_open(task_id):
        print(f"[CHALLENGE] ERROR: Challenge window closed for task {task_id}")
        return

    remaining_time = window_manager.get_remaining_time(task_id)
    print(
        f"[CHALLENGE] Challenge window for task {task_id} has {remaining_time:.1f}s remaining"
    )

    # Calculate required bond
    required_bond = bond_calculator.calculate_bond(proof_type, complexity)
    print(
        f"[CHALLENGE] Required bond: {required_bond} credits ({proof_type.value}, {complexity.name})"
    )

    # Validate challenger has sufficient balance
    if ledger:
        challenger_balance = ledger.get_balance(challenger_id)
        if challenger_balance < required_bond:
            print(
                f"[CHALLENGE] ERROR: Insufficient balance: {challenger_balance} < {required_bond}"
            )
            return
        print(f"[CHALLENGE] Balance verified: {challenger_balance} credits")
    else:
        print(f"[CHALLENGE] WARNING: No ledger, skipping balance check")

    # Create and validate proof schema
    proof = ProofSchema(
        proof_type=proof_type,
        evidence_hash=evidence_hash,
        size_bytes=size_bytes,
        gas_estimate=gas_estimate,
        metadata={
            "task_id": task_id,
            "commit_id": commit_id,
            "challenger_id": challenger_id,
            "complexity": complexity.name,
        },
    )

    is_valid, error_msg = proof.validate()
    if not is_valid:
        print(f"[CHALLENGE] ERROR: Proof validation failed: {error_msg}")
        return

    print(
        f"[CHALLENGE] Proof validated: {proof_type.value}, size={size_bytes}B, gas={gas_estimate}"
    )

    # Create bond escrow
    escrow_id = f"challenge_bond_{uuid.uuid4()}"
    if ledger:
        try:
            ledger.escrow(challenger_id, required_bond, escrow_id)
            print(
                f"[CHALLENGE] Escrowed {required_bond} credits, escrow_id: {escrow_id}"
            )
        except Exception as e:
            print(f"[CHALLENGE] ERROR: Failed to escrow bond: {e}")
            return
    else:
        print(f"[CHALLENGE] WARNING: No ledger, bond not escrowed")

    # Create challenge record
    challenge_id = str(uuid.uuid4())
    challenge_record = {
        "challenge_id": challenge_id,
        "task_id": task_id,
        "commit_id": commit_id,
        "challenger_id": challenger_id,
        "proof": proof.to_dict(),
        "bond_amount": required_bond,
        "escrow_id": escrow_id,
        "complexity": complexity.name,
        "lamport": lamport,
        "thread_id": thread_id,
        "status": "queued",
        "submitted_at_ns": time.time_ns(),
    }

    # Queue challenge for verification
    _challenge_queue.append(challenge_record)

    print(f"[CHALLENGE] Challenge {challenge_id} queued for task {task_id}")
    print(
        f"[CHALLENGE] Challenger: {challenger_id}, Bond: {required_bond}, Type: {proof_type.value}"
    )
    print(f"[CHALLENGE] Queue size: {len(_challenge_queue)}")

    # Note: In production, this would publish to message bus for verifiers to pick up


def get_queued_challenges() -> list:
    """Get all queued challenges (for testing/debugging)"""
    return list(_challenge_queue)


def clear_challenge_queue():
    """Clear challenge queue (for testing)"""
    global _challenge_queue
    _challenge_queue = []


# Register with dispatcher
DISPATCHER.register("CHALLENGE", handle_challenge)
