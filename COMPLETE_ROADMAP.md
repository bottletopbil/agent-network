# CAN Swarm Complete Implementation Roadmap
**From v1 PoC → Full Decentralized Agent Economy**

This roadmap details the path from the current v1 PoC (centralized, single-node, basic workflow) to the complete CAN Swarm vision: a decentralized, economically-driven, orchestrator-free multi-agent protocol with market-style negotiation, verifier pools, and open agent economy.

---

## 🎯 Executive Summary

### Current State (v1 PoC - Complete ✓)
- ✅ Basic NEED → FINALIZE workflow
- ✅ Ed25519 signatures and audit logging
- ✅ Lamport clocks for ordering
- ✅ Policy validation (Python)
- ✅ Plan store (SQLite CRDT)
- ✅ Consensus (Redis at-most-once DECIDE)
- ✅ Content-addressable storage (file-based)
- ✅ Single coordinator, 3 agents (Planner, Worker, Verifier)
- ✅ Deterministic replay
- ✅ Property tests (P1-P4)

### Target State (Complete CAN Swarm)
- 🎯 Decentralized P2P network (libp2p)
- 🎯 Market-style negotiation (Contract-Net protocol)
- 🎯 Economic layer with credits, stake, bounties
- 🎯 Verifier pools with diversity constraints
- 🎯 Challenge protocol with slashing
- 🎯 Distributed CRDT plan store (Automerge/OrbitDB)
- 🎯 Strong consensus via etcd-raft
- 🎯 IPFS/IPLD for artifact storage
- 🎯 WASM policy engine with gas metering
- 🎯 Router with bandit learning
- 🎯 Cross-shard coordination
- 🎯 Epoch checkpointing and GC
- 🎯 Open agent economy with manifests

---

## 📊 Gap Analysis

| Component | v1 PoC | Complete Swarm | Migration Complexity |
|-----------|--------|----------------|---------------------|
| **Transport** | NATS JetStream<br/>(centralized) | libp2p pubsub<br/>(P2P) | High - network rewrite |
| **Negotiation** | Direct assignment | Market bidding<br/>(PROPOSE/CLAIM/YIELD) | Medium - protocol extension |
| **Verifiers** | Single verifier | Pools with stake<br/>+diversity+quorum | High - economics + selection |
| **Consensus** | Redis (single DECIDE) | etcd-raft sharded<br/>(K_plan quorum) | Medium - distributed consensus |
| **Plan Store** | SQLite local | Automerge/OrbitDB<br/>(distributed CRDT) | Medium - CRDT sync |
| **CAS** | File system | IPFS/IPLD<br/>(content DAG) | Low - interface abstraction |
| **Policy** | Python validator | OPA→WASM<br/>(sandboxed+metered) | Medium - compilation pipeline |
| **Economics** | None | Credits, stake, bounties,<br/>slashing, payout | High - new subsystem |
| **Challenges** | None | Challenge protocol<br/>(bonds, proofs, escalation) | High - adversarial system |
| **Routing** | Fixed agents | Filter→Shortlist→Canary<br/>→Bandit | Medium - ML routing |
| **Identity** | Single keypair | DID:key/peer,<br/>attested runtimes | Medium - identity infrastructure |
| **GC/Sync** | None | Checkpoints, Merkle roots,<br/>fast sync | Medium - compaction |
| **Cross-Shard** | Single thread | Commit-by-reference,<br/>escrow artifacts | High - distributed coordination |

**Total Estimated Effort**: 6-12 months for complete implementation

---

## 🗺️ Implementation Phases

### Phase 6: Economic Foundation (4-6 weeks)

**Goal**: Implement credit ledger, stake system, and basic verifier pools

#### 6.1 Credit Ledger
- [ ] Create `src/economics/ledger.py`: account balances, transfers, escrow
- [ ] Add credit operations: MINT, TRANSFER, ESCROW, RELEASE
- [ ] Implement unbonding periods
- [ ] Add audit trail for economic events

#### 6.2 Stake System
- [ ] Verifier staking requirements
- [ ] Stake locking and unbonding
- [ ] Slashing conditions and execution
- [ ] Delegation limits

#### 6.3 Verifier Pools
- [ ] Pool registration and discovery
- [ ] Selection weighting: w = sqrt(stake) × reputation × recency
- [ ] Diversity constraints (org/ASN/region caps)
- [ ] Pool health monitoring

#### 6.4 Bounty System
- [ ] verify_bounty in COMMIT envelopes
- [ ] Escrow for 2×T_challenge duration
- [ ] Payout distribution to committee
- [ ] Bounty caps by task class

**Checkpoint**: Verifiers can stake credits, join pools, and earn bounties

---

### Phase 7: Market-Style Negotiation (4-6 weeks)

**Goal**: Implement Contract-Net protocol with bidding and leases

#### 7.1 Extended Verb Handlers
- [ ] PROPOSE handler with ballot and patch
- [ ] CLAIM handler with lease TTL, cost, ETA
- [ ] YIELD handler for task release
- [ ] RELEASE handler for lease expiration
- [ ] UPDATE_PLAN handler for plan patches

#### 7.2 Lease Management
- [ ] Lease TTL tracking
- [ ] Heartbeat protocol
- [ ] Lease renewal mechanism
- [ ] Scavenge on missed heartbeats

#### 7.3 Auction Protocol
- [ ] Bid windows for NEEDs
- [ ] Multi-round bidding
- [ ] Randomized backoff to prevent herds
- [ ] Bid evaluation and selection

#### 7.4 Plan Patching
- [ ] Proposal patch validation
- [ ] Conflict detection
- [ ] Merge rules for competing patches
- [ ] Plan versioning

**Checkpoint**: Tasks are auctioned, agents bid, leases enforce exclusivity

---

### Phase 8: Challenge Protocol (3-4 weeks)

**Goal**: Implement adversarial verification with bonds and slashing

#### 8.1 Challenge Mechanics
- [ ] CHALLENGE verb with proof schema
- [ ] Typed proof classes (schema_violation, missing_citation, etc.)
- [ ] Challenge window T_challenge tracking
- [ ] Proof size and gas bounds

#### 8.2 Challenge Bonds
- [ ] Challenger bond calculation
- [ ] Bond escrow and release
- [ ] Slashing for malformed proofs
- [ ] Bond proportional to complexity

#### 8.3 Challenge Verification
- [ ] Proof verification engine
- [ ] Automated challenge evaluations
- [ ] Manual escalation paths
- [ ] Verdict recording (INVALIDATE verb)

#### 8.4 Slashing and Payouts
- [ ] Verifier slashing on failed challenge
- [ ] Bounty reallocation (challenger + honest + burn)
- [ ] K_result escalation on invalidation
- [ ] Related-party checks for payouts

**Checkpoint**: Invalid results can be challenged, slashed, and invalidated

---

### Phase 9: Distributed Consensus (4-5 weeks)

**Goal**: Migrate from Redis to etcd-raft with sharding and epochs

#### 9.1 etcd-raft Integration
- [ ] Install and configure etcd cluster
- [ ] Create `src/consensus_raft.py` adapter
- [ ] Raft group topology (256 buckets by NEED-hash)
- [ ] Leader election and failover

#### 9.2 Scoped Consensus
- [ ] K_plan quorum tracking
- [ ] ATTEST_PLAN verb for proposals
- [ ] DECIDE emission on quorum
- [ ] Epoch/fencing token enforcement

#### 9.3 Partition Handling
- [ ] Epoch-based fencing
- [ ] Highest-epoch DECIDE wins
- [ ] Merge handlers for conflicts
- [ ] RECONCILE verb for partition heal

#### 9.4 Quorum Configuration
- [ ] K_plan = min(K_target, floor(active_verifiers × alpha))
- [ ] Progressive quorums during bootstrap
- [ ] Quorum health monitoring
- [ ] Dynamic K adjustment

**Checkpoint**: Multiple verifiers vote on proposals, quorum triggers DECIDE

---

### Phase 10: Distributed CRDT Plan Store (3-4 weeks)

**Goal**: Migrate from SQLite to Automerge with P2P sync

#### 10.1 Automerge Integration
- [ ] Install automerge-py
- [ ] Reimplement plan store with Automerge doc
- [ ] Op-log types: ADD_TASK, REQUIRES, PRODUCES, STATE, LINK, ANNOTATE
- [ ] LWW registers for annotations
- [ ] G-Sets for nodes/edges

#### 10.2 Sync Protocol
- [ ] Peer discovery for plan sync
- [ ] Incremental sync via Automerge
- [ ] Conflict-free merges
- [ ] Sync state monitoring

#### 10.3 Derived Views
- [ ] Materialized task graph
- [ ] State queries (get_task, get_thread)
- [ ] Dependency resolution
- [ ] Incremental view updates

#### 10.4 Migration from SQLite
- [ ] Data export from SQLite
- [ ] Import to Automerge doc
- [ ] Verification of equivalence
- [ ] Rollback procedures

**Checkpoint**: Plan state syncs across nodes, automatic conflict resolution

---

### Phase 11: WASM Policy Engine (3-4 weeks)

**Goal**: Migrate from Python to OPA/WASM with gas metering

#### 11.1 OPA Integration
- [ ] Install Open Policy Agent
- [ ] Convert Python policies to Rego
- [ ] Policy compilation to WASM
- [ ] Policy versioning and hashing

#### 11.2 WASM Runtime
- [ ] WASM executor with gas metering
- [ ] Resource limits (memory, CPU)
- [ ] Sandbox isolation
- [ ] policy_engine_hash verification

#### 11.3 Three-Gate Enforcement
- [ ] Preflight validation (client-side)
- [ ] Ingress validation (every agent)
- [ ] Commit-gate validation (verifiers check telemetry)
- [ ] policy_eval_digest in ATTESTs

#### 11.4 Policy Capsules
- [ ] Capsule schema (engine_hash, version, conformance)
- [ ] Capsule distribution
- [ ] Conformance testing
- [ ] Policy divergence detection

**Checkpoint**: Policies run in WASM sandbox, deterministic across all nodes

---

### Phase 12: IPFS CAS (2-3 weeks)

**Goal**: Migrate from file-based CAS to IPFS/IPLD

#### 12.1 IPFS Node Setup
- [ ] Deploy IPFS daemon
- [ ] Configure pinning strategies
- [ ] Set up IPFS cluster (optional)
- [ ] Gateway configuration

#### 12.2 CAS Interface Migration
- [ ] Implement `src/cas_ipfs.py`
- [ ] PUT → ipfs.add
- [ ] GET → ipfs.cat
- [ ] CID-based addressing

#### 12.3 Data Migration
- [ ] Export artifacts from file CAS
- [ ] Import to IPFS with pinning
- [ ] Verify CID mappings
- [ ] Update references in plan store

#### 12.4 IPLD Integration
- [ ] DAG structures for complex artifacts
- [ ] IPLD schemas for envelopes
- [ ] Content linking
- [ ] Merkle proofs

**Checkpoint**: Artifacts stored in IPFS, content-addressed by CID

---

### Phase 13: P2P Transport Layer (5-6 weeks)

**Goal**: Migrate from NATS to libp2p with gossipsub

#### 13.1 libp2p Bootstrap
- [ ] Install py-libp2p
- [ ] Node identity (peer IDs)
- [ ] Multi-address support
- [ ] NAT traversal (STUN/TURN)

#### 13.2 Gossipsub Pubsub
- [ ] Topic-based messaging
- [ ] Message propagation
- [ ] Peer scoring
- [ ] Message deduplication

#### 13.3 Protocol Migration
- [ ] Envelope format unchanged
- [ ] Bus adapter for libp2p
- [ ] Topic mapping (thread.*.verb → /swarm/thread/)
- [ ] Consumer group emulation

#### 13.4 Peer Discovery
- [ ] mDNS for local discovery
- [ ] DHT for global discovery
- [ ] Bootstrap nodes
- [ ] Peer exchange protocol

#### 13.5 Connection Management
- [ ] Connection pooling
- [ ] Peer reputation
- [ ] Blacklisting
- [ ] Circuit relay for NAT

**Checkpoint**: Agents communicate via P2P, no central message broker

---

### Phase 14: Intelligent Routing (4-5 weeks)

**Goal**: Implement Filter→Shortlist→Canary→Bandit routing

#### 14.1 Capability-Based Filtering
- [ ] Capability manifests (I/O schema, tags, constraints)
- [ ] Zone/budget constraints
- [ ] Policy-based filtering
- [ ] Capability matching algorithm

#### 14.2 Scoring and Shortlisting
- [ ] Scoring function: f(reputation, price, P95 latency, domain fit, stake)
- [ ] Recency weighting
- [ ] Diversity bonuses
- [ ] Top-K selection

#### 14.3 Canary Testing
- [ ] Micro-task generation
- [ ] Parallel execution on top 2 candidates
- [ ] Verifier scoring
- [ ] Winner selection

#### 14.4 Contextual Bandit Learning
- [ ] Domain-specific feature extraction
- [ ] Thompson sampling or UCB
- [ ] Exploration budget (ε-greedy)
- [ ] Model updates per feedback

#### 14.5 Router Service
- [ ] Routing daemon
- [ ] Request handling
- [ ] Model persistence
- [ ] Performance monitoring

**Checkpoint**: NEEDs are intelligently routed to best-fit agents

---

### Phase 15: Cross-Shard Coordination (3-4 weeks)

**Goal**: Implement multi-shard workflows without 2PC

#### 15.1 Shard Topology
- [ ] Shard partitioning strategy (by domain, by load)
- [ ] Shard registry and discovery
- [ ] Cross-shard routing
- [ ] Shard health monitoring

#### 15.2 Commit-by-Reference
- [ ] Commitment artifacts
- [ ] shard_dependencies field in PROPOSE
- [ ] Artifact-based dependencies
- [ ] Timeout handling

#### 15.3 Escrow Protocol
- [ ] Prepared DECIDE with TTL
- [ ] Escrow artifact publication
- [ ] Cross-shard finalization
- [ ] Rollback on timeout

#### 15.4 Dependency Resolution
- [ ] Dependency graph validation
- [ ] Circular dependency detection
- [ ] Topological ordering
- [ ] Cascading failures

**Checkpoint**: Workflows span multiple shards, no blocking 2PC

---

### Phase 16: Garbage Collection & Checkpointing (2-3 weeks)

**Goal**: Implement epoch checkpoints and compaction

#### 16.1 Epoch Checkpointing
- [ ] CHECKPOINT verb
- [ ] Merkle root calculation
- [ ] Verifier quorum for checkpoints
- [ ] Checkpoint storage and distribution

#### 16.2 Pruning
- [ ] Pre-checkpoint op pruning
- [ ] Hot/cold tier separation
- [ ] Archive storage
- [ ] Retention policies

#### 16.3 Fast Sync
- [ ] Checkpoint-based bootstrap
- [ ] Incremental sync from checkpoint
- [ ] State reconstruction
- [ ] Verification of checkpoint validity

#### 16.4 Deterministic Compression
- [ ] Final state summaries
- [ ] Merkle proof retention
- [ ] Compressed op-log format
- [ ] Decompression for replay

**Checkpoint**: Old data is pruned, new nodes sync from checkpoints

---

### Phase 17: Identity & Attestation (3-4 weeks)

**Goal**: Implement DID-based identity and attested runtimes

#### 17.1 DID Integration
- [ ] DID:key support
- [ ] DID:peer for ephemeral agents
- [ ] DID resolution
- [ ] Verifiable credentials

#### 17.2 Agent Manifests
- [ ] Manifest schema (capabilities, I/O, price, constraints)
- [ ] Manifest signing
- [ ] Manifest distribution
- [ ] Manifest verification

#### 17.3 Attested Runtimes
- [ ] TEE integration (SGX/SEV optional)
- [ ] Runtime attestation reports
- [ ] Attestation verification
- [ ] Trust anchors

#### 17.4 Reputation System
- [ ] Reputation scoring
- [ ] Historical performance tracking
- [ ] Slashing impact on reputation
- [ ] Reputation decay over time

**Checkpoint**: Agents have portable identities, manifests publish capabilities

---

### Phase 18: Observability & Chaos Engineering (2-3 weeks)

**Goal**: Advanced observability and fault injection

#### 18.1 Enhanced Tracing
- [ ] OpenTelemetry integration
- [ ] Distributed tracing across shards
- [ ] Trace aggregation
- [ ] Trace visualization

#### 18.2 Deterministic Simulator
- [ ] Replay engine from JSONL
- [ ] Policy WASM re-execution
- [ ] State verification
- [ ] Divergence detection

#### 18.3 Chaos Testing
- [ ] Partition injection
- [ ] Clock skew simulation
- [ ] Message duplication/loss
- [ ] Slow/failed verifier scenarios
- [ ] Lease expiration testing

#### 18.4 Property Verification
- [ ] Extended property tests (P1-P8)
- [ ] Jepsen-style linearizability checks
- [ ] Invariant monitoring
- [ ] Anomaly detection

**Checkpoint**: System resilience verified under chaos conditions

---

### Phase 19: Open Agent Economy (4-5 weeks)

**Goal**: Enable permissionless agent marketplace

#### 19.1 Registry Service
- [ ] Agent manifest registry
- [ ] Capability discovery
- [ ] Reputation tracking
- [ ] Price indexing

#### 19.2 Marketplace Mechanics
- [ ] Agent onboarding flow
- [ ] Conformance testing for new agents
- [ ] Stake requirements
- [ ] Listing and delisting

#### 19.3 Payment Channels
- [ ] Off-chain payment channels
- [ ] Channel opening/closing
- [ ] Micropayments
- [ ] Dispute resolution

#### 19.4 Governance
- [ ] Policy proposal mechanism
- [ ] Voting protocol
- [ ] Parameter adjustment (K values, timeouts)
- [ ] Emergency circuit breakers

**Checkpoint**: Permissionless agent marketplace operational

---

### Phase 20: Production Hardening (3-4 weeks)

**Goal**: Security, performance, and operational excellence

#### 20.1 Security Hardening
- [ ] Sandboxing for untrusted jobs (Firecracker)
- [ ] Process jails
- [ ] Outbound-only relays
- [ ] Rate limiting and DoS protection

#### 20.2 Performance Optimization
- [ ] Bus latency optimization (p99 < 25ms)
- [ ] Policy eval optimization (p95 < 20ms)
- [ ] DECIDE latency optimization (p95 < 2s)
- [ ] Replay performance (10k events < 60s)

#### 20.3 Monitoring & Alerting
- [ ] Metrics collection (Prometheus)
- [ ] Dashboards (Grafana)
- [ ] Alerting rules
- [ ] On-call runbooks

#### 20.4 Deployment Automation
- [ ] Kubernetes manifests
- [ ] Helm charts
- [ ] CI/CD pipelines
- [ ] Canary deployments

**Checkpoint**: Production-ready, secure, performant system

---

## 🔄 Recommended Implementation Order

Given dependencies and complexity, here's the recommended phase order:

### Tier 1: Foundation (Parallel)
1. **Phase 6**: Economic Foundation
2. **Phase 12**: IPFS CAS (simple, standalone)

### Tier 2: Core Protocol (Sequential)
3. **Phase 7**: Market Negotiation (depends on economics)
4. **Phase 11**: WASM Policy Engine (standalone)
5. **Phase 8**: Challenge Protocol (depends on economics + negotiation)

### Tier 3: Distribution (Parallel after Tier 2)
6. **Phase 9**: Distributed Consensus
7. **Phase 10**: Distributed CRDT Plan Store
8. **Phase 13**: P2P Transport (can start in parallel)

### Tier 4: Intelligence (Parallel)
9. **Phase 14**: Intelligent Routing
10. **Phase 17**: Identity & Attestation

### Tier 5: Advanced (Sequential)
11. **Phase 15**: Cross-Shard Coordination (needs distributed consensus)
12. **Phase 16**: GC & Checkpointing

### Tier 6: Ecosystem (Parallel)
13. **Phase 18**: Observability & Chaos
14. **Phase 19**: Open Agent Economy

### Tier 7: Production
15. **Phase 20**: Production Hardening

**Total Timeline**: 6-12 months (depending on team size and parallelization)

---

## 📋 Success Metrics

### Technical Metrics
- **P1-P8 Properties**: All pass under chaos testing
- **Bus Latency**: p99 < 25ms
- **Policy Eval**: p95 < 20ms with gas cap
- **DECIDE Latency**: p95 < 2s under target pool size
- **Replay**: 10k events < 60s
- **Throughput**: 1000+ tasks/sec (vs 10 in v1)
- **Availability**: 99.99% (multi-node)

### Economic Metrics
- **Active Verifiers**: 50+ staked participants
- **Task Diversity**: 10+ agent types
- **Challenge Rate**: < 1% invalid results
- **Stake Security**: Total stake > 100× largest bounty

### Ecosystem Metrics
- **Agent Variety**: 100+ distinct capabilities
- **Cross-Org Participation**: 10+ organizations
- **Geographic Distribution**: 5+ regions
- **Newcomer Success**: 80%+ of new agents earn within 7 days

---

## 🎓 Learning Resources

### For Each Phase

**Economic Systems:**
- Papers: Mechanism design, auction theory
- Projects: Filecoin, Livepeer, Ocean Protocol

**Distributed Consensus:**
- Papers: Raft, Paxos, Byzantine fault tolerance
- Projects: etcd, Consul, CockroachDB

**CRDTs:**
- Papers: Shapiro et al, "CRDTs: Consistency without concurrency control"
- Projects: Automerge, Yjs, OrbitDB

**Policy Engines:**
- OPA documentation
- WASM spec
- Gas metering techniques

**P2P Networks:**
- libp2p documentation
- IPFS/IPLD specs
- Gossipsub protocol

**Routing & ML:**
- Multi-armed bandit algorithms
- Thompson sampling
- Contextual bandits

---

## 🛡️ Risk Mitigation

### Phase-Specific Risks

**Economic Layer (Phase 6):**
- **Risk**: Stake requirements too high/low
- **Mitigation**: Start with bootstrap mode (K_min=1), progressive increase, simulation testing

**Challenge Protocol (Phase 8):**
- **Risk**: DoS via frivolous challenges
- **Mitigation**: Typed proofs with size/gas bounds, challenger bonds, pattern analysis

**Distributed Systems (Phases 9-10):**
- **Risk**: Split-brain, data loss
- **Mitigation**: Epoch fencing, deterministic merge rules, extensive chaos testing

**P2P Migration (Phase 13):**
- **Risk**: Network partitions, NAT traversal failures
- **Mitigation**: Hybrid mode (NATS + libp2p), circuit relays, fallback mechanisms

**Cross-Shard (Phase 15):**
- **Risk**: Deadlocks, circular dependencies
- **Mitigation**: Commit-by-reference (no 2PC), timeout-based rollback, cycle detection

---

## 📦 Deliverables Per Phase

Each phase includes:
1. **Code**: Implementations, tests, migrations
2. **Documentation**: API updates, architecture diagrams
3. **Tests**: Unit, integration, property, chaos
4. **Runbook**: Deployment, operations, troubleshooting
5. **Demo**: Working example proving the phase works

---

## ✨ Final State Capabilities

When all phases are complete, CAN Swarm will:

✅ **Self-Organize**: No central orchestrator; agents discover and negotiate  
✅ **Economic Alignment**: Credits, stake, bounties drive correct behavior  
✅ **Adversarial Robustness**: Challenges with slashing punish bad actors  
✅ **Decentralized**: P2P network, distributed consensus, no SPOF  
✅ **Scalable**: Cross-shard coordination, intelligent routing, GC  
✅ **Open**: Permissionless agent economy, portable identities  
✅ **Auditable**: Deterministic replay from signed audit logs  
✅ **Resilient**: Survives partitions, failures, attacks  
✅ **Efficient**: Local-first computation, delta prompts, tool-first  
✅ **Verifiable**: Quorum-based finality, formal property guarantees  

Welcome to the **Cognitive Agent Network**. 🐝

---

**Last Updated**: 2025-11-24  
**Status**: Roadmap Complete  
**Next Step**: Begin Phase 6 (Economic Foundation)
