"""
Deterministic Replay: verify a thread by replaying its audit log.

Validates:
1. All signatures valid
2. Lamport ordering correct
3. DECIDE uniqueness
4. Policy compliance (including WASM gates)
5. Final state consistency

Now uses DeterministicSimulator for enhanced replay capabilities.
"""

import json
import sys
from pathlib import Path

sys.path.append("src")
sys.path.append("tools")

from crypto import verify_record
from policy import validate_envelope
from simulator import DeterministicSimulator

# Optional WASM policy support
try:
    from policy.gates import GateEnforcer
    WASM_ENABLED = True
except ImportError:
    WASM_ENABLED = False

def replay_thread(log_path: str, thread_id: str, use_simulator: bool = True, test_chaos: bool = False):
    """
    Replay a thread from audit log and verify:
   1. All signatures valid
    2. Lamport ordering correct
    3. DECIDE uniqueness
    4. Policy compliance on envelopes (including WASM)
    5. Final state reached
    
    Args:
        log_path: Path to audit log file
        thread_id: Thread ID to replay
        use_simulator: Whether to use DeterministicSimulator (recommended)
        test_chaos: If True, test with chaos injection (clock skew + reordering)
    
    Returns: True if all checks pass, False otherwise
    """
    
    print("=" * 60)
    print(f"Replaying thread: {thread_id}")
    print(f"Audit log: {log_path}")
    print(f"Simulator: {'Enabled' if use_simulator else 'Legacy'}")
    if WASM_ENABLED:
        print("WASM policy: Enabled")
    print("=" * 60)
    
    # Load events for this thread
    events = []
    log_file = Path(log_path)
    
    if not log_file.exists():
        print(f"\n✗ ERROR: Log file not found: {log_path}")
        return False
    
    with open(log_file) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                event = json.loads(line.strip())
                if event.get("thread_id") == thread_id:
                    events.append(event)
            except json.JSONDecodeError as e:
                print(f"\n✗ ERROR: Invalid JSON in log: {e}")
                continue
    
    if not events:
        print(f"\n✗ ERROR: No events found for thread {thread_id}")
        return False
    
    print(f"\n✓ Found {len(events)} events for thread")
    
    # 1. Verify all signatures
    print("\n[1/5] Verifying signatures...")
    signature_failures = 0
    for i, event in enumerate(events):
        if not verify_record(event):
            print(f"  ✗ Event {i}: BAD SIGNATURE")
            signature_failures += 1
    
    if signature_failures > 0:
        print(f"  ✗ {signature_failures} signature(s) failed")
        return False
    print(f"  ✓ All {len(events)} signatures valid")
    
    # 2. Verify Lamport ordering (for envelope events)
    print("\n[2/5] Verifying Lamport ordering...")
    envelope_events = []
    for event in events:
        payload = event.get("payload", {})
        # Check if this is an envelope (has lamport in the nested payload)
        if isinstance(payload, dict) and "lamport" in payload:
            envelope_events.append(event)
    
    last_lamport = 0
    lamport_violations = 0
    for event in envelope_events:
        lamport = event["payload"]["lamport"]
        if lamport <= last_lamport:
            print(f"  ✗ Lamport not monotonic: {last_lamport} -> {lamport}")
            lamport_violations += 1
        last_lamport = max(last_lamport, lamport)
    
    if lamport_violations > 0:
        print(f"  ✗ {lamport_violations} Lamport violation(s)")
        return False
    print(f"  ✓ Lamport ordering correct ({len(envelope_events)} envelopes)")
    
    # 3. Verify DECIDE uniqueness
    print("\n[3/5] Verifying DECIDE uniqueness...")
    decide_events = []
    for event in events:
        payload = event.get("payload", {})
        if isinstance(payload, dict) and payload.get("kind") == "DECIDE":
            decide_events.append(event)
    
    # Check for duplicate DECIDEs per need_id
    need_decides = {}
    duplicate_decides = 0
    for event in decide_events:
        envelope = event["payload"]
        need_id = envelope.get("payload", {}).get("need_id", "unknown")
        if need_id in need_decides:
            print(f"  ✗ Multiple DECIDE for need {need_id}")
            duplicate_decides += 1
        need_decides[need_id] = event
    
    if duplicate_decides > 0:
        print(f"  ✗ {duplicate_decides} duplicate DECIDE(s)")
        return False
    print(f"  ✓ {len(decide_events)} DECIDE event(s), all unique")
    
    # 4. Validate policy compliance (including WASM gates)
    print("\n[4/5] Validating policy compliance...")
    policy_failures = 0
    gate_enforcer = None
    
    if WASM_ENABLED:
        gate_enforcer = GateEnforcer()
        print("  → WASM gate validation enabled")
    
    for event in envelope_events:
        envelope = event["payload"]
        try:
            # Standard policy validation
            validate_envelope(envelope)
            
            # WASM gate validation
            if gate_enforcer:
                decision = gate_enforcer.ingress_validate(envelope)
                if not decision.allowed:
                    raise ValueError(f"WASM gate rejected: {decision.reason}")
                    
        except Exception as e:
            print(f"  ✗ Policy violation: {e}")
            policy_failures += 1
    
    if policy_failures > 0:
        print(f"  ✗ {policy_failures} policy violation(s)")
        return False
    print(f"  ✓ All {len(envelope_events)} envelopes pass policy")
    
    # 5. Simulator-based verification (if enabled)
    if use_simulator:
        print("\n[5/5] Running deterministic simulation...")
        sim = DeterministicSimulator(seed=42)
        
        try:
            # Load and replay
            envelopes = sim.load_audit_log(log_path, thread_id)
            result = sim.replay_envelopes(validate_policy=True)
            
            if not result.success:
                print(f"  ✗ Simulation failed:")
                for error in result.errors:
                    print(f"     - {error}")
                return False
            
            print(f"  ✓ Deterministic replay successful")
            print(f"     - {result.envelopes_processed} envelopes processed")
            print(f"     - {len(result.decide_events)} DECIDE events")
            print(f"     - {len(result.finalize_events)} FINALIZE events")
            
            # Test chaos injection if requested
            if test_chaos:
                print("\n[CHAOS TEST] Injecting clock skew and reordering...")
                
                # Inject clock skew (±100ms)
                skewed = sim.inject_clock_skew(100, envelopes)
                
                # Inject message reordering
                reordered = sim.inject_message_reorder(0.2, 3, skewed)
                
                # Replay with chaos
                sim.reset()
                chaos_result = sim.replay_envelopes(reordered, validate_policy=True)
                
                if not chaos_result.success:
                    print(f"  ⚠ Chaos test failed (expected for some scenarios)")
                else:
                    print(f"  ✓ System resilient to chaos injection")
                    
                    # Verify FINALIZE matches
                    if result.finalize_events and chaos_result.finalize_events:
                        matches, diffs = sim.verify_finalize_match(
                            result.finalize_events[0],
                            chaos_result.finalize_events[0],
                            strict=False
                        )
                        
                        if matches:
                            print(f"  ✓ FINALIZE deterministic despite chaos")
                        else:
                            print(f"  ⚠ FINALIZE differences detected:")
                            for diff in diffs:
                                print(f"     - {diff}")
            
        except Exception as e:
            print(f"  ✗ Simulation error: {e}")
            return False
    else:
        # Legacy path - just check for FINALIZE
        print("\n[5/5] Checking final state...")
        finalize_events = []
        for event in events:
            payload = event.get("payload", {})
            if isinstance(payload, dict) and payload.get("kind") == "FINALIZE":
                finalize_events.append(event)
        
        if finalize_events:
            print(f"  ✓ Found {len(finalize_events)} FINALIZE event(s)")
        else:
            print(f"  ⚠ No FINALIZE events (flow may be incomplete)")
    
    # Summary
    print("\n" + "=" * 60)
    print("✓ REPLAY SUCCESSFUL")
    print("=" * 60)
    print(f"Events processed: {len(events)}")
    print(f"Envelopes validated: {len(envelope_events)}")
    print(f"DECIDE events: {len(decide_events)}")
    if use_simulator:
        print(f"Simulator: Enabled")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/replay.py <thread_id> [log_path] [--simulator] [--chaos]")
        print("\nExample:")
        print("  python tools/replay.py bb9f19b0-acf1-4597-8b0f-529d62d9d3dc")
        print("  python tools/replay.py <thread_id> --simulator --chaos")
        sys.exit(1)
    
    thread_id = sys.argv[1]
    log_path = "logs/swarm.jsonl"
    use_simulator = False
    test_chaos = False
    
    # Parse arguments
    for arg in sys.argv[2:]:
        if arg.startswith("--"):
            if arg == "--simulator":
                use_simulator = True
            elif arg == "--chaos":
                test_chaos = True
        else:
            log_path = arg
    
    success = replay_thread(log_path, thread_id, use_simulator, test_chaos)
    sys.exit(0 if success else 1)
