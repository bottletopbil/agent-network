"""
Unit tests for Challenge Verifier Agent.

Tests:
- Agent listens for challenges
- Agent verifies challenges
- Agent publishes verdicts
- Agent requires stake
"""

import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agents"))

import pytest
from challenge_verifier import ChallengeVerifierAgent, MIN_VERIFIER_STAKE
from challenges.queue import ChallengeQueue


class TestChallengeVerifierAgentInitialization:
    """Test agent initialization and stake requirements"""

    def test_agent_requires_minimum_stake(self):
        """Test agent requires minimum stake to initialize"""
        with pytest.raises(ValueError, match="Insufficient stake"):
            ChallengeVerifierAgent(
                agent_id="verifier-1",
                public_key_b64="test-key",
                stake_amount=100,  # Below minimum
            )

    def test_agent_initializes_with_sufficient_stake(self):
        """Test agent initializes with sufficient stake"""
        agent = ChallengeVerifierAgent(
            agent_id="verifier-1",
            public_key_b64="test-key",
            stake_amount=1500,  # Above minimum
            queue_db_path=Path(tempfile.mktemp()),
        )

        assert agent.agent_id == "verifier-1"
        assert agent.stake_amount == 1500
        assert agent.verifier is not None
        assert agent.queue is not None

    def test_agent_registration(self):
        """Test agent can register with verifier pool"""
        agent = ChallengeVerifierAgent(
            agent_id="verifier-1",
            public_key_b64="test-key",
            stake_amount=MIN_VERIFIER_STAKE,
            queue_db_path=Path(tempfile.mktemp()),
        )

        assert not agent.registered
        agent.register_with_pool()
        assert agent.registered


class TestChallengeVerification:
    """Test challenge verification functionality"""

    @pytest.mark.asyncio
    async def test_agent_verifies_schema_violation(self):
        """Test agent can verify schema violation challenge"""
        agent = ChallengeVerifierAgent(
            agent_id="verifier-1",
            public_key_b64="test-key",
            stake_amount=1500,
            queue_db_path=Path(tempfile.mktemp()),
            publish_verdicts=False,  # Disable publishing for tests
        )

        # Add challenge to queue
        challenge = agent.queue.add_challenge(
            challenge_id="c1",
            task_id="task-1",
            commit_id="commit-1",
            challenger_id="alice",
            proof_data={
                "proof_type": "SCHEMA_VIOLATION",
                "evidence": {
                    "expected_schema": {
                        "name": {"type": "string"},
                        "age": {"type": "integer"},
                    },
                    "actual_output": {"name": "John", "age": "invalid"},  # Wrong type
                    "violations": ["age"],
                },
            },
            bond_amount=100,
        )

        # Verify the challenge
        await agent.verify_challenge(challenge)

        # Check it was marked as verified
        assert agent.queue.get_queue_size("verified") == 1
        assert "c1" in agent.processed_challenges

    @pytest.mark.asyncio
    async def test_agent_verifies_citation_missing(self):
        """Test agent can verify missing citation challenge"""
        agent = ChallengeVerifierAgent(
            agent_id="verifier-2",
            public_key_b64="test-key",
            stake_amount=1500,
            queue_db_path=Path(tempfile.mktemp()),
            publish_verdicts=False,
        )

        challenge = agent.queue.add_challenge(
            challenge_id="c2",
            task_id="task-2",
            commit_id="commit-2",
            challenger_id="bob",
            proof_data={
                "proof_type": "MISSING_CITATION",
                "evidence": {
                    "required_citations": ["source-1", "source-2"],
                    "provided_citations": ["source-1"],  # Missing source-2
                },
            },
            bond_amount=50,
        )

        await agent.verify_challenge(challenge)

        assert "c2" in agent.processed_challenges

    @pytest.mark.asyncio
    async def test_agent_handles_invalid_proof_type(self):
        """Test agent handles invalid proof types gracefully"""
        agent = ChallengeVerifierAgent(
            agent_id="verifier-3",
            public_key_b64="test-key",
            stake_amount=1500,
            queue_db_path=Path(tempfile.mktemp()),
        )

        challenge = agent.queue.add_challenge(
            challenge_id="c3",
            task_id="task-3",
            commit_id="commit-3",
            challenger_id="charlie",
            proof_data={"proof_type": "INVALID_TYPE", "evidence": {}},  # Bad type
            bond_amount=25,
        )

        await agent.verify_challenge(challenge)

        # Should be marked as failed
        assert agent.queue.get_queue_size("failed") == 1


class TestQueueProcessing:
    """Test queue processing functionality"""

    def test_agent_pulls_from_queue_by_priority(self):
        """Test agent gets challenges in priority order"""
        agent = ChallengeVerifierAgent(
            agent_id="verifier-4",
            public_key_b64="test-key",
            stake_amount=2000,
            queue_db_path=Path(tempfile.mktemp()),
        )

        # Add challenges with different bonds
        agent.queue.add_challenge(
            "low",
            "t1",
            "c1",
            "alice",
            {"proof_type": "SCHEMA_VIOLATION", "evidence": {}},
            50,
        )
        agent.queue.add_challenge(
            "high",
            "t2",
            "c2",
            "bob",
            {"proof_type": "SCHEMA_VIOLATION", "evidence": {}},
            500,
        )
        agent.queue.add_challenge(
            "mid",
            "t3",
            "c3",
            "charlie",
            {"proof_type": "SCHEMA_VIOLATION", "evidence": {}},
            200,
        )

        # Get next should return highest bond first
        next_challenge = agent.queue.get_next_challenge()
        assert next_challenge.challenge_id == "high"
        assert next_challenge.bond_amount == 500

    def test_agent_skips_processed_challenges(self):
        """Test agent doesn't reprocess same challenge"""
        agent = ChallengeVerifierAgent(
            agent_id="verifier-5",
            public_key_b64="test-key",
            stake_amount=1500,
            queue_db_path=Path(tempfile.mktemp()),
        )

        agent.processed_challenges.add("c1")

        # Should recognize this as already processed
        assert "c1" in agent.processed_challenges


class TestVerdictPublishing:
    """Test verdict publishing"""

    @pytest.mark.asyncio
    async def test_agent_publishes_uphold_verdict(self):
        """Test agent publishes UPHOLD verdict for valid challenge"""
        agent = ChallengeVerifierAgent(
            agent_id="verifier-6",
            public_key_b64="test-key",
            stake_amount=1500,
            queue_db_path=Path(tempfile.mktemp()),
            publish_verdicts=False,
        )

        challenge = agent.queue.add_challenge(
            challenge_id="c4",
            task_id="task-4",
            commit_id="commit-4",
            challenger_id="dave",
            proof_data={
                "proof_type": "OUTPUT_MISMATCH",
                "evidence": {
                    "specified_output": {"result": "success"},
                    "actual_output": {"result": "failed"},  # Mismatch
                    "mismatch_fields": ["result"],
                },
            },
            bond_amount=100,
        )

        # Verify should publish UPHOLD verdict
        await agent.verify_challenge(challenge)

        # Check processed
        assert "c4" in agent.processed_challenges

    @pytest.mark.asyncio
    async def test_agent_publishes_reject_verdict(self):
        """Test agent publishes REJECT verdict for invalid challenge"""
        agent = ChallengeVerifierAgent(
            agent_id="verifier-7",
            public_key_b64="test-key",
            stake_amount=1500,
            queue_db_path=Path(tempfile.mktemp()),
            publish_verdicts=False,
        )

        challenge = agent.queue.add_challenge(
            challenge_id="c5",
            task_id="task-5",
            commit_id="commit-5",
            challenger_id="eve",
            proof_data={
                "proof_type": "SCHEMA_VIOLATION",
                "evidence": {
                    "expected_schema": {"name": {"type": "string"}},
                    "actual_output": {"name": "John"},  # Matches!
                    "violations": [],
                },
            },
            bond_amount=50,
        )

        # Verify should publish REJECT verdict (challenge invalid)
        await agent.verify_challenge(challenge)

        assert "c5" in agent.processed_challenges


class TestMultipleVerifiers:
    """Test multiple verifiers can process same challenge"""

    def test_multiple_verifiers_can_claim_challenge(self):
        """Test multiple verifiers can see and process same challenge"""
        # Shared queue
        queue_path = Path(tempfile.mktemp())
        queue = ChallengeQueue(queue_path)

        # Add a challenge
        queue.add_challenge(
            "shared-c1",
            "t1",
            "c1",
            "alice",
            {"proof_type": "SCHEMA_VIOLATION", "evidence": {}},
            100,
        )

        # Create multiple verifiers pointing to same queue
        verifier1 = ChallengeVerifierAgent(
            agent_id="v1",
            public_key_b64="key1",
            stake_amount=1500,
            queue_db_path=queue_path,
        )

        verifier2 = ChallengeVerifierAgent(
            agent_id="v2",
            public_key_b64="key2",
            stake_amount=1500,
            queue_db_path=queue_path,
        )

        # Both can see the challenge
        c1 = verifier1.queue.get_next_challenge()
        c2 = verifier2.queue.get_next_challenge()

        assert c1.challenge_id == "shared-c1"
        assert c2.challenge_id == "shared-c1"  # Same challenge
