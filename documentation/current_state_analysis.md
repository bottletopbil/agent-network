# CAN Swarm: Current State vs. Planned Architecture

## Executive Summary

**Where You Are:** You've built foundational infrastructure (30% of v1 PoC) but jumped ahead on some pieces while missing critical components.

**Good News:** Your code quality is solid and aligns with the protocol vision.

**Gap:** Missing the **core orchestration layer** (CRDT plan, Raft consensus, verb routing, agent lifecycle).

---

## Architecture Comparison

### What the Full Plan Requires (v1 PoC - from V1.md §12)

Your plan defines a **centralized-but-replayable** implementation with:

1. **Envelope/Signature SDK** ✅ (DONE)
2. **Policy Capsule Runner** ⚠️ (Partially done - missing OPA/WASM)
3. **CRDT Plan Op-log** ❌ (Not started - Automerge integration missing)
4. **Scoped Consensus Adapter** ❌ (Not started - Raft missing)
5. **Bus + Audit** ✅ (DONE)
6. **Chaos Hooks** ❌ (Not started)
7. **Property Tests** ❌ (Not started)

**PoC Goal:** `NEED → DECIDE → FINALIZE` with deterministic replay.

---

## Detailed Gap Analysis

### ✅ What You've Built (Strong Foundation)

| Component | Status | Notes |
|-----------|--------|-------|
| **Envelopes** | ✅ Complete | `envelope.py` has: id, thread_id, kind, lamport, sender_pk, payload_hash, sig |
| **Ed25519 Crypto** | ✅ Complete | Signing, verification, canonical JSON |
| **Lamport Clock** | ✅ Complete | Persistent, thread-safe, tick/observe |
| **CAS (File-based)** | ✅ Complete | SHA256 addressing, atomic writes, sharding |
| **NATS Integration** | ✅ Complete | JetStream, envelope pub/sub, audit logging |
| **Audit Log** | ✅ Complete | Signed JSONL per thread |
| **Policy Validation** | ⚠️ Partial | Python validation exists but **NOT using OPA→WASM** as planned |

### ⚠️ Critical Misalignments

#### 1. Policy Engine Implementation
**Plan Says:** OPA (Rego) compiled to WASM with gas metering  
**You Have:** Python validation in `policy.py` (hardcoded rules)  
**Gap:** No WASM isolation, no gas metering, not deterministic across languages  
**Impact:** Cannot satisfy deterministic replay requirement from V1.md §5

#### 2. Message Verbs
**Plan Says:** Rich verb set (NEED, PROPOSE, CLAIM, COMMIT, ATTEST, DECIDE, FINALIZE, etc.)  
**You Have:** Basic envelope "kind" field with: NEED, PLAN, COMMIT, ATTEST, FINAL  
**Gap:** Missing DECIDE, PROPOSE, CLAIM, YIELD/RELEASE, UPDATE_PLAN, RECONCILE, CHALLENGE, INVALIDATE, CHECKPOINT  
**Impact:** Cannot implement the negotiation protocol

#### 3. Envelope Schema
**Plan Says:** `capability, verb, content_refs[], policy_capsule_hash, policy_eval_digest`  
**You Have:** `kind, payload, policy_engine_hash` (simpler)  
**Gap:** Missing capability tokens, content_refs pattern, eval digest for attestations  
**Impact:** Cannot implement capability-based routing or policy divergence detection

### ❌ Missing Core Components

#### 1. **CRDT Plan Store (Critical)**
**Required:** Automerge-based op-log for shared plan state  
**Status:** Not started  
**Tasks:**
- Integrate Automerge (likely via Python bindings or subprocess to Node.js)
- Implement op types: ADD_TASK, REQUIRES, PRODUCES, STATE, LINK, ANNOTATE
- Build merge handlers for partition recovery
- Sync plan state via NATS messages

#### 2. **Scoped Consensus (DECIDE) (Critical)**
**Required:** etcd-raft for at-most-one DECIDE per NEED  
**Status:** Not started  
**Tasks:**
- Integrate etcd-raft (via Python bindings or sidecar process)
- Implement NEED-hash bucket sharding (256 buckets)
- Add epochs and fencing tokens
- Wire DECIDE output to audit log and CRDT

#### 3. **Agent Orchestration Layer (Critical)**
**Required:** Router + agent lifecycle management  
**Status:** Not started  
**Tasks:**
- Build negotiation protocol (bid windows, leases, heartbeats)
- Implement routing: filter → shortlist → selection
- Add lease expiry and scavenging
- Build verifier pool selection (even if K=1 for bootstrap)

#### 4. **Verb Handlers**
**Required:** Process NEED, PROPOSE, CLAIM, COMMIT, ATTEST, etc.  
**Status:** Not started  
**Tasks:**
- Create verb registry and dispatcher
- Implement state machine per NEED (DRAFT → VERIFIED → FINAL)
- Add telemetry extraction from COMMIT
- Build ATTEST aggregation and quorum logic

#### 5. **MinIO/S3 Integration**
**Required:** Replace file-based CAS with MinIO  
**Status:** File-based CAS exists, but not MinIO  
**Tasks:**
- Add MinIO to docker-compose.yml
- Integrate boto3/minio-py
- Preserve content-addressing API
- (Optional for PoC: keep file-based, migrate later)

#### 6. **Deterministic Replay Tool**
**Required:** JSONL replay → byte-for-byte FINALIZE reproduction  
**Status:** Basic signature verification exists, not full replay  
**Tasks:**
- Build replay engine that re-executes policy checks
- Verify lamport ordering
- Reproduce DECIDE from ATTEST quorum
- Assert final state matches

---

## What's Working vs. What the README Claims

Your `README.md` claims:

> **Phase 1 (Done):** NATS + Signed Audit Logs

**Reality:** Phase 1 IS done correctly.

> The next major step is to wrap these communications in Envelopes

**Reality:** You already did this (jumped to Phase 2).

> and begin building the rule-based decision layer (policy engine)

**Reality:** You built a simple policy validator, but **not** the planned OPA→WASM version.

**Conclusion:** Your README is 2 phases behind your actual code, but your code is still missing the **orchestration core** needed for the PoC.

---

## The Minimal Path Forward (v1 PoC)

Based on V1.md §12, here's the **critical path** to a working demo:

### Phase A: Fix Current Code (1-2 days)
1. Fix policy hash default in `envelope.py`
2. Add missing verbs to policy allowlist
3. Create `requirements.txt`
4. Add backward-compat `publish()`/`subscribe()` in `bus.py`
5. Fix all example scripts

### Phase B: Core Orchestration (1 week)
1. **Plan CRDT** (3 days)
   - Integrate Automerge (Python bindings or REST bridge)
   - Implement typed ops (ADD_TASK, STATE, etc.)
   - Wire to NATS for sync
2. **Scoped Consensus** (2 days)
   - Integrate etcd-raft (Python or sidecar)
   - Implement single NEED→DECIDE flow
   - Add epoch/fencing
3. **Verb Routing** (2 days)
   - Build dispatcher for NEED, PROPOSE, ATTEST, DECIDE, FINALIZE
   - Implement state machine
   - Add quorum logic (K=1 for bootstrap)

### Phase C: Agents & Demo (3-4 days)
1. **Simple Planner Agent**
   - Listens for NEED
   - Publishes PROPOSE
   - Waits for DECIDE
2. **Simple Worker Agent**
   - Claims task
   - Executes (mock work)
   - Publishes COMMIT with CAS artifact
3. **Verifier Pool** (K=1)
   - Listens for COMMIT
   - Validates artifact exists in CAS
   - Publishes ATTEST
   - Aggregator triggers FINALIZE
4. **End-to-End Test**
   - NEED("classify 10 items") → DECIDE → worker executes → COMMIT → ATTEST → FINALIZE
   - Replay log → verify same outcome

### Phase D: Deterministic Replay (2-3 days)
1. Build replay simulator
2. Property tests (P1-P4 from V1.md §6)
3. Basic chaos injection (message delay, duplication)

**Total Estimate:** 2-3 weeks for working PoC

---

## Technology Decisions Needed

### 1. Automerge Integration Strategy
**Options:**
- **A)** Use `automerge-py` (if exists/maintained)
- **B)** Run Automerge.js via Node sidecar with gRPC/HTTP bridge
- **C)** Skip Automerge for PoC, use simple op-log in SQLite with manual merge

**Recommendation:** Option C for speed (Automerge adds complexity). Migrate later.

### 2. Raft Integration Strategy
**Options:**
- **A)** Use `python-raft` library (if solid)
- **B)** Run etcd as sidecar, use HTTP API
- **C)** Skip Raft for PoC, use Redis + Lua for at-most-once DECIDE

**Recommendation:** Option C for PoC simplicity. Raft is overkill for K=1 bootstrap.

### 3. OPA→WASM Integration
**Options:**
- **A)** Full OPA integration with WASM compilation
- **B)** Keep Python policy validator, add gas metering manually
- **C)** Defer to v2

**Recommendation:** Option B for PoC. Add simple instruction counter.

---

## Recommended Next Steps

### Immediate (This Week)
1. **Fix existing code flaws** (from my earlier review)
2. **Choose integration strategies** for CRDT and Raft
3. **Design simplified verb protocol** for PoC (fewer verbs)
4. **Sketch agent architecture** (planner, worker, verifier)

### Next Week
1. Implement simplified plan store (op-log)
2. Implement DECIDE mechanism (even if just Redis)
3. Build first agent (planner or worker)

### Week 3
1. Complete 3-agent demo loop
2. Add replay verification
3. Document and demo

---

## Critical Questions for You

1. **Do you want to build the full Automerge+Raft stack now, or simplify for PoC?**
   - Full stack = 4-6 weeks
   - Simplified = 2-3 weeks, with clear migration path

2. **What's your timeline/deadline?**
   - Research deadline?
   - Personal learning project?

3. **Do you have multiple machines for testing distributed scenarios?**
   - Or should we design for single-machine multi-process?

4. **What's your Python vs. other languages preference?**
   - Pure Python? Or okay with Node.js/Go sidecars?

5. **What's the "one demo" you want to show first?**
   - Text classification (from README)?
   - Something simpler?
