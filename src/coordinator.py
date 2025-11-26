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
from daemons import BootstrapMonitor

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
        redis_url: str = "redis://localhost:6379",
        verifier_pool = None,
        enable_fast_sync: bool = True,
        checkpoint_dir: Path = None
    ):
        """
        Initialize coordinator with plan store and consensus adapter.
        
        Args:
            plan_store_path: Path to SQLite plan store
            redis_url: Redis connection URL
            verifier_pool: Optional VerifierPool instance for bootstrap monitoring
            enable_fast_sync: Enable fast sync from checkpoints
            checkpoint_dir: Directory for checkpoints (default: .state/checkpoints)
        """
        # Try fast sync if enabled
        if enable_fast_sync:
            self._attempt_fast_sync(checkpoint_dir)
        
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
        
        # Start bootstrap monitor if verifier pool is provided
        self.bootstrap_monitor = None
        if verifier_pool:
            self._start_bootstrap_monitor(verifier_pool)
    
    def _attempt_fast_sync(self, checkpoint_dir: Path = None):
        """Attempt to fast sync from checkpoint on startup."""
        try:
            from checkpoint.sync import FastSync
            
            fast_sync = FastSync(checkpoint_dir=checkpoint_dir)
            
            # Check if checkpoint is available
            checkpoint = fast_sync.get_latest_checkpoint()
            
            if checkpoint:
                # Estimate sync time
                sync_time = fast_sync.estimate_sync_time(checkpoint)
                
                if sync_time < 60:  # Under 60 seconds
                    print(
                        f"[COORDINATOR] Fast sync available: "
                        f"epoch {checkpoint.checkpoint.epoch}, "
                        f"~{sync_time:.1f}s estimated"
                    )
                    # Would perform actual sync here in production
                else:
                    print(
                        f"[COORDINATOR] Checkpoint available but sync time "
                        f"~{sync_time:.1f}s exceeds threshold"
                    )
            else:
                print("[COORDINATOR] No checkpoint available for fast sync")
                
        except Exception as e:
            print(f"[COORDINATOR] Fast sync check failed: {e}")
    
    def _start_bootstrap_monitor(self, verifier_pool):
        """Initialize and start bootstrap monitor daemon"""
        def get_active_verifier_count():
            """Callback to get current active verifier count"""
            return len(verifier_pool.get_active_verifiers(min_stake=1000))
        
        self.bootstrap_monitor = BootstrapMonitor(
            get_active_verifiers_callback=get_active_verifier_count,
            check_interval_seconds=3600  # Check every hour
        )
        self.bootstrap_monitor.start()
        print(f"[COORDINATOR] Bootstrap monitor started")
    
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
