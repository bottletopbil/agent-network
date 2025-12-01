# Remediation Commands - Test-Driven Fix Workflow

**Purpose:** Copy-paste these commands sequentially to systematically fix all audit findings.

**Pattern:** Each command follows Test-Driven Development:
1. Load context files
2. Create failing test for the bug
3. Fix the code
4. Verify test passes
5. Update REMEDIATION.md checklist

**Execution:** Copy each command block and paste into chat. Wait for completion before proceeding to next.

---

## 🔴 PHASE 1: CRITICAL SECURITY FIXES

### Command 1: Fix Ledger Double-Spend in Escrow Release

```
Context: Load src/economics/ledger.py (lines 322-391, the release_escrow method).

Task: Create a test file tests/test_remediation_escrow_double_spend.py that demonstrates the double-spend vulnerability. The test should:
- Create a ledger with an account that has 1000 credits
- Escrow 500 credits
- Launch 2 concurrent threads that both call release_escrow() with the same escrow_id
- Assert that only ONE release succeeds (currently both will succeed - this is the bug)
- Assert the source account's locked balance is only reduced by 500 (not 1000)

Task: Refactor src/economics/ledger.py release_escrow() method to fix the race condition by:
- Moving the transaction context (with self.conn:) to wrap the entire function body
- Moving the "released" check inside the transaction
- Ensuring atomic read-modify-write pattern

Task: Run pytest tests/test_remediation_escrow_double_spend.py -v to confirm the test now passes.

Task: Update REMEDIATION.md by marking item [ECON-001] as [x] completed.
```

---

### Command 2: Fix Firecracker Mock-Only Sandbox

```
Context: Load src/sandbox/firecracker.py (entire file, particularly __init__ method lines 79-99 and _real_exec method lines 285-297).

Task: Create a test file tests/test_remediation_firecracker_fail_closed.py that tests the fail-closed behavior. The test should:
- Mock _is_firecracker_available() to return False
- Attempt to create FirecrackerVM(mock_mode=False)
- Assert that a SandboxError is raised with message about Firecracker not being available
- Currently this test will FAIL because the system allows mock_mode even when real mode requested

Task: Refactor src/sandbox/firecracker.py to implement fail-closed behavior:
- In __init__, if mock_mode=False and _is_firecracker_available() returns False, raise SandboxError immediately
- Update _real_exec to provide more explicit error if called (keep NotImplementedError but enhance message)
- Add a production_ready() method that returns True only if real Firecracker is available

Task: Run pytest tests/test_remediation_firecracker_fail_closed.py -v to confirm proper fail-closed behavior.

Task: Update REMEDIATION.md by marking item [SAND-001] as [x] completed.
```

---

### Command 3: Enable Slashing Logic in Challenge Outcomes

```
Context: Load src/challenges/outcomes.py (lines 88-143, the _process_upheld method) and src/economics/slashing.py (the entire file for reference).

Task: Create a test file tests/test_remediation_slashing_integration.py that verifies slashing works. The test should:
- Create a CreditLedger and StakeManager
- Create a SlashingRules instance
- Create an OutcomeHandler with the ledger
- Set up a verifier account with 10000 staked credits
- Process an UPHELD outcome
- Assert that the verifier's stake is reduced by 50% (5000 credits)
- Assert that the challenger receives the reward
- Currently this test will FAIL because slashing is commented out

Task: Refactor src/challenges/outcomes.py to integrate slashing:
- In _process_upheld (line 122-124), uncomment and implement the actual slashing call using SlashingRules
- In _process_upheld (line 128-130), uncomment and implement the escrow release and reward transfer
- Import SlashingRules at the top of the file
- Update __init__ to accept stake_manager parameter

Task: Run pytest tests/test_remediation_slashing_integration.py -v to confirm slashing now works.

Task: Update REMEDIATION.md by marking item [ECON-002] as [x] completed.
```

---

### Command 4: Add Negative Balance CHECK Constraints

```
Context: Load src/economics/ledger.py (lines 60-101, the _init_schema method).

Task: Create a test file tests/test_remediation_negative_balance.py that verifies negative balances are prevented. The test should:
- Create a fresh ledger database
- Create account with 100 credits
- Attempt to transfer 200 credits (more than balance)
- Assert that an InsufficientBalanceError is raised (currently won't raise due to missing pre-check)
- For databases that already have CHECK constraints, attempt direct SQL update (should fail)

Task: Refactor src/economics/ledger.py to add CHECK constraints:
- In _init_schema method, modify the accounts table CREATE statement to add:
  - CHECK(balance >= 0)
  - CHECK(locked >= 0)
  - CHECK(unbonding >= 0)
- Add a pre-flight check in transfer() method before the transaction to ensure sufficient balance
- Add similar checks in escrow() method

Task: Run pytest tests/test_remediation_negative_balance.py -v to confirm constraints work.

Task: Update REMEDIATION.md by marking item [ECON-004] as [x] completed.
```

---

### Command 5: Implement Mint Authorization

```
Context: Load src/economics/ledger.py (lines 103-148, the create_account method) and src/economics/operations.py (for OpType enum).

Task: Create a test file tests/test_remediation_mint_authorization.py that tests mint limits. The test should:
- Create a ledger
- Define a SYSTEM_ACCOUNT constant for authorized minter
- Attempt to create account with initial_balance as non-system user
- Assert that ValueError is raised for unauthorized mint
- Create account as system user should succeed
- Currently this test will FAIL because anyone can mint

Task: Refactor src/economics/ledger.py to add mint authorization:
- Add SYSTEM_ACCOUNT_ID constant (e.g., "system")
- Modify create_account to accept optional minter_id parameter (defaults to "system")
- If initial_balance > 0 and minter_id != SYSTEM_ACCOUNT_ID, raise ValueError
- Add total_supply tracking (new table or cached value)
- Add MAX_SUPPLY constant and enforce in MINT operations

Task: Run pytest tests/test_remediation_mint_authorization.py -v to confirm authorization works.

Task: Update REMEDIATION.md by marking item [ECON-003] as [x] completed.
```

---

### Command 6: Implement Sybil Resistance for DID Creation

```
Context: Load src/identity/did.py (lines 58-112, the create_did_key method) and src/economics/ledger.py (for stake integration).

Task: Create a test file tests/test_remediation_sybil_resistance.py that tests identity cost. The test should:
- Create a DIDManager with a ledger
- Attempt to create 1000 DIDs in a loop
- Measure total cost (should be high enough to prevent spam)
- Assert that creating DIDs requires either:
  - Proof-of-work (computational cost), OR
  - Minimum stake deposit (economic cost)
- Currently this test will FAIL because DID creation is free

Task: Refactor src/identity/did.py to add sybil resistance:
- Add optional ledger parameter to DIDManager.__init__
- Add MIN_DID_STAKE constant (e.g., 1000 credits)
- In create_did_key, if ledger is provided, require stake or PoW
- Implement simple PoW: hash(seed + nonce) must have N leading zeros
- Add rate limiting: track DID creation timestamps, max 10 per hour per account

Task: Run pytest tests/test_remediation_sybil_resistance.py -v to confirm DIDs now have cost.

Task: Update REMEDIATION.md by marking item [SEC-001] as [x] completed.
```

---

### Command 7: Make Policy Enforcement Mandatory

```
Context: Load src/bus.py (lines 68-108, the publish_envelope function) and src/handlers/yield_handler.py (as example handler).

Task: Create a test file tests/test_remediation_policy_bypass.py that tests policy cannot be skipped. The test should:
- Create a malicious envelope with invalid kind (not in ALLOWED_KINDS)
- Attempt to call a handler directly (bypassing bus)
- Assert that the handler rejects the invalid envelope
- Attempt to publish via bus
- Assert that publish_envelope raises ValueError
- Currently direct handler calls may succeed (bypass vulnerability)

Task: Refactor handlers to enforce policy:
- Create a new decorator @require_policy_validation in src/policy/enforcement.py
- Wrap all handler functions with this decorator
- Decorator should call GateEnforcer.ingress_validate() and raise if not allowed
- Update src/handlers/yield_handler.py to use the decorator
- Update src/bus.py to make validate_envelope non-optional (remove try/except fallback)

Task: Run pytest tests/test_remediation_policy_bypass.py -v to confirm policy is enforced.

Task: Update REMEDIATION.md by marking item [SEC-002] as [x] completed.
```

---

## ⚠️ PHASE 2: HIGH SEVERITY FIXES

### Command 8: Fix Async/Threading Mismatch in PlanStore

```
Context: Load src/plan_store.py (entire file, particularly __init__ and append_op methods) and src/handlers/yield_handler.py (lines 47, 61 where plan_store is called).

Task: Create a test file tests/test_remediation_async_planstore.py that tests concurrent async operations. The test should:
- Create a PlanStore
- Define 100 async tasks that all call append_op() concurrently
- Use asyncio.gather() to run them in parallel
- Assert all operations complete without deadlock or errors
- Measure completion time (should be fast with proper async)
- Currently this may deadlock or be very slow due to threading.Lock

Task: Refactor src/plan_store.py to be async-safe:
- Change self.lock from threading.Lock() to asyncio.Lock()
- Make append_op() an async def function
- Add async with self.lock instead of with self.lock
- Make get_task() and get_ops_for_thread() async as needed
- Update annotate_task() to be async

Task: Refactor all handler files that call plan_store to await the async methods:
- Update src/handlers/yield_handler.py to await plan_store.append_op()
- Search for other plan_store calls and update them

Task: Run pytest tests/test_remediation_async_planstore.py -v to confirm async safety.

Task: Update REMEDIATION.md by marking item [RACE-001] as [x] completed.
```

---

### Command 9: Fix Integer Overflow in Slash Distribution

```
Context: Load src/economics/slashing.py (lines 275-278, the distribution calculation in slash_verifiers method).

Task: Create a test file tests/test_remediation_slash_precision.py that tests distribution accuracy. The test should:
- Test with total_slashed = 999 (odd number)
- Calculate distribution using current float method
- Calculate distribution using proposed integer method
- Assert integer method gives exact 50/40/10 split with no rounding errors
- Test with very large number (near max int) to ensure no overflow

Task: Refactor src/economics/slashing.py to use integer arithmetic:
- Replace line 276: challenger_payout = (total_slashed * 50) // 100
- Replace line 277: honest_total = (total_slashed * 40) // 100
- Line 278 burned calculation remains the same (handles remainder)
- Add assertion to verify sum equals total_slashed

Task: Run pytest tests/test_remediation_slash_precision.py -v to confirm exact distribution.

Task: Update REMEDIATION.md by marking item [ECON-005] as [x] completed.
```

---

### Command 10: Add YIELD Handler Error Handling

```
Context: Load src/handlers/yield_handler.py (entire file, currently has zero error handling).

Task: Create a test file tests/test_remediation_yield_error_handling.py that tests error resilience. The test should:
- Test with missing thread_id in envelope (should handle gracefully)
- Test with missing payload (should handle gracefully)
- Test with missing task_id in payload (should handle gracefully)
- Test with database error (mock plan_store to raise exception)
- Assert that handler logs errors but doesn't crash
- Assert malformed envelopes don't corrupt data

Task: Refactor src/handlers/yield_handler.py to add comprehensive error handling:
- Wrap entire handler in try/except block
- Validate envelope.get("thread_id") is not None before proceeding
- Validate envelope.get("payload") is not None
- Use payload.get("task_id") with None check
- Catch sqlite3.OperationalError specifically for database lock errors
- Log all errors with sufficient context
- Return early on validation failures (don't raise, just log and return)

Task: Run pytest tests/test_remediation_yield_error_handling.py -v to confirm resilience.

Task: Update REMEDIATION.md by marking item [ERR-001] as [x] completed.
```

---

### Command 11: Optimize Lamport Clock File I/O

```
Context: Load src/lamport.py (entire file, particularly tick and observe methods).

Task: Create a benchmark file tests/bench_remediation_lamport.py that measures throughput. The benchmark should:
- Create a Lamport clock
- Measure time to perform 1000 tick() operations
- Calculate ticks per second
- Current implementation should be slow (< 200 ticks/sec due to file I/O)
- Target: > 1000 ticks/sec after optimization

Task: Refactor src/lamport.py to implement write batching:
- Add _dirty flag to track if counter changed since last write
- Add _last_write_time to track when we last persisted
- In tick(), only set _dirty = True, don't write immediately
- Add async _background_flusher() method that writes every 1 second or every 100 ticks
- Keep observe() synchronous for correctness (always write)
- Add flush() method for manual persistence

Task: Run the benchmark again to confirm > 1000 ticks/sec throughput.

Task: Update REMEDIATION.md by marking item [ERR-002] as [x] completed.
```

---

### Command 12: Integrate Three-Gate Policy Enforcement

```
Context: Load src/policy/gates.py (entire file, the GateEnforcer class) and src/handlers/commit.py (as example handler to integrate).

Task: Create a test file tests/test_remediation_three_gates.py that validates all gates trigger. The test should:
- Create a GateEnforcer
- Test PREFLIGHT gate on publish (should cache results)
- Test INGRESS gate on receive (should use WASM runtime)
- Test COMMIT_GATE with telemetry (should detect resource violations)
- Assert all three gates are invoked in proper scenarios
- Currently gates may not be called

Task: Refactor src/handlers/commit.py to use commit_gate_validate:
- Import GateEnforcer at the top
- Before processing COMMIT, call gate_enforcer.commit_gate_validate(envelope, telemetry)
- If decision.allowed is False, reject the envelope and log reason
- Extract telemetry from envelope payload

Task: Verify src/bus.py already calls preflight_validate (lines 88-93) and ingress_validate (lines 146-151).

Task: Run pytest tests/test_remediation_three_gates.py -v to confirm integration.

Task: Update REMEDIATION.md by marking item [ARCH-001] as [x] completed.
```

---

## 📋 PHASE 3: MEDIUM SEVERITY FIXES

### Command 13: Implement Per-Agent Keypairs

```
Context: Load src/crypto.py (entire file) and src/identity/did.py (for integration).

Task: Create a test file tests/test_remediation_agent_keys.py that validates unique signatures. The test should:
- Create two agents with different IDs
- Have each agent sign the same message
- Assert the signatures are different
- Verify each signature with the corresponding agent's public key
- Currently using shared keypair will produce identical signatures (bug)

Task: Refactor src/crypto.py to support per-agent keys:
- Add generate_keypair() function that returns (signing_key, verify_key)
- Add save_keypair(agent_id, signing_key) to persist to ~/.swarm/keys/
- Add load_keypair(agent_id) to retrieve agent-specific key
- Modify sign_record to accept optional agent_id parameter
- Fall back to env keypair if agent_id not provided (backward compatibility)

Task: Update src/identity/did.py to use per-agent keys:
- When creating DID, generate and store keypair
- Link DID to keypair in did_cache

Task: Run pytest tests/test_remediation_agent_keys.py -v to confirm unique signatures.

Task: Update REMEDIATION.md by marking item [SEC-003] as [x] completed.
```

---

### Command 14: Fix CAS Silent Fallback

```
Context: Load src/cas_core.py (lines 53-83, the get_cas_store function).

Task: Create a test file tests/test_remediation_cas_fallback.py that tests failure notification. The test should:
- Mock use_ipfs_cas() to return True
- Mock IPFSContentStore to raise ConnectionError
- Call get_cas_store()
- Assert that either:
  - Exception is propagated to caller, OR
  - Return value indicates fallback mode (e.g., tuple (cas, is_fallback))
- Currently returns FileCAS silently (bug)

Task: Refactor src/cas_core.py to make fallback explicit:
- Change get_cas_store() return type to tuple: (cas_instance, is_ipfs_mode: bool)
- If IPFS fails, log ERROR and return (FileCAS(...), False)
- If IPFS succeeds, return (IPFSContentStore(...), True)
- Update all callers to check is_ipfs_mode flag
- Add health check endpoint that reports CAS backend status

Task: Run pytest tests/test_remediation_cas_fallback.py -v to confirm notification.

Task: Update REMEDIATION.md by marking item [STAB-001] as [x] completed.
```

---

### Command 15: Implement Bus Connection Pooling

```
Context: Load src/bus.py (lines 42-47 connect function and lines 49-59 publish_raw function).

Task: Create a benchmark file tests/bench_remediation_bus_pool.py that measures publish throughput. The benchmark should:
- Measure time to publish 100 messages with current implementation
- Calculate messages per second
- After fix, measure again and assert > 5x improvement
- Current implementation creates new connection per publish (slow)

Task: Refactor src/bus.py to implement connection pooling:
- Create a ConnectionPool class with get() and release() methods
- Use a module-level pool instance
- In publish_raw, get connection from pool instead of calling connect()
- Return connection to pool after use (don't drain)
- Add pool.close_all() for graceful shutdown
- Implement max_size limit (e.g., 10 connections)

Task: Run the benchmark to confirm > 5x throughput improvement.

Task: Update REMEDIATION.md by marking item [STAB-003] as [x] completed.
```

---

### Command 16: Add IPFS Timeout and Circuit Breaker

```
Context: Load src/cas/ipfs_store.py (lines 93-123, the get method).

Task: Create a test file tests/test_remediation_ipfs_timeout.py that tests timeout behavior. The test should:
- Mock IPFS client to sleep for 30 seconds
- Call ipfs_store.get(cid) with timeout=5
- Assert that RuntimeError is raised within 5 seconds
- Currently this will hang for 30 seconds (bug)

Task: Refactor src/cas/ipfs_store.py to add timeout support:
- Add timeout parameter to get() method (default 5 seconds)
- Wrap self.client.get_content() with asyncio.wait_for or threading.Timer
- Implement circuit breaker pattern: after 3 consecutive failures, skip IPFS for 60s
- Add _circuit_breaker_open flag and _failure_count counter
- Log when circuit breaker opens/closes

Task: Run pytest tests/test_remediation_ipfs_timeout.py -v to confirm fast failure.

Task: Update REMEDIATION.md by marking item [STAB-004] as [x] completed.
```

---

### Command 17: Implement Auction Anti-Sniping

```
Context: Load src/auction/bidding.py (lines 64-115, the accept_bid method).

Task: Create a test file tests/test_remediation_auction_snipe.py that tests bid extension. The test should:
- Start auction with 30 second window
- Submit bid at T=29 seconds (last second)
- Assert that bid window extends to T=34 seconds (+ 5s)
- Submit another bid at T=33s
- Assert window extends again
- Currently bid at T=29s closes at T=30s (allows sniping)

Task: Refactor src/auction/bidding.py to add anti-sniping timer:
- In accept_bid, calculate time_until_close
- If time_until_close < 5 seconds and bid is accepted:
  - Extend auction["start_time"] by 5 seconds
  - Log "Bid window extended due to late bid"
- Add max_extensions limit (e.g., 3) to prevent infinite extension
- Track extensions in auction state

Task: Run pytest tests/test_remediation_auction_snipe.py -v to confirm extension works.

Task: Update REMEDIATION.md by marking item [ECON-007] as [x] completed.
```

---

### Command 18: Validate Honest Verifier Rewards

```
Context: Load src/economics/slashing.py (lines 205-248, the slash_verifiers method) and src/audit.py (for attestation log).

Task: Create a test file tests/test_remediation_honest_proof.py that validates honest verifier list. The test should:
- Set up a scenario with 5 verifiers
- Record ATTEST messages from 3 verifiers (honest)
- 2 verifiers don't attest (dishonest)
- Call slash_verifiers with honest_verifiers=["attacker_sybil"] (fake)
- Assert that only actual attestors receive rewards
- Currently accepts honest_verifiers without validation (bug)

Task: Refactor src/economics/slashing.py to verify honest_verifiers:
- Add required parameter: attestation_log (list of ATTEST records)
- Before distributing rewards, verify each honest_verifier actually attested
- Filter honest_verifiers to only include verified attestors
- Log warning if honest_verifiers contains non-attestors
- Only distribute to verified honest verifiers

Task: Run pytest tests/test_remediation_honest_proof.py -v to confirm validation.

Task: Update REMEDIATION.md by marking item [ECON-008] as [x] completed.
```

---

### Command 19: Scale Challenge Rewards by Slashed Amount

```
Context: Load src/challenges/outcomes.py (lines 42, 106-107, the reward calculation).

Task: Create a test file tests/test_remediation_reward_scaling.py that tests proportional rewards. The test should:
- Scenario 1: Challenge 1 verifier with 10k stake → 5k slashed
- Scenario 2: Challenge 10 verifiers with 10k each → 50k slashed
- Assert scenario 2 reward is ~10x scenario 1 reward
- Currently both scenarios give same 2x bond reward (bug)

Task: Refactor src/challenges/outcomes.py to scale rewards:
- Remove UPHELD_REWARD_MULTIPLIER constant
- In _process_upheld, calculate actual total_slashed from verifiers
- Set reward_amount = int(total_slashed * 0.20)  # 20% of slashed
- Ensure challenger gets bond back + proportional reward
- Update tests to reflect new reward formula

Task: Run pytest tests/test_remediation_reward_scaling.py -v to confirm scaling.

Task: Update REMEDIATION.md by marking item [ECON-009] as [x] completed.
```

---

### Command 20: Validate Transfer Recipients

```
Context: Load src/economics/ledger.py (lines 191-271, the transfer method).

Task: Create a test file tests/test_remediation_transfer_validation.py that tests recipient check. The test should:
- Create ledger with account A (1000 credits)
- Attempt to transfer to non-existent account B
- Assert ValueError is raised with message "Recipient account does not exist"
- Currently auto-creates account B (bug allows typos to lose funds)

Task: Refactor src/economics/ledger.py to require recipient exists:
- In transfer method, before the transaction, check if to_id exists
- If cursor.fetchone() is None, raise ValueError
- Add optional parameter allow_create_recipient (default False)
- If allow_create_recipient=True, allow auto-creation (backward compatibility)
- Update documentation to recommend explicit account creation

Task: Run pytest tests/test_remediation_transfer_validation.py -v to confirm validation.

Task: Update REMEDIATION.md by marking item [ECON-010] as [x] completed.
```

---

## 🔧 PHASE 4: ARCHITECTURE & INTEGRATION

### Command 21: Deploy etcd Consensus Service

```
Context: Load docker-compose.yml and src/consensus/raft_adapter.py (entire file).

Task: Create integration test tests/test_remediation_etcd_consensus.py that validates etcd DECIDE. The test should:
- Require etcd service to be running (skip if not available)
- Create RaftConsensusAdapter instance
- Test try_decide() for same need_id from 2 different agents
- Assert only one DECIDE succeeds
- Assert loser can read winner's DECIDE
- Currently will fail because etcd not deployed

Task: Update docker-compose.yml to add etcd service:
- Add etcd service with 3-node cluster configuration
- Expose ports 2379 (client) and 2380 (peer)
- Configure data persistence volume
- Add health check

Task: Update src/coordinator.py to use RaftConsensusAdapter instead of Redis:
- Import RaftConsensusAdapter
- Replace consensus initialization with etcd backend
- Update DECIDE handler to use try_decide()

Task: Run docker-compose up -d etcd and then pytest tests/test_remediation_etcd_consensus.py -v.

Task: Update REMEDIATION.md by marking item [DIST-001] as [x] completed.
```

---

### Command 22: Implement Partition Detection

```
Context: Load src/consensus/merge.py (the merge_on_heal method) and create new src/monitoring/partition_detector.py.

Task: Create a test file tests/test_remediation_partition_detection.py that simulates network partition. The test should:
- Start 3 nodes with heartbeat monitoring
- Simulate partition: disconnect node 3 from nodes 1,2
- Assert PartitionDetector detects split within 30 seconds
- Assert epoch automatically advances
- Assert RECONCILE message is sent
- Currently no detection exists

Task: Create new file src/monitoring/partition_detector.py with:
- PartitionDetector class that monitors peer heartbeats
- detect_partition() method that checks for missing heartbeats
- on_partition_heal() callback that sends RECONCILE
- Integration with epoch_manager.advance_epoch()

Task: Integrate partition detector into coordinator:
- Start detector in coordinator startup
- Configure heartbeat interval (10 seconds)
- Configure partition threshold (3 missed heartbeats)

Task: Run pytest tests/test_remediation_partition_detection.py -v to confirm detection.

Task: Update REMEDIATION.md by marking item [PART-001] as [x] completed.
```

---

### Command 23: Integrate State Reconciliation

```
Context: Load src/handlers/reconcile.py (entire file) and src/consensus/merge.py (merge_on_heal method).

Task: Create integration test tests/test_remediation_state_reconcile.py that validates reconciliation. The test should:
- Simulate partition with conflicting DECIDE records
- Trigger RECONCILE handler with local and remote decides
- Assert merge_on_heal is called
- Assert winner is selected by highest_epoch_wins rule
- Assert orphaned branches are marked
- Currently RECONCILE handler exists but never called

Task: Update src/monitoring/partition_detector.py to trigger reconciliation:
- On partition heal, fetch local DECIDEs
- Fetch remote DECIDEs from rejoined peer
- Publish RECONCILE envelope with both sets
- Include epoch advancement reason

Task: Verify src/handlers/reconcile.py properly calls MergeHandler:
- Ensure merge_handler.merge_on_heal() is invoked
- Ensure mark_orphaned() is called for losing branches
- Add error handling for merge failures

Task: Run pytest tests/test_remediation_state_reconcile.py -v to confirm reconciliation.

Task: Update REMEDIATION.md by marking item [PART-002] and [ARCH-002] as [x] completed.
```

---

## 📊 PHASE 5: PERFORMANCE & MONITORING

### Command 24: Implement Async SQLite for PlanStore

```
Context: Load src/plan_store.py (entire file) after async locks are already implemented.

Task: Create benchmark tests/bench_remediation_async_db.py that measures database throughput. The benchmark should:
- Measure ops/sec with current blocking SQLite
- Measure ops/sec with aiosqlite
- Assert > 2x improvement with async
- Test under concurrent load (100 tasks)

Task: Refactor src/plan_store.py to use aiosqlite:
- Add aiosqlite to requirements.txt
- Import aiosqlite instead of sqlite3
- Make all database operations async (await conn.execute())
- Update __init__ to use await aiosqlite.connect()
- Ensure async context managers for transactions

Task: Run the benchmark to confirm > 2x throughput improvement.

Task: Update REMEDIATION.md by marking item [PERF-001] as [x] completed.
```

---

### Command 25: Create Economic Attack Test Suite

```
Context: Review all economic vulnerability tests created so far.

Task: Create comprehensive test suite tests/test_remediation_economic_attacks.py that includes:
- All double-spend scenarios (escrow, transfer, rewards)
- All sybil attacks (identity spam, verifier spam)
- Whale attacks on committee selection
- Auction manipulation (sniping, collusion)
- Slashing manipulation (fake honest verifiers)
- Each test should have clear attack description and expected defense

Task: Organize tests with pytest markers:
- @pytest.mark.security_critical for severe attacks
- @pytest.mark.economic for game theory exploits
- @pytest.mark.slow for tests requiring > 5 seconds

Task: Run pytest tests/test_remediation_economic_attacks.py -v -m security_critical to run critical tests.

Task: Update REMEDIATION.md by marking item [TEST-002] as [x] completed.
```

---

## ✅ COMPLETION VERIFICATION

### Command 26: Run Full Remediation Test Suite

```
Task: Run the complete remediation test suite to verify all fixes:

pytest tests/test_remediation_*.py -v --tb=short

Task: Generate coverage report for remediated code:

pytest tests/test_remediation_*.py --cov=src/economics --cov=src/sandbox --cov=src/policy --cov-report=html

Task: Review coverage report and ensure all critical paths are tested.

Task: Update REMEDIATION.md with final completion status and coverage percentage.

Task: Create final summary in REMEDIATION.md showing:
- Total issues identified: 50+
- Critical issues fixed: X
- High severity fixed: Y
- Medium severity fixed: Z
- Test coverage: N%
- Remaining items: [list any incomplete items]
```

---

## 📝 NOTES

**Execution Order:** Commands must be executed sequentially. Each command depends on previous fixes.

**Testing:** After each command, verify tests pass before proceeding. Do not skip test creation.

**Rollback:** If a fix breaks existing tests, rollback and revise approach before proceeding.

**Documentation:** Update REMEDIATION.md checkbox after each successful completion.

**Estimated Timeline:**
- Phase 1 (Critical Security): ~8-12 hours
- Phase 2 (High Severity): ~6-8 hours  
- Phase 3 (Medium Severity): ~6-8 hours
- Phase 4 (Architecture): ~8-10 hours
- Phase 5 (Performance): ~4-6 hours
- **Total: ~32-44 hours of focused development**

**Success Criteria:**
- All critical security issues resolved
- All high severity issues resolved
- >80% test coverage on modified code
- No regressions in existing functionality
- REMEDIATION.md shows clear progress tracking
