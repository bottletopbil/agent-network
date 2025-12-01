"""
Verifier Agent: listens for COMMIT, verifies artifacts, and attests/finalizes.

This agent:
- Subscribes to thread.*.worker (to see commits)
- Verifies artifacts exist in CAS
- Publishes ATTEST with verdict
- For K=1 bootstrap: immediately triggers FINALIZE
"""

import sys
import os
import uuid
import base64
import asyncio

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent import BaseAgent
from envelope import make_envelope, sign_envelope
from bus import publish_envelope
from crypto import load_verifier
import cas


class VerifierAgent(BaseAgent):
    """Agent that verifies artifacts and attests to their validity"""

    async def on_envelope(self, envelope: dict):
        """Handle incoming envelopes"""
        kind = envelope.get("kind")

        if kind == "COMMIT":
            await self.handle_commit(envelope)

    async def handle_commit(self, envelope: dict):
        """Verify commit and publish attestation"""
        thread_id = envelope["thread_id"]
        payload = envelope["payload"]

        task_id = payload.get("task_id")
        artifact_hash = payload.get("artifact_hash")

        print(f"[VERIFIER] Received COMMIT for task {task_id}")

        # 1. Verify artifact exists in CAS
        if not cas.has_blob(artifact_hash):
            print(f"[VERIFIER] ❌ Artifact {artifact_hash} NOT FOUND in CAS")
            # In a real system, we might publish ATTEST(verdict="rejected")
            return

        print(f"[VERIFIER] ✓ Artifact {artifact_hash} verified in CAS")

        # 2. Publish ATTEST
        await self.publish_attest(thread_id, envelope)

        # 3. Bootstrap: Trigger FINALIZE (K=1)
        # In a full system, this would wait for consensus
        await self.publish_finalize(thread_id, task_id)

    async def publish_attest(self, thread_id: str, commit_envelope: dict):
        """Publish ATTEST envelope"""
        commit_payload = commit_envelope["payload"]
        commit_id = commit_envelope["id"]
        task_id = commit_payload.get("task_id")

        attest_payload = {
            "commit_id": commit_id,
            "task_id": task_id,
            "verdict": "approved",
            "attestation_id": str(uuid.uuid4()),
        }

        env = make_envelope(
            kind="ATTEST",
            thread_id=thread_id,
            sender_pk_b64=self.public_key_b64,
            payload=attest_payload,
        )

        signed = sign_envelope(env)
        subject = f"thread.{thread_id}.verifier"

        await publish_envelope(thread_id, subject, signed)
        print(f"[VERIFIER] Published ATTEST for task {task_id}")

    async def publish_finalize(self, thread_id: str, task_id: str):
        """Publish FINALIZE envelope"""
        finalize_payload = {
            "task_id": task_id,
            "metadata": {"reason": "bootstrap_k1", "verifier": self.agent_id},
        }

        env = make_envelope(
            kind="FINALIZE",
            thread_id=thread_id,
            sender_pk_b64=self.public_key_b64,
            payload=finalize_payload,
        )

        signed = sign_envelope(env)
        subject = f"thread.{thread_id}.verifier"

        await publish_envelope(thread_id, subject, signed)
        print(f"[VERIFIER] Published FINALIZE for task {task_id}")


if __name__ == "__main__":
    print("=" * 60)
    print("Starting Verifier Agent")
    print("=" * 60)

    agent = VerifierAgent(
        agent_id="verifier-1",
        public_key_b64=base64.b64encode(bytes(load_verifier())).decode(),
    )

    print(f"Agent ID: {agent.agent_id}")
    # Subscribe to worker (commits)
    print("Subscribing to: thread.*.worker")

    asyncio.run(agent.run("demo-thread-v", "thread.*.worker"))
