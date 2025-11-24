"""
Coordinator: Integrates all verb handlers with the message bus.

Responsibilities:
- Initialize plan_store and consensus_adapter
- Inject dependencies into all handlers
- Subscribe to NATS and route envelopes to dispatcher
"""

import asyncio
from pathlib import Path
from plan_store import PlanStore
from consensus import ConsensusAdapter
from bus import subscribe_envelopes
from verbs import DISPATCHER

# Import all handlers to trigger auto-registration
import handlers.need
import handlers.propose
import handlers.claim
import handlers.commit
import handlers.attest
import handlers.decide
import handlers.finalize


class Coordinator:
    def __init__(
        self,
        plan_store_path: Path = Path(".state/plan.db"),
        redis_url: str = "redis://localhost:6379"
    ):
        """
        Initialize coordinator with plan store and consensus adapter.
        """
        # Create plan store
        self.plan_store = PlanStore(plan_store_path)
        print(f"[COORDINATOR] Plan store initialized at {plan_store_path}")
        
        # Create consensus adapter
        self.consensus_adapter = ConsensusAdapter(redis_url)
        print(f"[COORDINATOR] Consensus adapter connected to {redis_url}")
        
        # Inject dependencies into all handlers
        self._inject_dependencies()
        
        # Log registered verbs
        verbs = DISPATCHER.list_verbs()
        print(f"[COORDINATOR] Registered {len(verbs)} verb handlers: {', '.join(verbs)}")
    
    def _inject_dependencies(self):
        """Inject plan_store and consensus_adapter into handlers"""
        # Inject plan_store into all handlers that need it
        handlers.need.plan_store = self.plan_store
        handlers.propose.plan_store = self.plan_store
        handlers.claim.plan_store = self.plan_store
        handlers.commit.plan_store = self.plan_store
        handlers.attest.plan_store = self.plan_store
        handlers.decide.plan_store = self.plan_store
        handlers.finalize.plan_store = self.plan_store
        
        # Inject consensus_adapter into handlers that need it
        handlers.attest.consensus_adapter = self.consensus_adapter
        handlers.decide.consensus_adapter = self.consensus_adapter
        
        print("[COORDINATOR] Dependencies injected into all handlers")
    
    async def handle_envelope(self, envelope: dict):
        """
        Route envelope to appropriate handler via dispatcher.
        """
        kind = envelope.get("kind", "UNKNOWN")
        thread_id = envelope.get("thread_id", "unknown")
        
        print(f"[COORDINATOR] Received {kind} envelope in thread {thread_id}")
        
        # Dispatch to registered handler
        handled = await DISPATCHER.dispatch(envelope)
        
        if handled:
            print(f"[COORDINATOR] ✓ {kind} handled successfully")
        else:
            print(f"[COORDINATOR] ⚠ No handler registered for {kind}")
    
    async def run(self, thread_pattern: str = "thread.*.*"):
        """
        Start coordinator - subscribe to NATS and route envelopes.
        """
        print(f"[COORDINATOR] Starting coordinator on subject pattern: {thread_pattern}")
        print("[COORDINATOR] Listening for envelopes...")
        print("-" * 60)
        
        # Subscribe to all threads and route to handler
        await subscribe_envelopes(
            thread_id="coordinator",
            subject=thread_pattern,
            handler=self.handle_envelope
        )
