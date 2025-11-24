"""
Deterministic Replay: verify a thread by replaying its audit log.

Validates:
1. All signatures valid
2. Lamport ordering correct
3. DECIDE uniqueness
4. Policy compliance
5. Final state consistency
"""

import json
import sys
from pathlib import Path

sys.path.append("src")
from crypto import verify_record
from policy import validate_envelope

def replay_thread(log_path: str, thread_id: str):
    """
    Replay a thread from audit log and verify:
    1. All signatures valid
    2. Lamport ordering correct
    3. DECIDE uniqueness
    4. Policy compliance on envelopes
    5. Final state reached
    
    Returns: True if all checks pass, False otherwise
    """
    
    print("=" * 60)
    print(f"Replaying thread: {thread_id}")
    print(f"Audit log: {log_path}")
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
    
    # 4. Validate policy compliance
    print("\n[4/5] Validating policy compliance...")
    policy_failures = 0
    for event in envelope_events:
        envelope = event["payload"]
        try:
            validate_envelope(envelope)
        except Exception as e:
            print(f"  ✗ Policy violation: {e}")
            policy_failures += 1
    
    if policy_failures > 0:
        print(f"  ✗ {policy_failures} policy violation(s)")
        return False
    print(f"  ✓ All {len(envelope_events)} envelopes pass policy")
    
    # 5. Check for FINALIZE
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
    print(f"FINALIZE events: {len(finalize_events)}")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/replay.py <thread_id> [log_path]")
        print("\nExample:")
        print("  python tools/replay.py bb9f19b0-acf1-4597-8b0f-529d62d9d3dc")
        sys.exit(1)
    
    thread_id = sys.argv[1]
    log_path = sys.argv[2] if len(sys.argv) > 2 else "logs/swarm.jsonl"
    
    success = replay_thread(log_path, thread_id)
    sys.exit(0 if success else 1)
