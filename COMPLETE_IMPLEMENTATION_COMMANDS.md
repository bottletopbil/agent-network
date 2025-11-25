# CAN Swarm Complete Implementation Commands
**Step-by-Step Instructions from v1 PoC → Full Decentralized Agent Economy**

This document provides concrete, copy-paste commands to implement each phase of the complete CAN Swarm roadmap. Commands are sized for manageable implementation sessions with clear checkpoints.

---

## 📋 How to Use This Guide

1. **Read the** [COMPLETE_ROADMAP.md](COMPLETE_ROADMAP.md) **first** to understand the overall architecture
2. **Work through phases sequentially** unless otherwise noted
3. **Complete each checkpoint** before moving to the next command
4. **Run tests frequently** to catch issues early
5. **Document as you go** - update API.md and ARCHITECTURE.md

**Parallel Opportunities** are marked with 🔀 when commands can run concurrently.

---

## PHASE 6: ECONOMIC FOUNDATION

### Command 21: Credit Ledger

```
Implement Phase 6.1 - Credit Ledger:

Create src/economics/ directory and implement credit system:

1. Create src/economics/__init__.py (empty)

2. Create src/economics/ledger.py with:
   - Account class: account_id, balance, locked, unbonding
   - CreditLedger class with:
     - create_account(account_id, initial_balance)
     - get_balance(account_id)
     - transfer(from_id, to_id, amount)
     - escrow(account_id, amount, escrow_id)
     - release_escrow(escrow_id, to_id)
     - cancel_escrow(escrow_id)
   - Audit trail for all operations
   - SQLite backend for persistence

3. Create src/economics/operations.py with:
   - OpType enum: MINT, TRANSFER, ESCROW, RELEASE, SLASH
   - LedgerOp dataclass (op_id, account, operation, amount, timestamp)
   - Operation validation rules

4. Create tests/test_ledger.py with:
   - test_create_account
   - test_transfer_sufficient_balance
   - test_transfer_insufficient_balance
   - test_escrow_and_release
   - test_escrow_and_cancel
   - test_audit_trail

Run: pytest tests/test_ledger.py -v
```

**Checkpoint:** Credit ledger works with transfers and escrow

---

### Command 22: Stake System

```
Implement Phase 6.2 - Stake System:

1. Create src/economics/stake.py with:
   - StakeManager class:
     - stake(account_id, amount) # Lock credits
     - unstake(account_id, amount) # Start unbonding
     - complete_unbonding(account_id) # After unbonding period
     - get_staked_amount(account_id)
     - get_unbonding_amount(account_id)
   - Unbonding period: 7 days (configurable)
   - Slash conditions:
     - Failed challenge on ATTEST
     - Missing heartbeats
     - Policy violations

2. Create src/economics/slashing.py with:
   - SlashEvent dataclass (account_id, reason, amount, evidence_hash)
   - SlashingRules class:
     - calculate_slash_amount(violation_type, severity)
     - execute_slash(account_id, event)
   - Slashing percentages:
     - Failed challenge: 50% of stake
     - Missing heartbeats: 1% per miss
     - Policy violation: 10% (escalating)

3. Create tests/test_stake.py with:
   - test_stake_and_unstake
   - test_unbonding_period
   - test_slashing_execution
   - test_stake_requirements

Run: pytest tests/test_stake.py -v
```

**Checkpoint:** Stake/unstake works, slashing implemented

---

### Command 23A: Verifier Pool Registration 🔀

```
Implement Phase 6.3A - Verifier Pool Registration:

1. Create src/economics/pools.py with:
   - VerifierPool class:
     - register(verifier_id, stake, capabilities, metadata)
     - deregister(verifier_id)
     - get_pool_members()
     - get_active_verifiers(min_stake)
   - Metadata: org_id, asn, region, reputation
   - SQLite backend for pool storage

2. Create tests/test_pools_registration.py with:
   - test_pool_registration
   - test_pool_deregistration
   - test_get_pool_members
   - test_get_active_verifiers
   - test_stake_requirement

Run: pytest tests/test_pools_registration.py -v
```

**Checkpoint:** Verifiers can register and join pools

**Note:** 🔀 Can run in parallel with Command 24

---

### Command 23B: Committee Selection & Reputation 🔀

```
Implement Phase 6.3B - Committee Selection & Reputation:

1. Create src/economics/selection.py with:
   - VerifierSelector class:
     - calculate_weight(verifier) # sqrt(stake) × reputation × recency
     - select_committee(k, diversity_constraints)
     - enforce_diversity(committee) # org/ASN/region caps
   - Diversity constraints:
     - Max 30% from same org
     - Max 40% from same ASN
     - Max 50% from same region

2. Create src/economics/reputation.py with:
   - ReputationTracker class:
     - record_attestation(verifier_id, task_id, verdict)
     - record_challenge(verifier_id, upheld)
     - get_reputation(verifier_id) # 0.0-1.0
   - Decay: 5% per week without activity
   - Boost: +0.1 for successful challenge
   - Penalty: -0.3 for failed attestation

3. Create tests/test_pool_selection.py with:
   - test_committee_selection
   - test_diversity_enforcement
   - test_reputation_calculation
   - test_weight_calculation

Run: pytest tests/test_pool_selection.py -v
```

**Checkpoint:** Committees selected with proper diversity constraints and reputation weighting

**Note:** 🔀 Can run in parallel with Command 24


---

### Command 24: Bounty System 🔀

```
Implement Phase 6.4 - Bounty System:

1. Create src/economics/bounties.py with:
   - BountyManager class:
     - create_bounty(task_id, amount, task_class)
     - escrow_bounty(task_id, commit_id)
     - distribute_bounty(task_id, committee, challenger)
   - Bounty caps by task_class:
     - simple: 10 credits max
     - complex: 100 credits max
     - critical: 1000 credits max
   - Escrow duration: 2 × T_challenge (48 hours default)

2. Update src/handlers/commit.py to include verify_bounty:
   - Add verify_bounty field to COMMIT payload
   - Validate bounty against caps
   - Create ledger escrow
   - Record bounty in plan store

3. Create src/economics/payout.py with:
   - PayoutDistributor class:
     - calculate_shares(committee_size, challenger_present)
     - execute_payout(task_id)
     - validate_related_parties(committee, challenger)
   - Distribution:
     - If no challenge: 100% to committee (split equally)
     - If challenge: 50% challenger, 40% honest verifiers, 10% burn

4. Create tests/test_bounties.py with:
   - test_bounty_creation
   - test_bounty_caps
   - test_payout_no_challenge
   - test_payout_with_challenge
   - test_related_party_check

Run: pytest tests/test_bounties.py -v
```

**Checkpoint:** Bounties are escrowed and distributed to committees

**Note:** 🔀 Can run in parallel with Command 23

---

## PHASE 7: MARKET-STYLE NEGOTIATION

### Command 25A: Basic Negotiation Verbs

```
Implement Phase 7.1A - Basic Negotiation Verbs:

1. Update src/policy.py to add new verbs:
   ALLOWED_KINDS = {
     "NEED", "PROPOSE", "CLAIM", "COMMIT", "ATTEST", "DECIDE", "FINALIZE",
     "YIELD", "RELEASE", "UPDATE_PLAN"
   }

2. Create src/handlers/yield.py:
   - handle_yield(envelope):
     - Release lease
     - Update task state to DRAFT
     - Allow re-claiming
   - Yield payload:
     - task_id, reason

3. Create src/handlers/release.py:
   - handle_release(envelope):
     - Expire lease (system-initiated)
     - Scavenge task
     - Notify coordinator
   - Release payload:
     - task_id, lease_id, reason (timeout/heartbeat_miss)

4. Create src/handlers/update_plan.py:
   - handle_update_plan(envelope):
     - Validate plan update
     - Apply to plan store
     - Broadcast to peers
   - Update_plan payload:
     - thread_id, ops[]

5. Create tests/test_basic_negotiation.py:
   - test_yield_release_task
   - test_release_on_timeout
   - test_update_plan

Run: pytest tests/test_basic_negotiation.py -v
```

**Checkpoint:** Basic negotiation verbs (YIELD, RELEASE, UPDATE_PLAN) work

---

### Command 25B: Extended Proposal & Claim Handlers

```
Implement Phase 7.1B - Extended Proposal & Claim Handlers:

1. Update src/policy.py to add:
   ALLOWED_KINDS.add("ATTEST_PLAN")

2. Create src/handlers/propose_extended.py:
   - handle_propose_extended(envelope):
     - Validate ballot (must be unique per proposer)
     - Validate patch (must be valid plan ops)
     - Record proposal in plan store
     - Broadcast to verifiers for ATTEST_PLAN
   - Proposal payload:
     - need_id, proposal_id, patch[], ballot, cost, eta

3. Create src/handlers/claim_extended.py:
   - handle_claim_extended(envelope):
     - Validate lease_ttl (must be > min_lease)
     - Create lease record
     - Start heartbeat expectation
     - Update task state to CLAIMED
   - Claim payload:
     - task_id, worker_id, lease_ttl, cost, eta, heartbeat_interval

4. Create src/handlers/attest_plan.py:
   - handle_attest_plan(envelope):
     - Validate verifier is in pool
     - Record attestation for proposal
     - Check if K_plan reached
   - Attest_plan payload:
     - need_id, proposal_id, verdict

5. Create tests/test_extended_handlers.py:
   - test_propose_with_ballot
   - test_claim_with_lease
   - test_attest_plan

Run: pytest tests/test_extended_handlers.py -v
```

**Checkpoint:** Extended proposal and claim handlers work with attestation


---

### Command 26A: Lease Core Management

```
Implement Phase 7.2A - Lease Core:

1. Create src/leases/__init__.py

2. Create src/leases/manager.py with:
   - LeaseRecord dataclass:
     - lease_id, task_id, worker_id, ttl, created_at, last_heartbeat
   - LeaseManager class:
     - create_lease(task_id, worker_id, ttl, heartbeat_interval)
     - renew_lease(lease_id)
     - heartbeat(lease_id)
     - check_expiry() # Check if expired
     - get_lease(lease_id)
     - get_leases_for_worker(worker_id)

3. Create src/leases/heartbeat.py with:
   - HeartbeatProtocol class:
     - expect_heartbeat(lease_id, interval)
     - receive_heartbeat(lease_id)
     - check_missed_heartbeats()
     - get_next_expected_heartbeat(lease_id)

4. Update src/handlers/heartbeat.py:
   - handle_heartbeat(envelope):
     - Validate lease exists
     - Update last_heartbeat timestamp
     - Record progress
   - HEARTBEAT payload:
     - lease_id, worker_id, progress%

5. Create tests/test_leases_core.py:
   - test_lease_creation
   - test_lease_renewal
   - test_heartbeat_updates
   - test_lease_expiry_check

Run: pytest tests/test_leases_core.py -v
```

**Checkpoint:** Lease core system works with heartbeat tracking

---

### Command 26B: Lease Monitoring Daemon

```
Implement Phase 7.2B - Lease Monitoring:

1. Create src/daemons/__init__.py

2. Create src/daemons/lease_monitor.py:
   - LeaseMonitor class:
     - start() # Start monitoring loop
     - stop() # Stop monitoring
     - check_expired_leases() # Check every 10 seconds
     - handle_expired(lease_id) # Publish RELEASE
     - handle_missed_heartbeat(lease_id) # Slash worker
   - Background daemon that runs continuously

3. Update src/leases/manager.py:
   - Add scavenge_expired() method
     - Returns list of expired lease_ids
     - Called by daemon

4. Integrate with coordinator:
   - src/coordinator.py starts LeaseMonitor on init
   - Monitor publishes RELEASE for expired leases

5. Create tests/test_lease_monitor.py:
   - test_monitor_detects_expired_lease
   - test_monitor_publishes_release
   - test_monitor_handles_missed_heartbeat
   - test_scavenge_on_timeout

Run: pytest tests/test_lease_monitor.py -v
```

**Checkpoint:** Lease monitoring daemon detects and handles expiry


---

### Command 27A: Auction Core System

```
Implement Phase 7.3A - Auction Core:

1. Create src/auction/__init__.py

2. Create src/auction/bidding.py with:
   - AuctionConfig:
     - bid_window (default: 30s)
     - max_rounds (default: 3)
     - min_bid_increment (default: 1%)
   - AuctionManager class:
     - start_auction(need_id, budget)
     - accept_bid(need_id, agent_id, proposal)
     - close_auction(need_id) # Returns winner
     - timeout_auction(need_id) # No bids
     - get_auction_status(need_id)

3. Create src/auction/selection.py with:
   - BidEvaluator class:
     - score_bid(proposal) # Cost, ETA, reputation, capabilities
     - select_winner(bids[])
     - handle_ties(bids[]) # Use reputation as tiebreaker

4. Create src/auction/backoff.py:
   - calculate_backoff(attempt) # Exponential with jitter
   - RandomizedBackoff class

5. Create tests/test_auction_core.py:
   - test_auction_lifecycle
   - test_bid_evaluation
   - test_winner_selection
   - test_timeout_handling
   - test_randomized_backoff

Run: pytest tests/test_auction_core.py -v
```

**Checkpoint:** Auction core system manages bidding and winner selection

---

### Command 27B: Agent Bidding Integration

```
Implement Phase 7.3B - Agent Bidding Integration:

1. Update src/handlers/need.py:
   - Import AuctionManager
   - Trigger auction instead of direct assignment
   - Wait for bid window
   - Select best proposal via AuctionManager
   - Emit DECIDE with winning proposal

2. Update agents/planner.py:
   - Listen for NEED messages
   - Evaluate if can handle task
   - Calculate cost and ETA
   - Submit PROPOSE with bid (cost, ETA, capabilities)
   - Implement randomized backoff on rejection
   - Track bid history

3. Create src/auction/agent_integration.py:
   - Integration helpers for agents
   - Bid submission utilities
   - Cost/ETA calculation helpers

4. Create tests/test_auction_integration.py:
   - test_need_triggers_auction
   - test_planner_submits_bid
   - test_best_bid_wins
   - test_rejected_bid_backoff

Run: pytest tests/test_auction_integration.py -v
```

**Checkpoint:** NEEDs trigger auctions, agents bid, best proposal selected


---

### Command 28: Plan Patching

```
Implement Phase 7.4 - Plan Patching:

1. Create src/plan/patching.py with:
   - PlanPatch class:
     - ops[] # List of ADD_TASK, LINK, etc.
     - base_lamport # Patch applies after this lamport
   - PatchValidator class:
     - validate_patch(patch, current_plan)
     - detect_conflicts(patch, other_patches)
     - merge_patches(patches[])

2. Create src/plan/versioning.py with:
   - PlanVersion dataclass:
     - version_id, lamport, merkle_root
   - VersionTracker class:
     - record_version(plan_state)
     - get_version_at_lamport(lamport)
     - compute_diff(version_a, version_b)

3. Update src/handlers/update_plan.py:
   - handle_update_plan(envelope):
     - Validate patch against current plan
     - Apply patch to plan store
     - Broadcast to peers
     - Update plan version

4. Create conflict resolution rules:
   - Concurrent ADD_TASK: Both kept (G-Set)
   - Concurrent STATE updates: Higher lamport wins (LWW)
   - Concurrent LINK: Both kept if no cycle
   - Conflicting patches: Deterministic merge by (lamport, actor_id)

5. Create tests/test_patching.py:
   - test_apply_patch
   - test_conflict_detection
   - test_merge_rules
   - test_plan_versioning

Run: pytest tests/test_patching.py -v
```

**Checkpoint:** Proposals submit patches, plans merge deterministically

---

## PHASE 8: CHALLENGE PROTOCOL

### Command 29: Challenge Mechanics

```
Implement Phase 8.1 - Challenge Mechanics:

1. Update src/policy.py to add CHALLENGE and INVALIDATE verbs

2. Create src/challenges/__init__.py

3. Create src/challenges/proofs.py with:
   - ProofType enum:
     - SCHEMA_VIOLATION
     - MISSING_CITATION
     - SEMANTIC_CONTRADICTION
     - OUTPUT_MISMATCH
     - POLICY_BREACH
   - ProofSchema dataclass:
     - proof_type, evidence_hash, size_bytes, gas_estimate
   - Proof size limits:
     - Max 10KB per proof
     - Max 100k gas for verification

4. Create src/challenges/window.py with:
   - ChallengeWindow class:
     - create_window(task_id, duration) # Default: 24h
     - get_remaining_time(task_id)
     - is_window_open(task_id)
     - extend_window(task_id, duration) # On valid challenge

5. Create src/handlers/challenge.py:
   - handle_challenge(envelope):
     - Validate challenge window still open
     - Validate proof schema
     - Validate challenger bond posted
     - Queue challenge for verification
   - Challenge payload:
     - task_id, commit_id, proof_type, evidence_hash, bond_amount

6. Create tests/test_challenges.py:
   - test_challenge_submission
   - test_challenge_window
   - test_proof_validation
   - test_invalid_challenge_rejected

Run: pytest tests/test_challenges.py -v
```

**Checkpoint:** Challenges can be submitted with typed proofs

---

### Command 30: Challenge Bonds

```
Implement Phase 8.2 - Challenge Bonds:

1. Create src/challenges/bonds.py with:
   - BondCalculator class:
     - calculate_bond(proof_type, complexity)
     - Bond amounts:
       - schema_violation: 10 credits
       - missing_citation: 25 credits
       - semantic_contradiction: 50 credits
       - output_mismatch: 100 credits
   - Complexity multipliers: 1x, 2x, 5x

2. Update src/handlers/challenge.py:
   - Validate challenger has sufficient balance
   - Create bond escrow via ledger
   - Record bond in challenge record

3. Create src/challenges/outcomes.py with:
   - ChallengeOutcome enum:
     - UPHELD (challenge valid)
     - REJECTED (challenge invalid)
     - WITHDRAWN (challenger withdraws)
   - OutcomeHandler class:
     - process_outcome(challenge_id, outcome)
     - If UPHELD: slash verifiers, return bond + reward
     - If REJECTED: slash bond
     - If WITHDRAWN: return bond minus fee

4. Create anti-abuse measures:
   - src/challenges/abuse_detection.py:
     - Pattern analysis for excessive challenges
     - Rate limiting per challenger
     - Reputation impact on frivolous challenges

5. Create tests/test_bonds.py:
   - test_bond_calculation
   - test_bond_escrow
   - test_bond_return_on_upheld
   - test_bond_slash_on_rejected

Run: pytest tests/test_bonds.py -v
```

**Checkpoint:** Bonds required for challenges, slashed if frivolous

---

### Command 31A: Challenge Verification Core

```
Implement Phase 8.3A - Challenge Verification Core:

1. Create src/challenges/verification.py with:
   - ChallengeVerifier class:
     - verify_schema_violation(proof)
     - verify_missing_citation(proof)
     - verify_semantic_contradiction(proof)
     - verify_output_mismatch(proof)
   - Gas-metered execution
   - Deterministic verification rules

2. Create src/challenges/queue.py:
   - ChallengeQueue class:
     - add_challenge(challenge_id, proof)
     - get_next_challenge()
     - prioritize_by_bond() # Higher bond = faster
     - mark_verified(challenge_id, result)

3. Create src/challenges/escalation.py:
   - EscalationHandler class:
     - escalate_if_disagree(challenge_id, verdicts[])
     - create_human_review_task(challenge_id)
     - governance_vote(challenge_id) # For complex cases

4. Create tests/test_verification_core.py:
   - test_schema_violation_detection
   - test_citation_verification
   - test_queue_prioritization
   - test_escalation_path

Run: pytest tests/test_verification_core.py -v
```

**Checkpoint:** Challenge verification core logic works with escalation

---

### Command 31B: Challenge Verifier Agent

```
Implement Phase 8.3B - Challenge Verifier Agent:

1. Create agents/challenge_verifier.py:
   - ChallengeVerifierAgent class (extends BaseAgent)
     - Listens for CHALLENGE messages
     - Pulls from challenge queue
     - Runs verification logic via ChallengeVerifier
     - Publishes verdict (UPHOLD/REJECT)
     - Requires stake to participate

2. Add agent initialization:
   - Register with verifier pool
   - Stake minimum required amount
   - Subscribe to challenge topics

3. Integrate with verification queue:
   - Agent claims challenges from queue
   - Multiple verifiers can verify same challenge
   - Consensus on verdict required

4. Create tests/test_challenge_verifier_agent.py:
   - test_agent_listens_for_challenges
   - test_agent_verifies_challenge
   - test_agent_publishes_verdict
   - test_agent_requires_stake

Run: pytest tests/test_challenge_verifier_agent.py -v
```

**Checkpoint:** Challenge verifier agents automatically process challenges


---

### Command 32: Slashing and Payouts

```
Implement Phase 8.4 - Slashing and Payouts:

1. Create src/handlers/invalidate.py:
   - handle_invalidate(envelope):
     - Mark result as invalid
     - Slash attesting verifiers
     - Reopen task for re-execution
     - Escalate K_result requirement
   - INVALIDATE payload:
     - task_id, challenge_id, slashed_verifiers[], new_k_result

2. Update src/economics/slashing.py:
   - slash_verifiers(verifiers[], challenge_evidence)
   - Slash percentage: 50% of stake per verifier
   - Distribute slashed amount:
     - 50% to challenger
     - 40% to honest verifiers (if any)
     - 10% burned

3. Update src/economics/payout.py:
   - Payout only after 2 × T_challenge elapses
   - Validate no related parties in committee
   - Block payout if INVALIDATE occurred

4. Create related-party detection:
   - src/economics/relationships.py:
     - detect_same_org(verifiers[], challenger)
     - detect_same_asn(verifiers[], challenger)
     - detect_identity_links(verifiers[], challenger)
   - Block payout if relationships detected

5. K_result escalation:
   - If challenge upheld: K_result += 2
   - If multiple challenges on same task: K_result = min(active_verifiers, 2 × K_result)

6. Create tests/test_slashing_payout.py:
   - test_slash_on_invalid_result
   - test_payout_distribution
   - test_related_party_blocking
   - test_k_escalation

Run: pytest tests/test_slashing_payout.py -v
```

**Checkpoint:** Invalid results trigger slashing and re-execution

---

## PHASE 9: DISTRIBUTED CONSENSUS

_(Commands 33-36 to be continued in full document)_

### Command 33: etcd-raft Integration

```
Implement Phase 9.1 - etcd-raft Setup:

1. Install etcd:
   docker run -d --name etcd \
     -p 2379:2379 -p 2380:2380 \
     quay.io/coreos/etcd:latest \
     /usr/local/bin/etcd \
     --listen-client-urls http://0.0.0.0:2379 \
     --advertise-client-urls http://localhost:2379

2. Add etcd client to requirements.txt:
   etcd3==0.12.0

3. Create src/consensus/raft_adapter.py with:
   - RaftConsensusAdapter class:
     - connect(etcd_hosts[])
     - get_bucket_for_need(need_id) # Hash to 256 buckets
     - try_decide(need_id, proposal_id, k_plan, epoch)
   - Use etcd transaction for atomicity

4. Create bucket topology:
   - 256 Raft groups (sharded by hash(need_id) % 256)
   - Each bucket independent
   - Leader election per bucket

5. Test migration from Redis:
   python tools/migrate_redis_to_etcd.py

Run: pytest tests/test_raft_consensus.py -v
```

**Checkpoint:** etcd-raft handles DECIDE with sharding

---

## Phase-by-Phase Summary

The complete commands continue for:
- **Phase 6**: Economic Foundation (Commands 21, 22, 23A, 23B, 24) - 5 commands
- **Phase 7**: Market Negotiation (Commands 25A, 25B, 26A, 26B, 27A, 27B, 28) - 7 commands
- **Phase 8**: Challenge Protocol (Commands 29, 30, 31A, 31B, 32) - 5 commands
- **Phase 9**: Distributed Consensus (Commands 33-36) - 4 commands (detailed)
- **Phase 10**: Distributed CRDT (Commands 37-40) - 4 commands (to detail)
- **Phase 11**: WASM Policy (Commands 41-44) - 4 commands (to detail)
- **Phase 12**: IPFS CAS (Commands 45-48) - 4 commands (to detail)
- **Phase 13**: P2P Transport (Commands 49-54) - 6 commands (to detail)
- **Phase 14**: Intelligent Routing (Commands 55-59) - 5 commands (to detail)
- **Phase 15**: Cross-Shard (Commands 60-63) - 4 commands (to detail)
- **Phase 16**: GC & Checkpointing (Commands 64-67) - 4 commands (to detail)
- **Phase 17**: Identity & Attestation (Commands 68-71) - 4 commands (to detail)
- **Phase 18**: Observability (Commands 72-75) - 4 commands (to detail)
- **Phase 19**: Open Economy (Commands 76-80) - 5 commands (to detail)
- **Phase 20**: Production Hardening (Commands 81-85) - 5 commands (to detail)

**Total Commands**: 90 implementation commands (+5 from original 85)  
**Detailed Commands (6-8)**: 18 commands (was 13)  
**Timeline**: 6-12 months  
**Team Size**: 2-5 engineers

**Note**: Commands were sized for optimal implementation - each takes 1-2 hours and produces a clear checkpoint.


---

## Testing Strategy

### Per-Phase Tests
Each phase includes:
1. **Unit Tests**: Individual component testing
2. **Integration Tests**: Cross-component interactions
3. **Property Tests**: Invariant verification
4. **Chaos Tests**: Fault injection and recovery

### Continuous Testing
```bash
# Run all tests
pytest tests/ -v --cov=src --cov-report=html

# Run property tests only
pytest tests/test_properties.py -v

# Run chaos tests
pytest tests/chaos/ -v --chaos-enabled

# Run E2E demo
.venv/bin/python demo/e2e_flow.py
```

### Performance Benchmarks
```bash
# Bus latency
python benchmarks/bus_latency.py  # Target: p99 < 25ms

# Policy evaluation
python benchmarks/policy_eval.py  # Target: p95 < 20ms

# DECIDE latency
python benchmarks/decide_latency.py  # Target: p95 < 2s

# Replay performance
python benchmarks/replay_speed.py  # Target: 10k events < 60s
```

---

## Migration Checkpoints

### Critical Verification Points

After each major migration, verify these invariants:

**Economic System:**
- [ ] All credits balance (total_supply = sum(all_accounts))
- [ ] No double-spending
- [ ] Escrows eventually resolve

**Consensus:**
- [ ] P1: Single DECIDE per NEED (no exceptions)
- [ ] P2: Deterministic replay (byte-for-byte match)
- [ ] P3: Lamport ordering (no reversals)
- [ ] P4: Policy enforcement (no unapproved verbs)

**Economic Integrity:**
- [ ] P5: Stake ≥ minimum at all times for active verifiers
- [ ] P6: Bounties ≤ caps by task class
- [ ] P7: Challenges within window only
- [ ] P8: No related-party payouts

---

## Emergency Procedures

### Rollback Commands

If a phase fails:

```bash
# Stop all services
docker-compose down
pkill -f "python.*agents/"

# Restore from backup
cp .state/backup/* .state/
cp .cas/backup/* .cas/

# Revert code
git checkout v1-stable
pip install -r requirements.txt

# Restart v1
docker-compose up -d
.venv/bin/python demo/e2e_flow.py
```

### Health Checks

```bash
# Check all services
./tools/health_check.sh

# Sample output:
# ✓ NATS: Connected (4222)
# ✓ Redis: PONG
# ✓ etcd: Healthy (2379)
# ✓ IPFS: Ready (5001)
# ✓ Ledger: 1000 accounts, 50000 total credits
# ✓ Pools: 25 active verifiers
```

---

## Next Steps

1. **Read** [COMPLETE_ROADMAP.md](COMPLETE_ROADMAP.md) for architectural details
2. **Start with Command 21** (Credit Ledger)
3. **Work sequentially** unless marked 🔀
4. **Test after each command**
5. **Document discoveries** and update architecture diagrams
6. **Join community** for questions and collaboration

---

**Status**: Commands 21-33 Detailed (Phases 6-9)  
**Detailed**: 18 commands fully specified  
**Remaining**: Commands 34-90 (Phases 9-20) to be detailed  
**Next**: Continue building the decentralized agent economy! 🚀🐝

**Note**: This is a living document. As phases complete, we'll add:
- Production deployment guides
- Performance tuning recommendations
- Troubleshooting runbooks
- Community contributions

---

## Command Sizing Update (2025-11-24)

The commands were optimized for better implementation success:
- **Original**: 85 total commands
- **Optimized**: 90 total commands (+5 splits)
- **Why**: 5 commands were too large (4-5 files each), risking errors and overwhelming complexity
- **Result**: Each command now takes 1-2 hours, with 2-3 new files and clear checkpoints

