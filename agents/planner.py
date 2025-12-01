"""
Planner Agent: listens for NEED, submits competitive bids.

This agent:
- Subscribes to thread.*.need subject pattern
- Receives NEED envelopes
- Calculates cost and ETA
- Submits competitive bids
- Tracks bid history
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
from auction.agent_integration import BidSubmitter
from auction.backoff import RandomizedBackoff


class PlannerAgent(BaseAgent):
    """Agent that submits competitive bids in response to NEED messages"""

    def __init__(self, agent_id: str, public_key_b64: str, auction_manager=None):
        super().__init__(agent_id, public_key_b64)

        # Bidding configuration
        self.reputation = 0.8  # Fixed for now
        self.capabilities = ["planning", "task_decomposition"]
        self.bid_submitter = BidSubmitter(agent_id, self.reputation, self.capabilities)
        self.backoff = RandomizedBackoff()
        self.auction_manager = auction_manager  # For direct integration

    async def on_envelope(self, envelope: dict):
        """Handle incoming envelopes - filter for NEED messages"""
        kind = envelope.get("kind")

        if kind == "NEED":
            await self.handle_need(envelope)

    def can_handle(self, payload: dict) -> bool:
        """Determine if agent can handle this task"""
        task_type = payload.get("task_type", "generic")
        # Can handle planning and generic tasks
        return task_type in ["planning", "generic", "worker"]

    async def handle_need(self, envelope: dict):
        """Evaluate task and submit competitive bid"""
        thread_id = envelope["thread_id"]
        need_payload = envelope["payload"]
        task_id = envelope.get("task_id", str(uuid.uuid4()))

        print(f"[PLANNER] Received NEED in thread {thread_id}")

        # Check if can handle
        if not self.can_handle(need_payload):
            print(f"[PLANNER] Cannot handle task type: {need_payload.get('task_type')}")
            return

        # Create bid using helper
        bid = self.bid_submitter.create_bid(need_payload)

        print(f"[PLANNER] Calculated bid: cost={bid['cost']}, eta={bid['eta']}s")

        # Create proposal with plan
        proposal = {
            "cost": bid["cost"],
            "eta": bid["eta"],
            "reputation": bid["reputation"],
            "capabilities": bid["capabilities"],
            "proposal_id": bid["proposal_id"],
            "plan": [
                {"task_id": str(uuid.uuid4()), "type": "worker", "input": need_payload}
            ],
        }

        # Submit bid directly to auction manager if available
        if self.auction_manager:
            success = self.auction_manager.accept_bid(task_id, self.agent_id, proposal)

            if success:
                print(f"[PLANNER] Bid accepted for task {task_id}")
                self.bid_submitter.record_bid(task_id, bid)
            else:
                print(f"[PLANNER] Bid rejected for task {task_id}")
                # Apply backoff for retry
                delay = self.backoff.next()
                print(f"[PLANNER] Backing off for {delay:.2f}s")
                await asyncio.sleep(delay)
        else:
            # Fallback: publish PROPOSE envelope
            env = make_envelope(
                kind="PROPOSE",
                thread_id=thread_id,
                sender_pk_b64=self.public_key_b64,
                payload=proposal,
            )

            signed = sign_envelope(env)
            subject = f"thread.{thread_id}.planner"

            await publish_envelope(thread_id, subject, signed)
            print(f"[PLANNER] Published PROPOSE for thread {thread_id}")
            self.bid_submitter.record_bid(task_id, bid)


# Run as standalone process
if __name__ == "__main__":
    print("=" * 60)
    print("Starting Planner Agent with Bidding")
    print("=" * 60)

    # Initialize agent with unique ID and public key from environment
    agent = PlannerAgent(
        agent_id="planner-1",
        public_key_b64=base64.b64encode(bytes(load_verifier())).decode(),
    )

    print(f"Agent ID: {agent.agent_id}")
    print(f"Reputation: {agent.reputation}")
    print(f"Capabilities: {agent.capabilities}")
    print(f"Subscribing to: thread.*.need")
    print("Waiting for NEED messages...")
    print("=" * 60)

    # Run agent - subscribe to all NEED messages on any thread
    asyncio.run(agent.run("demo-thread", "thread.*.need"))
