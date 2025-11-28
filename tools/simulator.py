"""
Deterministic Simulator for replaying and testing agent swarm behavior.

Provides:
- Deterministic replay from audit logs
- Chaos injection (clock skew, message reordering)
- FINALIZE verification
- WASM policy replay support
"""

import json
import random
import copy
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    """Result of a simulation run"""
    success: bool
    final_state: Dict[str, Any]
    envelopes_processed: int
    decide_events: List[Dict[str, Any]]
    finalize_events: List[Dict[str, Any]]
    errors: List[str]
    warnings: List[str]


class DeterministicSimulator:
    """
    Deterministic simulator for replaying agent swarm traces.
    
    Features:
    - Load and replay audit logs
    - Inject clock skew for chaos testing
    - Inject message reordering
    - Verify FINALIZE determinism
    """
    
    def __init__(self, seed: Optional[int] = None):
        """
        Initialize simulator.
        
        Args:
            seed: Random seed for deterministic chaos injection
        """
        self.seed = seed
        if seed is not None:
            random.seed(seed)
        
        self.envelopes: List[Dict[str, Any]] = []
        self.state: Dict[str, Any] = {
            "needs": {},
            "decisions": {},
            "finalizations": {},
            "lamport": 0
        }
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def load_audit_log(self, path: str, thread_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Load envelopes from audit log.
        
        Args:
            path: Path to audit log file (JSONL format)
            thread_id: Optional thread ID to filter by
        
        Returns:
            List of envelope dictionaries
        
        Raises:
            FileNotFoundError: If log file doesn't exist
            ValueError: If log format is invalid
        """
        log_file = Path(path)
        
        if not log_file.exists():
            raise FileNotFoundError(f"Audit log not found: {path}")
        
        envelopes = []
        
        with open(log_file) as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                
                try:
                    event = json.loads(line.strip())
                    
                    # Filter by thread_id if specified
                    if thread_id and event.get("thread_id") != thread_id:
                        continue
                    
                    # Extract envelope from event payload
                    payload = event.get("payload", {})
                    
                    # Check if this is an envelope (has required fields)
                    if isinstance(payload, dict) and "kind" in payload:
                        envelopes.append(payload)
                    
                except json.JSONDecodeError as e:
                    self.warnings.append(f"Invalid JSON at line {line_num}: {e}")
                    continue
        
        self.envelopes = envelopes
        logger.info(f"Loaded {len(envelopes)} envelopes from {path}")
        
        return envelopes
    
    def replay_envelopes(
        self,
        envelopes: Optional[List[Dict[str, Any]]] = None,
        validate_policy: bool = True
    ) -> SimulationResult:
        """
        Replay envelopes in deterministic order.
        
        Args:
            envelopes: Envelopes to replay (uses loaded if None)
            validate_policy: Whether to validate policy compliance
        
        Returns:
            SimulationResult with final state and statistics
        """
        if envelopes is None:
            envelopes = self.envelopes
        
        if not envelopes:
            return SimulationResult(
                success=False,
                final_state=copy.deepcopy(self.state),
                envelopes_processed=0,
                decide_events=[],
                finalize_events=[],
                errors=["No envelopes to replay"],
                warnings=self.warnings
            )
        
        # Reset state
        self.state = {
            "needs": {},
            "decisions": {},
            "finalizations": {},
            "lamport": 0
        }
        self.errors = []
        
        decide_events = []
        finalize_events = []
        
        # Sort by Lamport clock for deterministic ordering
        sorted_envelopes = sorted(
            envelopes,
            key=lambda e: e.get("lamport", 0)
        )
        
        # Replay each envelope
        for i, envelope in enumerate(sorted_envelopes):
            try:
                self._process_envelope(envelope, validate_policy)
                
                # Track DECIDE and FINALIZE events
                kind = envelope.get("kind")
                if kind == "DECIDE":
                    decide_events.append(envelope)
                elif kind == "FINALIZE":
                    finalize_events.append(envelope)
                    
            except Exception as e:
                error_msg = f"Error processing envelope {i}: {e}"
                self.errors.append(error_msg)
                logger.error(error_msg)
        
        success = len(self.errors) == 0
        
        return SimulationResult(
            success=success,
            final_state=copy.deepcopy(self.state),
            envelopes_processed=len(sorted_envelopes),
            decide_events=decide_events,
            finalize_events=finalize_events,
            errors=self.errors,
            warnings=self.warnings
        )
    
    def inject_clock_skew(self, delta_ms: int, envelopes: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        Inject clock skew into envelope timestamps.
        
        Simulates clock drift by adding random skew to timestamps
        while preserving Lamport ordering.
        
        Args:
            delta_ms: Maximum clock skew in milliseconds (+/-)
            envelopes: Envelopes to modify (uses loaded if None)
        
        Returns:
            Modified envelopes with clock skew
        """
        if envelopes is None:
            envelopes = self.envelopes
        
        modified = []
        
        for envelope in envelopes:
            env_copy = copy.deepcopy(envelope)
            
            # Add random skew to timestamp
            if "timestamp_ns" in env_copy:
                skew_ns = random.randint(-delta_ms * 1_000_000, delta_ms * 1_000_000)
                env_copy["timestamp_ns"] = env_copy["timestamp_ns"] + skew_ns
                
                # Ensure timestamp doesn't go negative
                env_copy["timestamp_ns"] = max(0, env_copy["timestamp_ns"])
            
            modified.append(env_copy)
        
        logger.info(f"Injected clock skew (±{delta_ms}ms) into {len(modified)} envelopes")
        
        return modified
    
    def inject_message_reorder(
        self,
        probability: float = 0.1,
        max_distance: int = 5,
        envelopes: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Inject message reordering to simulate network delays.
        
        Randomly reorders messages while preserving causality
        (respects Lamport clock dependencies).
        
        NOTE: Reordering preserves Lamport order to maintain causality.
        Messages can only be reordered if they have the same Lamport clock.
        
        Args:
            probability: Probability of reordering each message (0.0-1.0)
            max_distance: Maximum positions a message can move
            envelopes: Envelopes to reorder (uses loaded if None)
        
        Returns:
            Reordered envelopes (Lamport order preserved)
        """
        if envelopes is None:
            envelopes = self.envelopes
        
        # Create mutable copy with indices
        indexed = [(i, copy.deepcopy(env)) for i, env in enumerate(envelopes)]
        
        # Group by Lamport clock (can only reorder within same Lamport value)
        lamport_groups = {}
        for idx, env in indexed:
            lamport = env.get("lamport", 0)
            if lamport not in lamport_groups:
                lamport_groups[lamport] = []
            lamport_groups[lamport].append((idx, env))
        
        # Reorder within each group
        for lamport, group in lamport_groups.items():
            if len(group) > 1 and random.random() < probability:
                # Shuffle this group (all have same Lamport, so safe)
                indices = [idx for idx, env in group]
                envs = [env for idx, env in group]
                random.shuffle(envs)
                lamport_groups[lamport] = list(zip(indices, envs))
        
        # Reconstruct in Lamport order
        reordered = []
        for lamport in sorted(lamport_groups.keys()):
            for idx, env in lamport_groups[lamport]:
                reordered.append(env)
        
        logger.info(f"Reordered messages with p={probability}, max_distance={max_distance}")
        
        return reordered
    
    def verify_finalize_match(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        strict: bool = True
    ) -> Tuple[bool, List[str]]:
        """
        Verify that FINALIZE events match between runs.
        
        Args:
            expected: Expected FINALIZE envelope
            actual: Actual FINALIZE envelope
            strict: If True, require exact match. If False, allow minor differences.
        
        Returns:
            Tuple of (matches: bool, differences: List[str])
        """
        differences = []
        
        # Check kind
        if expected.get("kind") != "FINALIZE" or actual.get("kind") != "FINALIZE":
            differences.append("One or both envelopes are not FINALIZE events")
            return False, differences
        
        # Compare payloads
        exp_payload = expected.get("payload", {})
        act_payload = actual.get("payload", {})
        
        # Critical fields that must match
        critical_fields = ["need_id", "agent_id", "result"]
        
        for field in critical_fields:
            exp_val = exp_payload.get(field)
            act_val = act_payload.get(field)
            
            if exp_val != act_val:
                differences.append(
                    f"Field '{field}' mismatch: expected={exp_val}, actual={act_val}"
                )
        
        if strict:
            # In strict mode, check Lamport clock and timestamp
            if expected.get("lamport") != actual.get("lamport"):
                differences.append(
                    f"Lamport mismatch: expected={expected.get('lamport')}, "
                    f"actual={actual.get('lamport')}"
                )
            
            # Allow small timestamp differences (up to 1ms)
            exp_ts = expected.get("timestamp_ns", 0)
            act_ts = actual.get("timestamp_ns", 0)
            if abs(exp_ts - act_ts) > 1_000_000:  # 1ms tolerance
                differences.append(
                    f"Timestamp difference > 1ms: expected={exp_ts}, actual={act_ts}"
                )
        
        matches = len(differences) == 0
        
        return matches, differences
    
    def _process_envelope(self, envelope: Dict[str, Any], validate_policy: bool):
        """
        Process a single envelope and update state.
        
        Args:
            envelope: Envelope to process
            validate_policy: Whether to validate policy compliance
        """
        kind = envelope.get("kind")
        lamport = envelope.get("lamport", 0)
        payload = envelope.get("payload", {})
        
        # Update Lamport clock
        self.state["lamport"] = max(self.state["lamport"], lamport)
        
        # Validate policy if requested
        if validate_policy:
            try:
                # Import here to avoid circular dependency
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
                from policy import validate_envelope
                validate_envelope(envelope)
            except Exception as e:
                raise ValueError(f"Policy validation failed: {e}")
        
        # Update state based on envelope kind
        if kind == "NEED":
            need_id = payload.get("need_id")
            if need_id:
                self.state["needs"][need_id] = envelope
        
        elif kind == "DECIDE":
            need_id = payload.get("need_id")
            if need_id:
                # Check for duplicate DECIDE
                if need_id in self.state["decisions"]:
                    raise ValueError(f"Duplicate DECIDE for need {need_id}")
                self.state["decisions"][need_id] = envelope
        
        elif kind == "FINALIZE":
            need_id = payload.get("need_id")
            if need_id:
                self.state["finalizations"][need_id] = envelope
    
    def get_state(self) -> Dict[str, Any]:
        """Get current simulation state"""
        return copy.deepcopy(self.state)
    
    def reset(self):
        """Reset simulator state"""
        self.envelopes = []
        self.state = {
            "needs": {},
            "decisions": {},
            "finalizations": {},
            "lamport": 0
        }
        self.errors = []
        self.warnings = []
