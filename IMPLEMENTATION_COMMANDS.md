# CAN Swarm v1 PoC — Implementation Commands

**Instructions:** Copy and paste each command block to your AI assistant in order. Each command is sized for completion in a single session.

**Parallel Opportunities:** Commands marked with 🔀 can be done in parallel with the next command if you're working with multiple AI sessions.

---

## PHASE 1: FIX CURRENT IMPLEMENTATION

### Command 1: Fix Core Issues
```
Implement Phase 1 fixes (tasks 1.1-1.3):

1. Fix the policy hash default in src/envelope.py:
   - Import current_policy_hash from policy module
   - Change line 39 default from "v0" to current_policy_hash()

2. Add missing verbs to src/policy.py:
   - Update ALLOWED_KINDS to include: DECIDE, PROPOSE, CLAIM, YIELD, RELEASE
   - Increment version from 0 to 1

3. Create requirements.txt with these dependencies:
   - nats-py==2.9.0
   - pynacl==1.5.0
   - redis==5.0.0
   - opentelemetry-api==1.21.0
   - opentelemetry-sdk==1.21.0

Run examples/publisher_envelope.py to verify the fix works.
```

**Checkpoint:** Examples run without policy validation errors

---

### Command 2: Add Backward Compatibility
```
Implement Phase 1 fixes (tasks 1.4-1.5):

1. Add backward-compatible functions to src/bus.py:
   - Create async def publish(thread_id, subject, message) that wraps publish_raw()
   - Create async def subscribe(thread_id, subject, handler) that wraps basic subscription
   - Both should still log to audit trail but skip envelope validation

2. Fix example scripts to remove hardcoded policy hashes:
   - examples/publisher_envelope.py: remove policy_engine_hash="v0" parameter
   - examples/publisher_cas.py: remove policy_engine_hash="v0" parameter

Test that examples/publisher.py and examples/listener.py now work.
```

**Checkpoint:** All examples run successfully

---

### Command 3: Add Testing Infrastructure 🔀
```
Implement Phase 1 fixes (tasks 1.6-1.8):

1. Create tests/test_core.py with these unit tests:
   - test_sign_verify_record: test crypto signing and tampering detection
   - test_lamport_ordering: test clock tick/observe
   - test_envelope_creation: test make_envelope
   - test_policy_validation: test validate_envelope for pass/fail cases

2. Update docker-compose.yml to add Redis service:
   - Add redis:7-alpine service on port 6379
   - Add redis-data volume

3. Create/update .gitignore to exclude:
   - .venv/, *.pyc, __pycache__/, .pytest_cache/
   - logs/*.jsonl, .state/, .cas/, .env

Run: pytest tests/test_core.py -v
Then: docker-compose up -d
```

**Checkpoint:** Tests pass, Redis and NATS running

**Note:** 🔀 This can be done in parallel with Command 4 if using separate sessions

---

## PHASE 2: CORE INFRASTRUCTURE

### Command 4: Implement Plan Store 🔀
```
Implement Phase 2.1 - SQLite Plan Store:

Create src/plan_store.py with:
- OpType enum: ADD_TASK, REQUIRES, PRODUCES, STATE, LINK, ANNOTATE
- TaskState enum: DRAFT, DECIDED, VERIFIED, FINAL
- PlanOp dataclass
- PlanStore class with:
  - SQLite database with ops, tasks, edges tables
  - append_op(op) method
  - get_task(task_id) method
  - get_ops_for_thread(thread_id) method
  - Proper CRDT semantics (G-Set for ops, LWW for annotations, monotonic state)

Create tests/test_plan_store.py with:
- test_plan_store_basic: test ADD_TASK and get_task
- test_state_monotonic: test STATE only advances with higher lamport
- test_thread_ops: test get_ops_for_thread ordering

Run: pytest tests/test_plan_store.py -v

Use the full code example from IMPLEMENTATION_ROADMAP.md section 2.1.
```

**Checkpoint:** Plan store tests pass, ops are persisted

**Note:** 🔀 Can be done in parallel with Command 3

---

### Command 5: Implement Consensus Adapter
```
Implement Phase 2.2 - Redis DECIDE Consensus:

Create src/consensus.py with:
- DecideRecord dataclass
- ConsensusAdapter class with:
  - Redis connection
  - Lua script for atomic DECIDE (check-and-set pattern)
  - try_decide() method returning DecideRecord or None
  - get_decide() method to fetch existing DECIDE

Create tests/test_consensus.py with:
- test_at_most_once_decide: verify only first DECIDE succeeds
- test_idempotent_retry: verify same DECIDE can be retried
- test_different_proposals: verify conflicts are rejected

Run: pytest tests/test_consensus.py -v

Use the full code example from IMPLEMENTATION_ROADMAP.md section 2.2.
```

**Checkpoint:** Consensus tests pass, at-most-once DECIDE verified

---

### Command 6: Implement Verb Dispatcher
```
Implement Phase 2.3 - Verb Dispatcher and NEED Handler:

1. Create src/verbs.py with:
   - VerbHandler type alias
   - VerbDispatcher class with register() and dispatch() methods
   - Global DISPATCHER instance

2. Create src/handlers/ directory

3. Create src/handlers/need.py with:
   - handle_need(envelope) function
   - Creates task in plan store
   - Registers with DISPATCHER

4. Update src/verbs.py to import and initialize plan_store reference

Create tests/test_verbs.py with:
- test_dispatcher_registration
- test_dispatcher_dispatch
- test_need_handler: verify task created in plan store

Run: pytest tests/test_verbs.py -v

Use the code examples from IMPLEMENTATION_ROADMAP.md sections 2.3-2.4.
```

**Checkpoint:** Verb dispatcher works, NEED creates tasks

---

### Command 7: Implement PROPOSE and CLAIM Handlers
```
Implement Phase 2.5-2.6 - PROPOSE and CLAIM Handlers:

1. Create src/handlers/propose.py with:
   - handle_propose(envelope) function
   - Stores proposal in plan store as ANNOTATE op
   - Registers with DISPATCHER

2. Create src/handlers/claim.py with:
   - handle_claim(envelope) function
   - Records claim with lease TTL
   - Updates task state to CLAIMED
   - Registers with DISPATCHER

Create tests/test_handlers.py with:
- test_propose_handler: verify proposal stored
- test_claim_handler: verify claim recorded and state updated

Run: pytest tests/test_handlers.py -v
```

**Checkpoint:** PROPOSE and CLAIM handlers work

---

### Command 8: Implement COMMIT and ATTEST Handlers
```
Implement Phase 2.7-2.8 - COMMIT and ATTEST Handlers:

1. Create src/handlers/commit.py with:
   - handle_commit(envelope) function
   - Validates artifact_hash exists in CAS
   - Records commit in plan store
   - Registers with DISPATCHER

2. Create src/handlers/attest.py with:
   - handle_attest(envelope) function
   - Records attestation in plan store
   - Checks if K_plan threshold reached (for now K=1)
   - Triggers DECIDE if threshold met
   - Registers with DISPATCHER

Create tests/test_commit_attest.py with:
- test_commit_requires_cas: verify artifact validation
- test_attest_aggregation: verify K threshold logic

Run: pytest tests/test_commit_attest.py -v
```

**Checkpoint:** COMMIT validates CAS, ATTEST aggregates

---

### Command 9: Implement DECIDE and FINALIZE Handlers
```
Implement Phase 2.9-2.10 - DECIDE and FINALIZE Handlers:

1. Create src/handlers/decide.py with:
   - handle_decide(envelope) function
   - Calls consensus.try_decide() for atomicity
   - Updates task state to DECIDED in plan store
   - Publishes DECIDE envelope on success
   - Registers with DISPATCHER

2. Create src/handlers/finalize.py with:
   - handle_finalize(envelope) function
   - Updates task state to FINAL
   - Records completion metadata
   - Registers with DISPATCHER

Create tests/test_decide_finalize.py with:
- test_decide_atomicity: verify at-most-once via consensus
- test_finalize_state: verify state becomes FINAL

Run: pytest tests/test_decide_finalize.py -v
```

**Checkpoint:** DECIDE is atomic, FINALIZE marks completion

---

### Command 10: Wire Handlers to Bus
```
Implement Phase 2.11 - Integration Layer:

1. Create src/coordinator.py with:
   - Coordinator class that:
     - Initializes plan_store, consensus adapter
     - Subscribes to thread.*.* subject
     - Routes envelopes to DISPATCHER
     - Handles unrecognized verbs gracefully

2. Update src/handlers/__init__.py to import all handlers

3. Create a demo script: demo/start_coordinator.py
   - Starts coordinator listening on all threads
   - Logs verb handling to console

Test by running:
- Terminal 1: python demo/start_coordinator.py
- Terminal 2: python examples/publisher_envelope.py
- Verify coordinator receives and dispatches NEED
```

**Checkpoint:** Coordinator routes messages to handlers

---

## PHASE 3: AGENT IMPLEMENTATION

### Command 11: Implement Base Agent Class
```
Implement Phase 3.1 - Base Agent:

Create src/agent.py with:
- BaseAgent abstract class with:
  - __init__(agent_id, public_key_b64)
  - abstract on_envelope(envelope) method
  - run(thread_id, subject) method that subscribes to bus
  - Helper methods for publishing envelopes

Create tests/test_agent.py with:
- test_agent_subscription: verify base agent can subscribe
- test_agent_envelope_handling: verify on_envelope is called

Use the code example from IMPLEMENTATION_ROADMAP.md section 3.1.
```

**Checkpoint:** Base agent can subscribe and receive messages

---

### Command 12: Implement Planner Agent
```
Implement Phase 3.2 - Planner Agent:

Create agents/planner.py with:
- PlannerAgent class extending BaseAgent
- on_envelope() handles NEED messages
- Creates simple single-worker proposals
- Publishes PROPOSE envelope

Create a standalone script:
- Can be run as: python agents/planner.py
- Subscribes to thread.*.need pattern
- Logs all NEED messages received and proposals created

Test by running:
- Terminal 1: python agents/planner.py
- Terminal 2: python examples/publisher_envelope.py (with kind=NEED)
- Verify planner creates and publishes PROPOSE

Use the code example from IMPLEMENTATION_ROADMAP.md section 3.2.
```

**Checkpoint:** Planner responds to NEED with PROPOSE

---

### Command 13: Implement Worker Agent
```
Implement Phase 3.3 - Worker Agent:

Create agents/worker.py with:
- WorkerAgent class extending BaseAgent
- on_envelope() handles PROPOSE and CLAIM messages
- For PROPOSE: evaluates if can handle, publishes CLAIM if yes
- For assigned work: executes task (mock for now)
- Publishes COMMIT with artifact to CAS

Create mock work function:
- Takes task payload as input
- Creates dummy result (e.g., {"result": "mock classification"})
- Stores in CAS
- Returns artifact hash

Test by running:
- Terminal 1: python demo/start_coordinator.py
- Terminal 2: python agents/worker.py
- Terminal 3: Publish PROPOSE message
- Verify worker claims task and publishes COMMIT
```

**Checkpoint:** Worker claims tasks and produces artifacts

---

### Command 14: Implement Verifier Agent
```
Implement Phase 3.4-3.5 - Verifier and Aggregator:

Create agents/verifier.py with:
- VerifierAgent class extending BaseAgent
- on_envelope() handles COMMIT messages
- Validates:
  - Artifact exists in CAS
  - Payload hash matches
  - Policy compliance
- Publishes ATTEST with verdict
- For K=1 bootstrap: immediately triggers FINALIZE

Test verification logic:
- Valid COMMIT → ATTEST(pass) → FINALIZE
- Missing artifact → ATTEST(fail) → no FINALIZE

Test by running full chain:
- Coordinator, Planner, Worker, Verifier all running
- Publish NEED
- Verify FINALIZE is emitted
```

**Checkpoint:** Verifier validates and triggers FINALIZE

---

## PHASE 4: INTEGRATION & DEMO

### Command 15: Create End-to-End Demo
```
Implement Phase 4.1 - E2E Demo Script:

Create demo/e2e_flow.py with:
- Automated test that:
  1. Starts all agents in subprocesses (coordinator, planner, worker, verifier)
  2. Waits for them to connect
  3. Publishes a NEED message
  4. Waits for processing (10-15 seconds)
  5. Queries plan store to verify FINALIZE state
  6. Checks audit log for complete flow
  7. Cleans up processes

Create demo/publish_need.py:
- Simple script to publish a test NEED

Create demo/check_finalize.py:
- Queries plan store and audit log
- Prints final state
- Returns success/failure exit code

Run: python demo/e2e_flow.py

Use the code example from IMPLEMENTATION_ROADMAP.md section 4.1.
```

**Checkpoint:** Complete NEED→FINALIZE flow works end-to-end

---

### Command 16: Implement Replay Tool
```
Implement Phase 4.2 - Deterministic Replay:

Create tools/replay.py with:
- replay_thread(log_path, thread_id) function that:
  1. Reads audit log for thread
  2. Verifies all signatures
  3. Checks Lamport ordering
  4. Verifies DECIDE uniqueness
  5. Validates policy compliance
  6. Reproduces final state
  7. Returns success/failure

Add CLI interface:
- Usage: python tools/replay.py <thread_id>
- Prints validation results
- Exits with code 0 for success, 1 for failure

Test by:
1. Run demo/e2e_flow.py to generate a thread
2. Run tools/replay.py <thread-id>
3. Verify all checks pass

Use the code example from IMPLEMENTATION_ROADMAP.md section 4.2.
```

**Checkpoint:** Replay verifies determinism and integrity

---

### Command 17: Implement Property Tests
```
Implement Phase 4.3-4.6 - Property Tests:

Create tests/test_properties.py with:

1. test_p1_single_decide:
   - Run E2E flow multiple times with same NEED
   - Verify exactly one DECIDE recorded in consensus
   - Different proposals should all be rejected after first

2. test_p2_deterministic_replay:
   - Run E2E flow
   - Replay audit log
   - Verify final states match exactly

3. test_p3_lamport_ordering:
   - Generate multiple concurrent messages
   - Verify Lamport clock maintains causal ordering
   - Check no clock reversals

4. test_p4_policy_enforcement:
   - Try to publish invalid envelopes
   - Verify coordinator rejects them
   - Check audit log shows rejection

Run: pytest tests/test_properties.py -v
```

**Checkpoint:** All property tests pass (P1-P4)

---

## PHASE 5: DOCUMENTATION & POLISH

### Command 18: Update Documentation
```
Implement Phase 5.1-5.3 - Core Documentation:

1. Update README.md:
   - Add quick start guide
   - Add architecture overview
   - Add demo instructions
   - Document all phases (0-4) as complete
   - Link to detailed docs

2. Create docs/API.md:
   - Document all modules (crypto, audit, bus, envelope, cas, policy)
   - Document plan_store, consensus, verbs, agent APIs
   - Include usage examples for each

3. Create docs/ARCHITECTURE.md with:
   - System architecture diagram (text or mermaid)
   - Data flow diagram for NEED→FINALIZE
   - State machine diagram for task states
   - Component interaction diagram
```

**Checkpoint:** Documentation complete and accurate

---

### Command 19: Create Demo Walkthrough
```
Implement Phase 5.4 - Demo Walkthrough:

Create docs/DEMO.md with:
- Prerequisites (Docker, Python, dependencies)
- Step-by-step setup:
  1. Clone and setup venv
  2. Generate keys
  3. Start infrastructure (docker-compose up)
  4. Install dependencies
- Running the demo:
  1. Start coordinator
  2. Start agents
  3. Publish NEED
  4. Watch the flow
  5. Run replay
- Expected output at each step
- Troubleshooting common issues

Test the walkthrough yourself to verify accuracy.
```

**Checkpoint:** A newcomer can run the demo following instructions

---

### Command 20: Migration Plan and Final Polish
```
Implement Phase 5.5-5.6 - Migration and Contribution Docs:

1. Create docs/V2_MIGRATION.md:
   - Document upgrade path from v1 to v2
   - SQLite → Automerge migration
   - Redis → etcd-raft migration
   - File CAS → MinIO → IPFS migration
   - Python policy → OPA/WASM migration
   - Single-node → distributed deployment

2. Create CONTRIBUTING.md:
   - Code style guidelines
   - How to add new verbs
   - How to add new agent types
   - Testing requirements
   - PR process

3. Final cleanup:
   - Remove any TODOs or placeholder code
   - Ensure all tests pass
   - Verify all examples work
   - Check all links in documentation
   - Update version numbers

Run full test suite: pytest -v
Run E2E demo: python demo/e2e_flow.py
Run replay: python tools/replay.py <thread-id>
```

**Checkpoint:** PoC is complete, documented, and ready for use

---

## SUMMARY

**Total Commands:** 20
**Parallel Opportunities:** Commands 3 and 4 can run in parallel

**Order:**
1-2: Fix current code (2 commands)
3-4: Testing + Plan Store (2 commands, can be parallel)
5-10: Core infrastructure (6 commands)
11-14: Agents (4 commands)
15-17: Integration (3 commands)
18-20: Documentation (3 commands)

**Estimated Completion:**
- Phase 1: 2-3 commands
- Phase 2: 7 commands  
- Phase 3: 4 commands
- Phase 4: 3 commands
- Phase 5: 3 commands

**Total:** 20 structured commands to complete PoC

---

## NOTES

- Each command is designed to be completed in one AI session
- Commands build on previous work - do them in order (except where marked parallel)
- Each has a clear checkpoint for you to verify
- Save this file and paste one command at a time
- If any command fails or seems too large, you can ask to split it further
