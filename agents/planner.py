"""
Planner Agent: listens for NEED, creates proposals.

This agent:
- Subscribes to thread.*.need subject pattern
- Receives NEED envelopes
- Creates simple single-worker proposals
- Publishes PROPOSE envelopes back to the bus
"""

import sys
import os
import uuid
import base64
import asyncio

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent import BaseAgent
from envelope import make_envelope, sign_envelope
from bus import publish_envelope
from crypto import load_verifier


class PlannerAgent(BaseAgent):
    """Agent that creates execution plans in response to NEED messages"""
    
    async def on_envelope(self, envelope: dict):
        """Handle incoming envelopes - filter for NEED messages"""
        kind = envelope.get("kind")
        
        if kind == "NEED":
            await self.handle_need(envelope)
    
    async def handle_need(self, envelope: dict):
        """Create a simple plan proposal for a NEED"""
        thread_id = envelope["thread_id"]
        need_payload = envelope["payload"]
        
        print(f"[PLANNER] Received NEED in thread {thread_id}")
        print(f"[PLANNER] NEED payload: {need_payload}")
        
        # Simple proposal: one worker task
        proposal = {
            "plan": [
                {
                    "task_id": str(uuid.uuid4()),
                    "type": "worker",
                    "input": need_payload
                }
            ]
        }
        
        # Create PROPOSE envelope
        env = make_envelope(
            kind="PROPOSE",
            thread_id=thread_id,
            sender_pk_b64=self.public_key_b64,
            payload=proposal
        )
        
        # Sign the envelope
        signed = sign_envelope(env)
        
        # Publish to planner subject
        subject = f"thread.{thread_id}.planner"
        
        await publish_envelope(thread_id, subject, signed)
        print(f"[PLANNER] Proposed plan for thread {thread_id}")
        print(f"[PLANNER] Plan: {proposal}")


# Run as standalone process
if __name__ == "__main__":
    print("=" * 60)
    print("Starting Planner Agent")
    print("=" * 60)
    
    # Initialize agent with unique ID and public key from environment
    agent = PlannerAgent(
        agent_id="planner-1",
        public_key_b64=base64.b64encode(bytes(load_verifier())).decode()
    )
    
    print(f"Agent ID: {agent.agent_id}")
    print(f"Subscribing to: thread.*.need")
    print("Waiting for NEED messages...")
    print("=" * 60)
    
    # Run agent - subscribe to all NEED messages on any thread
    asyncio.run(agent.run("demo-thread", "thread.*.need"))
