"""
Worker Agent: listens for PROPOSE, claims tasks, executes work, and commits results.

This agent:
- Subscribes to thread.*.planner (to see proposals) and thread.*.worker (for claims)
- Evaluates proposals and claims "worker" tasks
- Executes mock work
- Stores results in CAS
- Publishes COMMIT envelopes
"""

import sys
import os
import uuid
import base64
import asyncio
import time

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent import BaseAgent
from envelope import make_envelope, sign_envelope
from bus import publish_envelope
from crypto import load_verifier
import cas

class WorkerAgent(BaseAgent):
    """Agent that claims and executes tasks"""
    
    def __init__(self, agent_id: str, public_key_b64: str):
        super().__init__(agent_id, public_key_b64)
        self.claimed_tasks = set()
    
    async def on_envelope(self, envelope: dict):
        """Handle incoming envelopes"""
        kind = envelope.get("kind")
        
        if kind == "PROPOSE":
            await self.handle_propose(envelope)
        elif kind == "CLAIM":
            await self.handle_claim(envelope)
            
    async def handle_propose(self, envelope: dict):
        """Evaluate proposal and claim tasks if capable"""
        thread_id = envelope["thread_id"]
        payload = envelope["payload"]
        plan = payload.get("plan", [])
        
        print(f"[WORKER] Received PROPOSE in thread {thread_id}")
        
        for task in plan:
            task_id = task.get("task_id")
            task_type = task.get("type")
            
            # Simple logic: claim any "worker" task we haven't seen
            if task_type == "worker" and task_id not in self.claimed_tasks:
                print(f"[WORKER] Found suitable task {task_id}")
                await self.claim_task(thread_id, task)
                
    async def claim_task(self, thread_id: str, task: dict):
        """Publish CLAIM for a task"""
        task_id = task["task_id"]
        
        claim_payload = {
            "task_id": task_id,
            "claimer_id": self.agent_id,
            "lease_seconds": 30
        }
        
        env = make_envelope(
            kind="CLAIM",
            thread_id=thread_id,
            sender_pk_b64=self.public_key_b64,
            payload=claim_payload
        )
        
        signed = sign_envelope(env)
        subject = f"thread.{thread_id}.worker"
        
        await publish_envelope(thread_id, subject, signed)
        print(f"[WORKER] Published CLAIM for task {task_id}")
        
        # Optimistic execution: assume we got it
        self.claimed_tasks.add(task_id)
        await self.execute_task(thread_id, task)
        
    async def handle_claim(self, envelope: dict):
        """Track claims (could be used for coordination)"""
        payload = envelope["payload"]
        task_id = payload.get("task_id")
        claimer = payload.get("claimer_id")
        
        if claimer != self.agent_id:
            print(f"[WORKER] Observed CLAIM for {task_id} by {claimer}")
            self.claimed_tasks.add(task_id)

    async def execute_task(self, thread_id: str, task: dict):
        """Execute the task and publish result"""
        task_id = task["task_id"]
        input_data = task.get("input", {})
        
        print(f"[WORKER] Executing task {task_id}...")
        
        # Mock work simulation
        await asyncio.sleep(1)
        
        # Create result
        result = {
            "status": "success",
            "task_id": task_id,
            "worker_id": self.agent_id,
            "output": f"Processed: {input_data}",
            "timestamp": time.time()
        }
        
        # Store in CAS
        artifact_hash = cas.put_json(result)
        print(f"[WORKER] Stored result in CAS: {artifact_hash}")
        
        # Publish COMMIT
        await self.publish_commit(thread_id, task_id, artifact_hash)
        
    async def publish_commit(self, thread_id: str, task_id: str, artifact_hash: str):
        """Publish COMMIT envelope with artifact hash"""
        commit_payload = {
            "task_id": task_id,
            "artifact_hash": artifact_hash,
            "artifact_algo": "sha256"
        }
        
        env = make_envelope(
            kind="COMMIT",
            thread_id=thread_id,
            sender_pk_b64=self.public_key_b64,
            payload=commit_payload
        )
        
        signed = sign_envelope(env)
        subject = f"thread.{thread_id}.worker"
        
        await publish_envelope(thread_id, subject, signed)
        print(f"[WORKER] Published COMMIT for task {task_id}")


if __name__ == "__main__":
    print("=" * 60)
    print("Starting Worker Agent")
    print("=" * 60)
    
    agent = WorkerAgent(
        agent_id="worker-1",
        public_key_b64=base64.b64encode(bytes(load_verifier())).decode()
    )
    
    print(f"Agent ID: {agent.agent_id}")
    # Subscribe to planner (proposals) and worker (claims) channels
    # Using wildcards to catch messages from any thread
    print("Subscribing to: thread.*.planner, thread.*.worker")
    
    async def main():
        # Run multiple subscriptions
        await asyncio.gather(
            agent.run("demo-thread-p", "thread.*.planner"),
            agent.run("demo-thread-w", "thread.*.worker")
        )
        
    asyncio.run(main())
