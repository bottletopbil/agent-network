"""
Challenge Verifier Agent: Automatically processes challenges from the queue.

This agent:
- Listens for CHALLENGE messages
- Pulls challenges from priority queue
- Verifies proofs using ChallengeVerifier
- Publishes verdicts (UPHOLD/REJECT)
- Requires stake to participate
"""

import sys
import os
import uuid
import base64
import asyncio
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent import BaseAgent
from envelope import make_envelope, sign_envelope
from bus import publish_envelope
from crypto import load_verifier
from challenges.verification import ChallengeVerifier
from challenges.queue import ChallengeQueue
from challenges.proofs import ProofType
from challenges.escalation import VerifierVerdict
import cas


# Minimum stake required to be a challenge verifier (in credits)
MIN_VERIFIER_STAKE = 1000


class ChallengeVerifierAgent(BaseAgent):
    """
    Agent that verifies challenge proofs and publishes verdicts.
    
    Requires:
    - Minimum stake of 1000 credits
    - Registration with verifier pool
    - Subscription to challenge topics
    """
    
    def __init__(
        self,
        agent_id: str,
        public_key_b64: str,
        stake_amount: int = 0,
        queue_db_path: Path = None,
        publish_verdicts: bool = True
    ):
        super().__init__(agent_id, public_key_b64)
        
        # Stake requirement
        self.stake_amount = stake_amount
        if self.stake_amount < MIN_VERIFIER_STAKE:
            raise ValueError(f"Insufficient stake: {stake_amount} < {MIN_VERIFIER_STAKE}")
        
        # Initialize verification components
        self.verifier = ChallengeVerifier()
        
        # Challenge queue
        if queue_db_path is None:
            queue_db_path = Path(".state/challenge_queue.db")
            queue_db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.queue = ChallengeQueue(queue_db_path)
        
        # Track processed challenges
        self.processed_challenges = set()
        
        # Verifier pool registration flag
        self.registered = False
        
        # Publishing flag (can disable for testing)
        self.publish_verdicts = publish_verdicts
        
        print(f"[CHALLENGE_VERIFIER] Initialized with stake: {stake_amount} credits")
    
    def register_with_pool(self):
        """Register this verifier with the pool"""
        # In production, this would:
        # 1. Submit stake to escrow
        # 2. Register public key with pool contract
        # 3. Receive pool membership confirmation
        self.registered = True
        print(f"[CHALLENGE_VERIFIER] Registered with verifier pool, stake: {self.stake_amount}")
    
    async def on_envelope(self, envelope: dict):
        """Handle incoming envelopes"""
        kind = envelope.get("kind")
        
        if kind == "CHALLENGE":
            await self.handle_challenge_message(envelope)
    
    async def handle_challenge_message(self, envelope: dict):
        """
        Handle incoming CHALLENGE message.
        
        This could be used to notify verifiers of new challenges,
        but the main work happens via queue polling.
        """
        payload = envelope["payload"]
        challenge_id = payload.get("challenge_id")
        
        if challenge_id:
            print(f"[CHALLENGE_VERIFIER] Notified of challenge {challenge_id}")
    
    async def process_queue(self):
        """
        Main processing loop: pull challenges from queue and verify them.
        
        This should run continuously in the background.
        """
        while True:
            try:
                # Get next challenge from queue (highest priority)
                challenge = self.queue.get_next_challenge()
                
                if challenge is None:
                    # No challenges available, wait a bit
                    await asyncio.sleep(2)
                    continue
                
                # Check if already processed
                if challenge.challenge_id in self.processed_challenges:
                    await asyncio.sleep(0.1)
                    continue
                
                # Mark as verifying
                self.queue.mark_verifying(challenge.challenge_id)
                
                # Verify the challenge
                await self.verify_challenge(challenge)
                
                # Mark as processed
                self.processed_challenges.add(challenge.challenge_id)
                
            except Exception as e:
                print(f"[CHALLENGE_VERIFIER] Error processing queue: {e}")
                await asyncio.sleep(1)
    
    async def verify_challenge(self, challenge):
        """
        Verify a challenge and publish verdict.
        
        Args:
            challenge: QueuedChallenge object
        """
        challenge_id = challenge.challenge_id
        task_id = challenge.task_id
        commit_id = challenge.commit_id
        proof_data = challenge.proof_data
        
        print(f"[CHALLENGE_VERIFIER] Verifying challenge {challenge_id}")
        print(f"[CHALLENGE_VERIFIER] Task: {task_id}, Commit: {commit_id}")
        
        # Extract proof type
        proof_type_str = proof_data.get('proof_type')
        if not proof_type_str:
            print(f"[CHALLENGE_VERIFIER] ERROR: No proof_type in challenge")
            self.queue.mark_failed(challenge_id, "Missing proof_type")
            return
        
        try:
            proof_type = ProofType(proof_type_str)
        except ValueError:
            print(f"[CHALLENGE_VERIFIER] ERROR: Invalid proof_type: {proof_type_str}")
            self.queue.mark_failed(challenge_id, f"Invalid proof_type: {proof_type_str}")
            return
        
        # Get evidence from CAS (if evidence_hash provided)
        evidence_hash = proof_data.get('evidence_hash')
        if evidence_hash and cas.has_blob(evidence_hash):
            evidence_data = cas.get_json(evidence_hash)
        else:
            # Use proof_data as evidence
            evidence_data = proof_data.get('evidence', {})
        
        # Run verification
        result = self.verifier.verify_proof(proof_type, evidence_data)
        
        print(f"[CHALLENGE_VERIFIER] Verification result: {result.is_valid}")
        print(f"[CHALLENGE_VERIFIER] Gas used: {result.gas_used}")
        print(f"[CHALLENGE_VERIFIER] Reason: {result.reason}")
        
        # Create verdict
        verdict = VerifierVerdict(
            verifier_id=self.agent_id,
            is_valid=result.is_valid,
            confidence=0.9,  # High confidence for deterministic verification
            reasoning=result.reason
        )
        
        # Mark in queue
        self.queue.mark_verified(challenge_id, result.to_dict())
        
        # Publish verdict (skip if disabled for testing)
        if self.publish_verdicts:
            await self.publish_verdict(
                challenge_id=challenge_id,
                task_id=task_id,
                commit_id=commit_id,
                verdict=verdict,
                verification_result=result
            )
        else:
            print(f"[CHALLENGE_VERIFIER] Skipping verdict publish (test mode)")
        
        # Mark as processed
        self.processed_challenges.add(challenge_id)
    
    async def publish_verdict(
        self,
        challenge_id: str,
        task_id: str,
        commit_id: str,
        verdict: VerifierVerdict,
        verification_result
    ):
        """
        Publish verdict envelope.
        
        Args:
            challenge_id: Challenge being verified
            task_id: Task that was challenged
            commit_id: Commit that was challenged
            verdict: Verifier verdict
            verification_result: Full verification result
        """
        verdict_payload = {
            "challenge_id": challenge_id,
            "task_id": task_id,
            "commit_id": commit_id,
            "verifier_id": self.agent_id,
            "verdict": "UPHOLD" if verdict.is_valid else "REJECT",
            "confidence": verdict.confidence,
            "reasoning": verdict.reasoning,
            "gas_used": verification_result.gas_used,
            "evidence": verification_result.evidence
        }
        
        env = make_envelope(
            kind="CHALLENGE_VERDICT",
            thread_id=f"challenge_{challenge_id}",
            sender_pk_b64=self.public_key_b64,
            payload=verdict_payload
        )
        
        signed = sign_envelope(env)
        subject = f"challenge.{challenge_id}.verdict"
        
        await publish_envelope(f"challenge_{challenge_id}", subject, signed)
        
        verdict_str = "UPHELD" if verdict.is_valid else "REJECTED"
        print(f"[CHALLENGE_VERIFIER] Published verdict: {verdict_str} for challenge {challenge_id}")


if __name__ == "__main__":
    print("=" * 60)
    print("Starting Challenge Verifier Agent")
    print("=" * 60)
    
    # Create agent with stake
    agent = ChallengeVerifierAgent(
        agent_id="challenge-verifier-1",
        public_key_b64=base64.b64encode(bytes(load_verifier())).decode(),
        stake_amount=1500  # 1500 credits staked
    )
    
    # Register with pool
    agent.register_with_pool()
    
    print(f"Agent ID: {agent.agent_id}")
    print(f"Stake: {agent.stake_amount} credits")
    print("Subscribing to: challenge.* ")
    
    async def main():
        # Run both queue processing and message listening
        await asyncio.gather(
            agent.process_queue(),  # Process challenges from queue
            agent.run("challenges", "challenge.*")  # Listen for challenge notifications
        )
    
    asyncio.run(main())
