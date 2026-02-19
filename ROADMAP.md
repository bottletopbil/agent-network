# CAN Swarm Development Roadmap

**Version**: 2.1 (Post-Audit)  
**Last Updated**: 2026-02-18  
**Status**: Active Remediation

---

## Overview

This roadmap reflects the **honest state** of the CAN Swarm project after comprehensive security and architectural auditing. Phases 1-5 represent completed scaffolding with known gaps. Phases 6-8 address those gaps systematically.

### Reality Check (2026-02-18)

- Core/API drift issues previously blocking targeted execution are fixed in the current baseline.
- All five required quality gates are currently green on the verified baseline snapshot.
- Full-suite confidence is still incomplete due remaining skipped modules and unresolved backlog slices.
- Treat this roadmap as a hardening plan for an in-progress PoC, not a completed v1 delivery.

> [!IMPORTANT]
> **Production Readiness Score**: 4.5/10  
> This is a functional PoC, not a production system. The roadmap prioritizes critical fixes before feature expansion.

---

## Progress Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Complete and audited |
| ⚠️ | Scaffolding only — pending hardening |
| 🔴 | Critical vulnerability — immediate fix required |
| 🟡 | Known gap — fix scheduled |
| ⬜ | Not started |

---

## Phase 1-5: Core Protocol (Retrospective)

### Phase 1: Foundation ✅
- ✅ NATS JetStream integration
- ✅ Ed25519 key generation and signing
- ✅ Basic pub/sub messaging

### Phase 2: Coordination Layer ⚠️
- ✅ Envelope schema with Lamport clocks
- ✅ Message bus abstraction
- ⚠️ Policy engine (Python fallback, no real WASM)
- ⚠️ Plan Store (homegrown CRDT, not Automerge library)
- 🔴 **Consensus adapter — PENDING HARDENING**

### Phase 3: Agent Implementation ✅
- ✅ Base agent framework
- ✅ Planner, Worker, Verifier agents
- ✅ Coordinator orchestration

### Phase 4: Integration ⚠️
- ✅ E2E demo workflow
- ✅ Deterministic replay tool
- ⚠️ Property tests (pass on happy path only)

### Phase 5: Documentation ✅
- ✅ README, API docs, architecture diagrams

### Definition of Done (Phases 1-5)
- [x] E2E demo completes successfully
- [x] All property tests P1-P4 pass (single-node)
- [ ] ~~Multi-node consensus validated~~ (NOT DONE)
- [ ] ~~CRDT merge determinism proven~~ (NOT DONE)

---

## Phase 6: Security & Integrity Fixes (Immediate)

**Timeline**: 5-7 days  
**Priority**: 🔴 CRITICAL

> [!CAUTION]
> These fixes must be completed before ANY multi-node deployment.

### 6.1 Epoch Fencing Enforcement 🔴

**File**: `src/handlers/decide.py`  
**Vulnerability**: Zombie agents from old epochs can submit accepted DECIDEs

**Implementation**:
```python
# decide.py - Add at start of handle_decide()
from consensus.epochs import epoch_manager

current_epoch = epoch_manager.get_current_epoch()
if payload.get("epoch", 0) < current_epoch:
    logger.warning(f"FENCED: stale epoch {payload['epoch']} < {current_epoch}")
    return  # Reject
```

**Additional Work**:
- [ ] Migrate epoch persistence from local SQLite to etcd/distributed coordination
- [ ] Wire epoch increment to partition detection
- [x] Add epoch validation to `raft_adapter.try_decide()`

---

### 6.2 CLAIM_EXTENDED Consensus Bypass 🔴

**File**: `src/handlers/claim_extended.py`  
**Vulnerability**: Direct `STATE → DECIDED` write bypasses consensus

**Implementation**:
- [x] Remove direct state update in `handle_claim_extended()`
- [x] Route all DECIDED transitions through `handle_decide()`
- [x] Add lock check: reject if task already claimed by another agent

---

### 6.3 Free-Rider Exploit Closure 🔴

**File**: `src/economics/slashing.py`  
**Vulnerability**: `honest_verifiers` can be Sybil-inflated without attestation proof

**Current State**:
- Attestation verification logic exists when `attestation_log` is provided
- Backward-compatible path still allows rewarding claimed honest verifiers without proof when log is omitted

**Remaining Work**:
- [ ] Make `attestation_log` mandatory (remove compatibility bypass)
- [ ] Reject unverified `honest_verifiers` claims by default
- [ ] Add coverage that fails on missing proof input

---

### 6.4 Deterministic Merge Fix 🟡

**File**: `src/plan/automerge_store.py`  
**Issue**: Merge sort lacks tie-breaker for equal Lamport values

**Implementation**:
```python
# automerge_store.py - Total ordering
self.doc.ops.sort(key=lambda op: (
    op["lamport"],
    op["actor_id"],
    op["op_id"]
))
```

**Additional Work**:
- [ ] Replace `time.time_ns()` in `annotate_task()` with proper Lamport

---

### 6.5 Bucket Sharding Activation 🟡

**File**: `src/consensus/raft_adapter.py`  
**Issue**: Sharding function exists but is never called

**Implementation**:
```python
# raft_adapter.py:try_decide() - Use bucket in key
bucket = self.get_bucket_for_need(need_id)
key = f"/decide/bucket-{bucket}/{need_id}"
```

**Status**:
- [x] Bucketed DECIDE key path activated in `try_decide()` and `get_decide()`
- [x] Raft tests cover bucketed key behavior and idempotent retry with sharded keys

---

### 6.6 SEC-002 Ingress Policy Bypass Closure 🔴

**Files**: `src/policy/enforcement.py`, `src/policy/gates.py`, `src/coordinator.py`, `src/bus.py`, `src/hybrid_bus.py`  
**Vulnerability**: External ingress paths can route envelopes without mandatory policy enforcement

**Current Status**:
- [x] Shared fail-closed ingress validation helper added
- [x] Coordinator dispatch ingress validation wired
- [x] P2P and hybrid ingress validation wired
- [x] Policy input normalization supports both canonical envelope fields and legacy gate fields
- [ ] Required gate evidence not yet attached for completion transition

---

### Definition of Done (Phase 6)
- [ ] Property P1 (Single DECIDE) passes under simulated partition
- [ ] Property P2 (Deterministic replay) passes with concurrent ops
- [ ] Free-rider exploit test fails (attack blocked)
- [ ] All 5 critical gaps from audit closed

---

## Phase 7: Economic Enforcement (Near-term)

**Timeline**: 2-3 weeks  
**Priority**: 🟡 HIGH

### 7.1 Real Gas Metering

**Current State**: Symbolic operation counting  
**Target**: WASM instruction metering or timeout-based limits

**Options**:
1. Integrate `wasmtime-py` for real WASM gas
2. Implement `sys.settrace()` bytecode counting
3. Replace gas with wall-clock timeout (simpler)

**Implementation Steps**:
- [ ] Choose metering strategy
- [ ] Implement resource limiter in `wasm_runtime.py`
- [ ] Add gas cost to policy evaluation results
- [ ] Enforce gas limits (reject over-limit operations)

---

### 7.2 Bond Locking Integration

**Current State**: `BondCalculator` only calculates; doesn't lock funds  
**Target**: Atomic bond escrow on challenge submission

**Implementation**:
- [ ] Create `ChallengeSubmitter` that combines bond calculation + escrow
- [ ] Update challenge handlers to use atomic submission
- [ ] Add bond refund on successful challenge

---

### 7.3 Lease Persistence

**Current State**: In-memory `_lease_registry` in `claim_extended.py`  
**Target**: Persist leases to etcd or SQLite

**Implementation**:
- [ ] Move lease registry to persistent store
- [ ] Add lease expiration daemon
- [ ] Implement lease renewal protocol

---

### 7.4 Epoch State Persistence

**Current State**: Persisted locally in SQLite (`.state/epochs.db`)  
**Target**: Store epoch in etcd with distributed coordination

**Implementation**:
- [ ] Add distributed epoch key to etcd
- [ ] Implement epoch increment on partition detection
- [ ] Add epoch sync on node startup

---

### Definition of Done (Phase 7)
- [ ] Gas metering enforces real resource limits
- [ ] Challenge bonds are atomically locked
- [ ] Node restart preserves epoch/lease state
- [ ] Property tests pass after simulated restart

---

## Phase 8: Profile B Migration (Long-term)

**Timeline**: 4-6 weeks  
**Priority**: 🟢 PLANNED

### 8.1 libp2p Transport

**Current**: NATS JetStream  
**Target**: libp2p with gossipsub

**Implementation**:
- [ ] Create `P2PBus` implementation using py-libp2p
- [ ] Implement peer discovery (mDNS + DHT)
- [ ] Add message signing at transport layer

---

### 8.2 IPFS CAS Backend

**Current**: FileCAS (SHA256) + IPFS backend (ready but not default)  
**Target**: IPFS as primary CAS

**Implementation**:
- [ ] Enable IPFS by default via feature flag
- [ ] Write migration script for FileCAS → IPFS re-hashing
- [ ] Add IPLD link verification

---

### 8.3 Real Automerge Integration

**Current**: Homegrown Python CRDT  
**Target**: automerge-py library

**Implementation**:
- [ ] Evaluate automerge-py stability
- [ ] Create adapter maintaining current API
- [ ] Migrate state with version upgrade

---

### 8.4 Multi-Node Testing

**Target**: Validated multi-node deployment

**Implementation**:
- [ ] Create Docker Compose for 3-node cluster
- [ ] Implement chaos testing (network partitions)
- [ ] Validate consensus under failure scenarios

---

### Definition of Done (Phase 8)
- [ ] System operates without NATS dependency
- [ ] IPFS CAS provides distributed storage
- [ ] 3-node cluster handles partition without data loss
- [ ] All property tests pass in distributed mode

---

## Quality Gates Summary

| Phase | Key Tests | Pass Criteria |
|-------|-----------|---------------|
| 6 | P1 Single DECIDE | No duplicate DECIDEs under partition |
| 6 | P2 Deterministic Replay | Same state on different merge orders |
| 7 | Gas Enforcement | Runaway policy rejected |
| 7 | Lease Persistence | State survives restart |
| 8 | Partition Tolerance | Consensus maintained across split |
| 8 | Distributed Merge | All nodes converge to same state |

---

## Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Zombie agent attack | High (currently exploitable) | Critical | Phase 6.1 |
| State divergence | Medium | High | Phase 6.4 |
| Economic exploit | High (currently exploitable) | High | Phase 6.3 |
| DoS via gas | Medium | Medium | Phase 7.1 |
| Data loss on restart | High | Critical | Phase 7.3, 7.4 |

---

## Timeline Summary

```
NOW ────────────────────────────────────────────────────────> PRODUCTION

Phase 6 (5-7 days)          Phase 7 (2-3 weeks)       Phase 8 (4-6 weeks)
├── Epoch fencing           ├── Real gas metering     ├── libp2p transport
├── CLAIM_EXTENDED fix      ├── Bond locking          ├── IPFS default
├── Free-rider closure      ├── Lease persistence     ├── Automerge-py
├── Merge determinism       ├── Epoch persistence     ├── Multi-node testing
└── Bucket sharding         └── Restart recovery      └── Production hardening
```

---

*This roadmap is a living document. Update after each phase completion.*
