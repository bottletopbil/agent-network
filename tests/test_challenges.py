"""
Unit tests for Challenge Protocol.

Tests:
- Challenge submission and validation
- Challenge window management
- Proof schema validation
- Invalid challenge rejection
"""

import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import time
from challenges.proofs import (
    ProofType,
    ProofSchema,
    MAX_PROOF_SIZE_BYTES,
    MAX_GAS_ESTIMATE,
)
from challenges.window import ChallengeWindow, DEFAULT_WINDOW_DURATION
import handlers.challenge


class TestProofValidation:
    """Test proof schema validation"""

    def test_valid_proof_schema(self):
        """Test valid proof schema passes validation"""
        proof = ProofSchema(
            proof_type=ProofType.SCHEMA_VIOLATION,
            evidence_hash="a" * 64,  # Valid SHA256 hex
            size_bytes=5000,
            gas_estimate=50000,
        )

        is_valid, error = proof.validate()
        assert is_valid
        assert error is None

    def test_proof_size_limit(self):
        """Test proof size limit enforcement"""
        # Exceeds max size
        proof = ProofSchema(
            proof_type=ProofType.OUTPUT_MISMATCH,
            evidence_hash="b" * 64,
            size_bytes=MAX_PROOF_SIZE_BYTES + 1,
            gas_estimate=10000,
        )

        is_valid, error = proof.validate()
        assert not is_valid
        assert "size" in error.lower()

    def test_proof_gas_limit(self):
        """Test gas limit enforcement"""
        # Exceeds max gas
        proof = ProofSchema(
            proof_type=ProofType.SEMANTIC_CONTRADICTION,
            evidence_hash="c" * 64,
            size_bytes=5000,
            gas_estimate=MAX_GAS_ESTIMATE + 1,
        )

        is_valid, error = proof.validate()
        assert not is_valid
        assert "gas" in error.lower()

    def test_invalid_evidence_hash(self):
        """Test invalid evidence hash rejection"""
        # Too short
        proof = ProofSchema(
            proof_type=ProofType.MISSING_CITATION,
            evidence_hash="short",
            size_bytes=1000,
            gas_estimate=10000,
        )

        is_valid, error = proof.validate()
        assert not is_valid
        assert "hash" in error.lower()

    def test_proof_serialization(self):
        """Test proof to_dict and from_dict"""
        proof = ProofSchema(
            proof_type=ProofType.POLICY_BREACH,
            evidence_hash="d" * 64,
            size_bytes=2000,
            gas_estimate=20000,
            metadata={"key": "value"},
        )

        # Serialize
        data = proof.to_dict()
        assert data["proof_type"] == ProofType.POLICY_BREACH.value
        assert data["evidence_hash"] == "d" * 64
        assert data["metadata"]["key"] == "value"

        # Deserialize
        proof2 = ProofSchema.from_dict(data)
        assert proof2.proof_type == proof.proof_type
        assert proof2.evidence_hash == proof.evidence_hash
        assert proof2.size_bytes == proof.size_bytes


class TestChallengeWindow:
    """Test challenge window management"""

    def test_create_window(self):
        """Test creating a challenge window"""
        db_path = Path(tempfile.mktemp())
        window_mgr = ChallengeWindow(db_path)

        window = window_mgr.create_window("task-1", duration=3600)

        assert window.task_id == "task-1"
        assert window.duration_seconds == 3600
        assert window.is_open()
        assert window.get_remaining_time() > 3590  # Should be close to 3600

    def test_window_default_duration(self):
        """Test default window duration (24 hours)"""
        db_path = Path(tempfile.mktemp())
        window_mgr = ChallengeWindow(db_path)

        window = window_mgr.create_window("task-2")

        assert window.duration_seconds == DEFAULT_WINDOW_DURATION
        assert window.duration_seconds == 24 * 60 * 60

    def test_window_expiration(self):
        """Test window expiration"""
        db_path = Path(tempfile.mktemp())
        window_mgr = ChallengeWindow(db_path)

        # Create window with 1 second duration
        window = window_mgr.create_window("task-3", duration=1)

        assert window.is_open()

        # Wait for expiration
        time.sleep(1.1)

        # Check if expired
        remaining = window_mgr.get_remaining_time("task-3")
        assert remaining == 0.0
        assert not window_mgr.is_window_open("task-3")

    def test_extend_window(self):
        """Test extending a challenge window"""
        db_path = Path(tempfile.mktemp())
        window_mgr = ChallengeWindow(db_path)

        # Create initial window
        window = window_mgr.create_window("task-4", duration=3600)
        original_duration = window.duration_seconds

        # Extend by 1 hour
        extended = window_mgr.extend_window("task-4", 3600)

        assert extended is not None
        assert extended.duration_seconds == original_duration + 3600
        assert extended.extended_count == 1

    def test_get_remaining_time(self):
        """Test getting remaining time"""
        db_path = Path(tempfile.mktemp())
        window_mgr = ChallengeWindow(db_path)

        window_mgr.create_window("task-5", duration=7200)

        remaining = window_mgr.get_remaining_time("task-5")
        assert remaining is not None
        assert 7190 < remaining <= 7200

    def test_nonexistent_window(self):
        """Test querying nonexistent window"""
        db_path = Path(tempfile.mktemp())
        window_mgr = ChallengeWindow(db_path)

        assert window_mgr.get_window("nonexistent") is None
        assert window_mgr.get_remaining_time("nonexistent") is None
        assert not window_mgr.is_window_open("nonexistent")


class TestChallengeSubmission:
    """Test challenge submission via handler"""

    @pytest.mark.asyncio
    async def test_challenge_submission(self):
        """Test valid challenge submission"""
        # Clear queue
        handlers.challenge.clear_challenge_queue()

        # Create challenge window
        db_path = Path(tempfile.mktemp())
        window_mgr = ChallengeWindow(db_path)
        window_mgr.create_window("task-100", duration=3600)

        # Inject window manager
        handlers.challenge.challenge_window = window_mgr

        # Create CHALLENGE envelope
        envelope = {
            "kind": "CHALLENGE",
            "thread_id": "test-thread",
            "lamport": 500,
            "sender_pk_b64": "challenger-alice",
            "payload": {
                "task_id": "task-100",
                "commit_id": "commit-abc",
                "proof_type": "SCHEMA_VIOLATION",
                "evidence_hash": "e" * 64,
                "bond_amount": 50,
                "size_bytes": 5000,
                "gas_estimate": 40000,
            },
        }

        # Handle challenge
        await handlers.challenge.handle_challenge(envelope)

        # Verify challenge was queued
        queued = handlers.challenge.get_queued_challenges()
        assert len(queued) == 1

        challenge = queued[0]
        assert challenge["task_id"] == "task-100"
        assert challenge["commit_id"] == "commit-abc"
        assert challenge["challenger_id"] == "challenger-alice"
        assert challenge["bond_amount"] == 50
        assert challenge["status"] == "queued"

    @pytest.mark.asyncio
    async def test_challenge_window_closed(self):
        """Test challenge rejected when window is closed"""
        handlers.challenge.clear_challenge_queue()

        # Create very short window (1 second) and wait for expiration
        db_path = Path(tempfile.mktemp())
        window_mgr = ChallengeWindow(db_path)
        window_mgr.create_window("task-101", duration=1)

        # Wait for window to expire
        time.sleep(1.1)

        handlers.challenge.challenge_window = window_mgr

        envelope = {
            "kind": "CHALLENGE",
            "thread_id": "test-thread",
            "lamport": 501,
            "sender_pk_b64": "challenger-bob",
            "payload": {
                "task_id": "task-101",
                "commit_id": "commit-xyz",
                "proof_type": "OUTPUT_MISMATCH",
                "evidence_hash": "f" * 64,
                "bond_amount": 100,
                "size_bytes": 3000,
                "gas_estimate": 30000,
            },
        }

        await handlers.challenge.handle_challenge(envelope)

        # Challenge should not be queued
        queued = handlers.challenge.get_queued_challenges()
        assert len(queued) == 0

    @pytest.mark.asyncio
    async def test_invalid_challenge_rejected(self):
        """Test various invalid challenges are rejected"""
        handlers.challenge.clear_challenge_queue()

        db_path = Path(tempfile.mktemp())
        window_mgr = ChallengeWindow(db_path)
        window_mgr.create_window("task-102", duration=3600)
        handlers.challenge.challenge_window = window_mgr

        # Missing task_id
        envelope1 = {
            "kind": "CHALLENGE",
            "thread_id": "test-thread",
            "lamport": 502,
            "sender_pk_b64": "challenger-charlie",
            "payload": {
                "commit_id": "commit-123",
                "proof_type": "POLICY_BREACH",
                "evidence_hash": "g" * 64,
                "bond_amount": 25,
                "size_bytes": 1000,
                "gas_estimate": 10000,
            },
        }

        await handlers.challenge.handle_challenge(envelope1)
        assert len(handlers.challenge.get_queued_challenges()) == 0

        # Invalid proof type
        envelope2 = {
            "kind": "CHALLENGE",
            "thread_id": "test-thread",
            "lamport": 503,
            "sender_pk_b64": "challenger-diane",
            "payload": {
                "task_id": "task-102",
                "commit_id": "commit-456",
                "proof_type": "INVALID_TYPE",
                "evidence_hash": "h" * 64,
                "bond_amount": 30,
                "size_bytes": 2000,
                "gas_estimate": 20000,
            },
        }

        await handlers.challenge.handle_challenge(envelope2)
        assert len(handlers.challenge.get_queued_challenges()) == 0

        # Proof too large
        envelope3 = {
            "kind": "CHALLENGE",
            "thread_id": "test-thread",
            "lamport": 504,
            "sender_pk_b64": "challenger-eve",
            "payload": {
                "task_id": "task-102",
                "commit_id": "commit-789",
                "proof_type": "SEMANTIC_CONTRADICTION",
                "evidence_hash": "i" * 64,
                "bond_amount": 40,
                "size_bytes": MAX_PROOF_SIZE_BYTES + 1000,
                "gas_estimate": 50000,
            },
        }

        await handlers.challenge.handle_challenge(envelope3)
        assert len(handlers.challenge.get_queued_challenges()) == 0

        # Invalid bond
        envelope4 = {
            "kind": "CHALLENGE",
            "thread_id": "test-thread",
            "lamport": 505,
            "sender_pk_b64": "challenger-frank",
            "payload": {
                "task_id": "task-102",
                "commit_id": "commit-101",
                "proof_type": "MISSING_CITATION",
                "evidence_hash": "j" * 64,
                "bond_amount": 0,  # Invalid: must be > 0
                "size_bytes": 4000,
                "gas_estimate": 35000,
            },
        }

        await handlers.challenge.handle_challenge(envelope4)
        assert len(handlers.challenge.get_queued_challenges()) == 0
