# CAN Swarm - Final Implementation Commands (Phases 9-20)
**Step-by-Step Commands to Complete the Decentralized Agent Economy**

This document provides concrete, copy-paste commands to implement Phases 9-20, completing the CAN Swarm vision.

**Prerequisites**: Phases 0-8 complete (Commands 1-32) ✅

---

## 📋 How to Use This Guide

1. **Copy each command block** and paste into chat
2. **I will implement** the described functionality
3. **Run the checkpoint test** to verify
4. **Move to next command** once tests pass

**Command Sizing**: Each command takes 1-2 hours, creates 2-4 files, has clear checkpoint.

---

## PHASE 9: DISTRIBUTED CONSENSUS

### Command 33: etcd-raft Setup & Integration

```
Implement Phase 9.1 - etcd-raft Setup:

1. Install etcd:
   docker run -d --name etcd \
     -p 2379:2379 -p 2380:2380 \
     quay.io/coreos/etcd:latest \
     /usr/local/bin/etcd \
     --listen-client-urls http://0.0.0.0:2379 \
     --advertise-client-urls http://localhost:2379

2. Add to requirements.txt:
   etcd3==0.12.0

3. Create src/consensus/__init__.py (empty)

4. Create src/consensus/raft_adapter.py with:
   - RaftConsensusAdapter class:
     - __init__(etcd_hosts=[])
     - get_bucket_for_need(need_id) → int (0-255 via SHA256)
     - try_decide(need_id, proposal_id, epoch, lamport, k_plan, decider_id, timestamp_ns)
       - Use etcd.transaction with compare-and-set
       - Return DecideRecord if success, None if conflict
       - Support idempotent retries
     - get_decide(need_id) → Optional[DecideRecord]
   - DecideRecord dataclass:
     - need_id, proposal_id, epoch, lamport, k_plan, decider_id, timestamp_ns

5. Create src/consensus/feature_flag.py with:
   - use_raft_consensus() → bool (check RAFT_CONSENSUS env var)

6. Update src/handlers/decide.py:
   - Import RaftConsensusAdapter and feature_flag
   - If use_raft_consensus(), use raft.try_decide()
   - Else use existing Redis consensus

7. Create tests/test_raft_consensus.py with:
   - test_single_decide_succeeds
   - test_conflicting_decide_fails
   - test_idempotent_retry
   - test_bucket_hashing (consistent, distributed)

8. Add to docker-compose.yml:
   etcd service with ports 2379, 2380, volume etcd-data

Run: RAFT_CONSENSUS=true pytest tests/test_raft_consensus.py -v
```

**Checkpoint:** etcd-raft handles atomic DECIDE with 256-bucket sharding

---

### Command 34: K_plan Quorum Tracking

```
Implement Phase 9.2 - Quorum-Based DECIDE:

1. Create src/consensus/quorum.py with:
   - QuorumState dataclass:
     - need_id, proposal_id, attestations (Set[str]), k_plan_required
     - add_attestation(verifier_id) → bool (returns True if quorum reached)
     - has_quorum() → bool
   - QuorumTracker class:
     - record_attestation(need_id, proposal_id, verifier_id, k_plan) → bool
       - Returns True only if THIS attestation completes quorum
     - check_quorum(need_id, proposal_id) → bool
     - get_k_plan(active_verifiers, alpha=0.3, k_target=5) → int
       - Formula: min(k_target, floor(active × alpha))

2. Update src/handlers/attest_plan.py:
   - Import QuorumTracker, RaftConsensusAdapter, feature_flag
   - Get active verifier count from VerifierPool
   - Calculate k_plan from active count
   - Record attestation in QuorumTracker
   - If quorum reached:
     - Call raft.try_decide() if using Raft
     - Emit DECIDE message on success

3. Create tests/test_quorum.py with:
   - test_quorum_tracking (3 attestations reach K=3)
   - test_quorum_only_triggers_once
   - test_k_plan_calculation (various active counts)
   - test_separate_proposals (don't interfere)

Run: pytest tests/test_quorum.py -v
```

**Checkpoint:** Multiple verifiers vote on proposals, quorum triggers DECIDE

---

### Command 35: Epoch Fencing & Partition Handling

```
Implement Phase 9.3 - Partition Recovery:

1. Create src/consensus/epochs.py with:
   - EpochState dataclass: epoch_number, started_at_ns, coordinator_id
   - EpochManager class:
     - get_current_epoch() → int
     - create_fence_token(epoch=None) → str
     - validate_fence_token(token, current_epoch) → bool
     - advance_epoch(reason) → int (increments epoch)
   - Global: epoch_manager = EpochManager()

2. Create src/consensus/merge.py with:
   - DecideConflict dataclass:
     - need_id, local_decide, remote_decide, winner, reason
   - MergeHandler class:
     - highest_epoch_wins(local_decide, remote_decide) → str ('local' or 'remote')
       - Compare: epoch, then lamport, then decider_id (lexicographic)
     - merge_on_heal(local_decides[], remote_decides[]) → List[DecideConflict]
       - Find conflicting DECIDEs by need_id
       - Resolve using highest_epoch_wins
     - mark_orphaned(decide, winning_epoch, plan_store)
       - Annotate task with orphaned_by_epoch

3. Update src/policy.py:
   Add RECONCILE to ALLOWED_KINDS

4. Create src/handlers/reconcile.py with:
   - handle_reconcile(envelope):
     - Get thread_id, orphaned_branches from payload
     - Advance epoch via epoch_manager
     - Mark orphaned branches in plan_store
     - Log reconciliation summary

5. Create tests/test_partition_handling.py with:
   - test_highest_epoch_wins
   - test_lamport_tiebreaker
   - test_decider_id_tiebreaker
   - test_merge_on_heal (finds conflicts)

Run: pytest tests/test_partition_handling.py -v
```

**Checkpoint:** Partitions heal deterministically, highest-epoch DECIDE wins

---

### Command 36: Bootstrap Mode & Progressive Quorums

```
Implement Phase 9.4 - Bootstrap Mode:

1. Create src/consensus/bootstrap.py with:
   - BootstrapManager class:
     - bootstrap_threshold: int = 10 (min verifiers to exit)
     - bootstrap_stable_hours: int = 24 (stability requirement)
     - is_bootstrap_mode(active_verifiers) → bool
     - calculate_k_result(active_verifiers, bootstrap_mode, k_target=5) → int
       - If bootstrap: return 1
       - Else: return min(k_target, max(2, int(active × 0.3)))
     - should_exit_bootstrap(active_verifiers, hours_above_threshold) → bool
     - boost_challenge_reward(base_reward, bootstrap_mode) → int (2x if bootstrap)
   - Global: bootstrap_manager = BootstrapManager()

2. Update src/consensus/quorum.py:
   - QuorumTracker.get_k_plan_with_bootstrap(active_verifiers, alpha, k_target)
     - Check bootstrap_manager.is_bootstrap_mode()
     - Return 1 if bootstrap, else normal K calculation

3. Create src/daemons/bootstrap_monitor.py with:
   - BootstrapMonitor class:
     - Monitors active verifiers every hour
     - Tracks hours_above_threshold
     - Logs when should exit bootstrap

4. Update src/coordinator.py:
   - Start BootstrapMonitor daemon on init

5. Create tests/test_bootstrap_mode.py with:
   - test_bootstrap_mode_detection (< 10 verifiers)
   - test_k_result_calculation (K=1 in bootstrap, progressive after)
   - test_exit_conditions (10+ verifiers for 24h)
   - test_challenge_reward_boost (2x during bootstrap)

Run: pytest tests/test_bootstrap_mode.py -v
```

**Checkpoint:** Network starts with K=1, exits bootstrap after stability

---

## PHASE 10: DISTRIBUTED CRDT PLAN STORE

### Command 37: Automerge Document Setup

```
Implement Phase 10.1 - Automerge Integration:

1. Install Automerge:
   pip install automerge-py
   echo "automerge-py==0.1.0" >> requirements.txt

2. Create src/plan/automerge_store.py with:
   - Import automerge, OpType, TaskState from plan_store
   - AutomergePlanStore class:
     - __init__(): Initialize Automerge document
     - _init_schema(): Create doc with:
       - tasks: {} (Map)
       - edges: {} (Map of Lists)
       - annotations: {} (Map of Maps with LWW)
       - ops: [] (List for replay)
     - append_op(op: PlanOp):
       - Add to ops list
       - Apply to derived state
     - _apply_to_state(doc, op):
       - ADD_TASK: Create task entry (G-Set)
       - STATE: Update if lamport > last_lamport (monotonic)
       - LINK: Add to edges (G-Set)
       - ANNOTATE: Update if lamport > existing (LWW)
     - get_task(task_id) → Optional[Dict]
     - get_ops_for_thread(thread_id) → List[PlanOp]
     - get_save_data() → bytes (automerge.save)
     - load_from_data(data: bytes)
     - merge_with_peer(peer_data: bytes)

3. Create tests/test_automerge_store.py with:
   - test_add_task
   - test_monotonic_state (higher lamport wins)
   - test_lww_annotations
   - test_save_and_load
   - test_merge_peers (both tasks appear after merge)

Run: pytest tests/test_automerge_store.py -v
```

**Checkpoint:** Automerge CRDT store with G-Set, LWW, and merge

---

### Command 38: Sync Protocol & Peer Discovery

```
Implement Phase 10.2 - Automerge Sync:

1. Create src/plan/sync_protocol.py with:
   - SyncManager class:
     - peers: Dict[str, PeerState] (peer_id → state)
     - register_peer(peer_id, address)
     - sync_with_peer(peer_id):
       - Get peer's save data
       - Merge into local doc
       - Send local save data to peer
     - incremental_sync(peer_id, peer_changes):
       - Apply peer changes via automerge.apply_changes
       - Return local changes since last sync
   - PeerState dataclass: peer_id, address, last_sync_ns, sync_state

2. Create src/plan/peer_discovery.py with:
   - PeerDiscovery class:
     - announce_self(local_address):
       - Broadcast availability on NATS
     - discover_peers() → List[PeerInfo]:
       - Listen for announcements
       - Return list of active peers
   - PeerInfo dataclass: peer_id, address, capabilities

3. Update src/coordinator.py:
   - Initialize SyncManager
   - Start peer discovery
   - Sync plan store with peers every 30 seconds

4. Create tests/test_automerge_sync.py with:
   - test_full_sync (two stores merge completely)
   - test_incremental_sync (only send new changes)
   - test_three_way_merge (A, B, C all converge)
   - test_concurrent_edits (both preserved)

Run: pytest tests/test_automerge_sync.py -v
```

**Checkpoint:** Plan state syncs across nodes automatically

---

### Command 39: Migration from SQLite to Automerge

```
Implement Phase 10.3 - Migration Tool:

1. Create tools/migrate_to_automerge.py with:
   - MigrationTool class:
     - load_from_sqlite(db_path) → List[PlanOp]:
       - Read all ops from SQLite
       - Convert to PlanOp objects
     - export_to_automerge(ops, output_path):
       - Create AutomergePlanStore
       - Replay all ops in lamport order
       - Save to output_path
     - verify_migration(sqlite_path, automerge_path):
       - Load both stores
       - Compare task counts, states, edges
       - Return bool + diff report

2. Add command-line interface:
   - python tools/migrate_to_automerge.py \
       --sqlite-db .state/plan.db \
       --output automerge_plan.bin \
       --verify

3. Create tests/test_migration.py with:
   - test_export_all_ops
   - test_task_equivalence
   - test_edge_equivalence
   - test_annotation_equivalence
   - test_full_migration_pipeline

Run: pytest tests/test_migration.py -v
```

**Checkpoint:** SQLite data successfully migrates to Automerge

---

### Command 40: Derived Views & Query Interface

```
Implement Phase 10.4 - Derived Views:

1. Create src/plan/views.py with:
   - TaskView class:
     - Materialized view of tasks
     - get_tasks_by_state(state) → List[Dict]
     - get_tasks_by_thread(thread_id) → List[Dict]
     - get_ready_tasks() → List[Dict] (DRAFT with no blockers)
   - GraphView class:
     - get_children(task_id) → List[str]
     - get_parents(task_id) → List[str]
     - get_ancestors(task_id) → Set[str] (transitive)
     - get_descendants(task_id) → Set[str] (transitive)
     - topological_sort(thread_id) → List[str]
     - detect_cycles() → List[List[str]]

2. Update src/plan/automerge_store.py:
   - Add update_views() method called after each op
   - Maintain TaskView and GraphView instances
   - Expose view queries

3. Create tests/test_derived_views.py with:
   - test_tasks_by_state
   - test_ready_tasks
   - test_graph_traversal
   - test_topological_sort
   - test_cycle_detection

Run: pytest tests/test_derived_views.py -v
```

**Checkpoint:** Efficient queries on distributed plan state

---

## PHASE 11: WASM POLICY ENGINE

### Command 41: OPA Integration

```
Implement Phase 11.1 - Open Policy Agent:

1. Install OPA:
   brew install opa  # or download binary
   pip install opa-python-client
   echo "opa-python-client==1.3.0" >> requirements.txt

2. Create policies/ directory

3. Create policies/base.rego with base policy:
   package swarm.policy
   
   default allow = false
   
   allow {
     input.kind in allowed_kinds
     input.payload_size < max_payload_size
   }
   
   allowed_kinds = {
     "NEED", "PROPOSE", "CLAIM", "COMMIT", "ATTEST",
     "DECIDE", "FINALIZE", "YIELD", "RELEASE",
     "UPDATE_PLAN", "ATTEST_PLAN", "CHALLENGE",
     "INVALIDATE", "RECONCILE", "CHECKPOINT"
   }
   
   max_payload_size = 1048576  # 1MB

4. Create src/policy/opa_engine.py with:
   - OPAEngine class:
     - __init__(policy_path):
       - Load .rego files
       - Compile to bundle
     - evaluate(envelope) → PolicyResult:
       - Call OPA with envelope as input
       - Return allow/deny + reasons
   - PolicyResult dataclass: allowed, reasons, gas_used

5. Create tests/test_opa_integration.py with:
   - test_allowed_envelope
   - test_disallowed_kind
   - test_payload_size_limit
   - test_policy_versioning

Run: pytest tests/test_opa_integration.py -v
```

**Checkpoint:** OPA evaluates policies against envelopes

---

### Command 42: WASM Compilation & Runtime

```
Implement Phase 11.2 - WASM Policy Runtime:

1. Install WASM tools:
   pip install wasmer wasmer-compiler-cranelift
   echo "wasmer==1.1.0" >> requirements.txt
   echo "wasmer-compiler-cranelift==1.1.0" >> requirements.txt

2. Compile OPA policy to WASM:
   opa build -t wasm -e swarm/policy/allow policies/
   # Produces bundle.tar.gz with policy.wasm

3. Create src/policy/wasm_runtime.py with:
   - WASMRuntime class:
     - __init__(wasm_path, gas_limit=100000):
       - Load WASM module with wasmer
       - Set gas metering limits
     - evaluate(input_json) → PolicyResult:
       - Call WASM entrypoint with input
       - Track gas consumption
       - Return result + gas_used
     - get_policy_hash() → str (SHA256 of WASM)

4. Create src/policy/gas_meter.py with:
   - GasMeter class:
     - Track instruction count
     - Enforce limits (default 100k instructions)
     - Raise GasExceededError if over limit

5. Create tests/test_wasm_runtime.py with:
   - test_wasm_evaluation
   - test_gas_metering
   - test_gas_limit_exceeded
   - test_policy_hash_stability

Run: pytest tests/test_wasm_runtime.py -v
```

**Checkpoint:** WASM policies run with gas metering

---

### Command 43: Three-Gate Enforcement

```
Implement Phase 11.3 - Policy Gates:

1. Create src/policy/gates.py with:
   - PolicyGate enum: PREFLIGHT, INGRESS, COMMIT_GATE
   - GateEnforcer class:
     - preflight_validate(envelope):
       - Client-side check before publishing
       - Fast, cached policy
     - ingress_validate(envelope):
       - Every agent checks on receive
       - Full WASM evaluation
     - commit_gate_validate(envelope, telemetry):
       - Verifiers check actual execution
       - Compare claimed vs actual resources

2. Update src/bus.py:
   - publish_envelope():
     - Add preflight_validate() before NATS publish
   - subscribe_envelope():
     - Add ingress_validate() after NATS receive

3. Update src/handlers/attest.py:
   - commit_gate_validate() before ATTEST
   - Include policy_eval_digest in ATTEST payload

4. Create src/policy/eval_digest.py with:
   - compute_eval_digest(input, decision) → str:
     - Hash(input || decision || policy_hash)
   - verify_eval_digest(envelope) → bool

5. Create tests/test_three_gates.py with:
   - test_preflight_rejects_invalid
   - test_ingress_blocks_bad_envelope
   - test_commit_gate_catches_violations
   - test_eval_digest_verification

Run: pytest tests/test_three_gates.py -v
```

**Checkpoint:** Policies enforced at preflight, ingress, and commit-gate

---

### Command 44: Policy Capsules & Versioning

```
Implement Phase 11.4 - Policy Capsules:

1. Create src/policy/capsule.py with:
   - PolicyCapsule dataclass:
     - policy_engine_hash: str (SHA256 of WASM)
     - policy_schema_version: str
     - conformance_vector: List[str] (passed test IDs)
     - signature: str (capsule signed by author)
   - CapsuleManager class:
     - create_capsule(wasm_path, tests_passed) → PolicyCapsule
     - sign_capsule(capsule, signer_key) → PolicyCapsule
     - verify_capsule(capsule) → bool
     - distribute_capsule(capsule):
       - Publish to NATS for peers
     - receive_capsule(capsule):
       - Validate signature
       - Load if conformance checks pass

2. Create policies/conformance_tests.rego with:
   - Test cases for policy validation
   - Must pass to be conformant

3. Create src/policy/conformance.py with:
   - ConformanceChecker class:
     - run_tests(policy_wasm) → List[str] (passed test IDs)
     - validate_conformance(capsule) → bool

4. Update src/envelope.py:
   - Add policy_capsule_hash field
   - Add policy_eval_digest field

5. Create tests/test_policy_capsules.py with:
   - test_capsule_creation
   - test_capsule_signing
   - test_capsule_distribution
   - test_conformance_validation

Run: pytest tests/test_policy_capsules.py -v
```

**Checkpoint:** Policy capsules distributed with conformance guarantees

---

## PHASE 12: IPFS CAS

### Command 45: IPFS Node Setup

```
Implement Phase 12.1 - IPFS Daemon:

1. Install IPFS:
   brew install ipfs  # or download from ipfs.io
   ipfs init
   ipfs daemon &  # Start in background

2. Install Python client:
   pip install ipfshttpclient
   echo "ipfshttpclient==0.8.0" >> requirements.txt

3. Add to docker-compose.yml:
   ipfs:
     image: ipfs/go-ipfs:latest
     ports:
       - "5001:5001"  # API
       - "8080:8080"  # Gateway
     volumes:
       - ipfs-data:/data/ipfs

4. Create src/cas/ipfs_config.py with:
   - IPFS connection settings
   - Pinning strategy (pin all, pin recent, pin by size)
   - Garbage collection settings

5. Test IPFS connection:
   ipfs add --only-hash README.md  # Test hash without pinning

Run: ipfs id  # Should show peer ID
```

**Checkpoint:** IPFS daemon running and accessible

---

### Command 46: CAS Interface Migration to IPFS

```
Implement Phase 12.2 - IPFS CAS Implementation:

1. Create src/cas/ipfs_store.py with:
   - IPFSContentStore class:
     - Implements same interface as FileCAS
     - __init__(ipfs_host="localhost", ipfs_port=5001)
     - put(data: bytes) → str (returns CID)
       - ipfs.add_bytes(data)
       - Pin the CID
       - Return CID as string
     - get(cid: str) → bytes
       - ipfs.cat(cid)
       - Return bytes
     - exists(cid: str) → bool
     - pin(cid: str) → None
     - unpin(cid: str) → None

2. Create src/cas/feature_flag.py:
   - use_ipfs_cas() → bool (check IPFS_CAS env var)

3. Update src/cas.py:
   - Import IPFSContentStore and feature_flag
   - If use_ipfs_cas(): return IPFSContentStore()
   - Else: return FileCAS()

4. Create tests/test_ipfs_cas.py with:
   - test_put_and_get
   - test_cid_stability (same data → same CID)
   - test_missing_content
   - test_pinning

Run: IPFS_CAS=true pytest tests/test_ipfs_cas.py -v
```

**Checkpoint:** CAS operations work via IPFS with CIDs

---

### Command 47: Data Migration to IPFS

```
Implement Phase 12.3 - File CAS to IPFS Migration:

1. Create tools/migrate_to_ipfs.py with:
   - IPFSMigration class:
     - scan_file_cas(cas_dir) → List[Tuple[hash, path]]:
       - Walk .cas directory
       - Return all stored artifacts
     - migrate_to_ipfs(cas_dir):
       - For each file:
         - Read content
         - Add to IPFS
         - Verify CID matches original hash
         - Log mapping: old_hash → CID
     - create_mapping_file(mappings, output_path):
       - Write JSON: {old_hash: cid}
     - verify_migration(mapping_file):
       - For each mapping:
         - Fetch from IPFS
         - Verify content matches

2. Add command-line interface:
   python tools/migrate_to_ipfs.py \
     --cas-dir .cas \
     --output-mapping cas_to_ipfs.json \
     --verify

3. Create tests/test_ipfs_migration.py with:
   - test_scan_file_cas
   - test_single_file_migration
   - test_hash_to_cid_mapping
   - test_migration_verification

Run: pytest tests/test_ipfs_migration.py -v
```

**Checkpoint:** File CAS artifacts successfully migrated to IPFS

---

### Command 48: IPLD Integration for Envelopes

```
Implement Phase 12.4 - IPLD Structures:

1. Create src/cas/ipld_format.py with:
   - EnvelopeIPLD class:
     - Convert envelope to IPLD DAG format
     - to_ipld(envelope) → dict:
       - Structured with links to content refs
       - {kind, thread, sender, payload: {/: CID}, ...}
     - from_ipld(ipld_data) → envelope:
       - Resolve CID links
       - Reconstruct envelope
   - ThreadIPLD class:
     - Store entire thread as IPLD DAG
     - Linked envelopes with merkle proofs

2. Update src/envelope.py:
   - Add to_ipld() method
   - Add from_ipld() classmethod

3. Create src/cas/merkle_proof.py with:
   - MerkleProof class:
     - build_proof(thread_envelopes, target_index) → proof
     - verify_proof(root_cid, envelope, proof) → bool

4. Create tests/test_ipld_format.py with:
   - test_envelope_to_ipld
   - test_ipld_round_trip
   - test_content_linking
   - test_merkle_proof_generation
   - test_merkle_proof_verification

Run: pytest tests/test_ipld_format.py -v
```

**Checkpoint:** Envelopes stored as IPLD DAGs with merkle proofs

---

## PHASE 13: P2P TRANSPORT LAYER

### Command 49: libp2p Bootstrap

```
Implement Phase 13.1 - libp2p Setup:

1. Install py-libp2p:
   pip install libp2p
   echo "libp2p==0.1.4" >> requirements.txt

2. Create src/p2p/__init__.py

3. Create src/p2p/node.py with:
   - P2PNode class:
     - __init__(listen_addr="/ip4/0.0.0.0/tcp/4001"):
       - Create libp2p host
       - Generate peer ID from Ed25519 key
     - start() → None:
       - Start libp2p host
       - Listen on address
     - stop() → None
     - get_peer_id() → str
     - get_multiaddrs() → List[str]

4. Create src/p2p/identity.py with:
   - Load keypair for peer ID
   - DID:peer generation from libp2p peer ID

5. Create tests/test_p2p_node.py with:
   - test_node_startup
   - test_peer_id_generation
   - test_multiaddr_listening

Run: pytest tests/test_p2p_node.py -v
```

**Checkpoint:** libp2p node starts with peer ID

---

### Command 50: Gossipsub Pubsub

```
Implement Phase 13.2 - Gossipsub Implementation:

1. Create src/p2p/gossipsub.py with:
   - GossipsubRouter class:
     - __init__(p2p_node):
       - Setup gossipsub protocol
       - Configure mesh parameters
     - subscribe(topic, handler):
       - Join topic mesh
       - Register message handler
     - publish(topic, message):
       - Gossip message to mesh peers
       - Handle deduplication
     - get_peers_in_topic(topic) → List[str]

2. Create src/p2p/topics.py with:
   - Topic naming: /swarm/thread/{thread_id}/{verb}
   - Topic discovery and filtering

3. Update src/bus.py:
   - Add P2PBus class (parallel to NATSBus)
   - publish_envelope(): Use gossipsub
   - subscribe_envelope(): Use gossipsub

4. Create tests/test_gossipsub.py with:
   - test_topic_subscription
   - test_message_propagation (2-3 nodes)
   - test_message_deduplication
   - test_peer_scoring

Run: pytest tests/test_gossipsub.py -v
```

**Checkpoint:** Messages propagate via gossipsub

---

### Command 51: Protocol Migration (Hybrid Mode)

```
Implement Phase 13.3 - NATS + libp2p Dual Mode:

1. Create src/bus/hybrid.py with:
   - HybridBus class:
     - Publishes to both NATS and libp2p
     - Subscribes from both, deduplicates
     - Feature flag: P2P_PRIMARY (prefer p2p)
   - MessageCache for deduplication

2. Update src/bus.py:
   - get_bus() → Bus:
     - If P2P_ENABLED: return HybridBus()
     - Else: return NATSBus()

3. Create src/bus/migration_monitor.py with:
   - Track message delivery via both transports
   - Log success rates
   - Alert on divergence

4. Create tests/test_hybrid_bus.py with:
   - test_dual_publish
   - test_deduplication
   - test_fallback_to_nats
   - test_prefer_p2p_mode

Run: P2P_ENABLED=true pytest tests/test_hybrid_bus.py -v
```

**Checkpoint:** Hybrid NATS+libp2p mode operational

---

### Command 52: Peer Discovery (mDNS + DHT)

```
Implement Phase 13.4 - Peer Discovery:

1. Create src/p2p/mdns_discovery.py with:
   - MDNSDiscovery class:
     - Enable mDNS for local network
     - Announce service: _swarm._tcp.local
     - Discover local peers automatically

2. Create src/p2p/dht_discovery.py with:
   - DHTDiscovery class:
     - Bootstrap from known DHT nodes
     - Announce self in DHT
     - Query DHT for peer discovery
     - Store/retrieve peer addresses

3. Create src/p2p/bootstrap_nodes.py with:
   - List of bootstrap nodes
   - Public bootstrap.swarm.network nodes
   - Fallback to IPFS bootstrap nodes

4. Update src/p2p/node.py:
   - Enable mDNS discovery on start
   - Connect to DHT bootstrap nodes
   - Track discovered peers

5. Create tests/test_peer_discovery.py with:
   - test_mdns_discovery (2 local nodes)
   - test_dht_announce_and_find
   - test_bootstrap_connection

Run: pytest tests/test_peer_discovery.py -v
```

**Checkpoint:** Peers discover each other via mDNS and DHT

---

### Command 53: Connection Management

```
Implement Phase 13.5 - Connection Pool & Reputation:

1. Create src/p2p/connection_pool.py with:
   - ConnectionPool class:
     - max_connections: int = 100
     - connection_timeout: int = 30s
     - maintain_connections(target_peer_count):
       - Keep N connections active
       - Rotate low-quality connections
     - get_connection(peer_id) → Connection
     - close_connection(peer_id)

2. Create src/p2p/peer_reputation.py with:
   - PeerReputation class:
     - Track message latency per peer
     - Track reliability (delivered/total)
     - Score peers: 0.0-1.0
     - Blacklist peers below threshold

3. Create src/p2p/circuit_relay.py with:
   - CircuitRelayClient class:
     - Enable relay for NAT traversal
     - Auto-enable if direct connection fails
     - Use relay as fallback

4. Create tests/test_connection_management.py with:
   - test_connection_pool_limits
   - test_peer_scoring
   - test_blacklist_enforcement
   - test_circuit_relay_fallback

Run: pytest tests/test_connection_management.py -v
```

**Checkpoint:** Connection pool manages peers with reputation

---

### Command 54: Complete P2P Migration

```
Implement Phase 13.6 - Full P2P Mode:

1. Update .env.example:
   P2P_ENABLED=true
   P2P_PRIMARY=true
   NATS_FALLBACK=true

2. Create tools/test_p2p_mesh.py:
   - Spawn 5-10 nodes
   - Connect via libp2p
   - Publish NEEDs, verify propagation
   - Measure latency, throughput

3. Update documentation:
   - docs/P2P_DEPLOYMENT.md with:
     - NAT traversal setup
     - Bootstrap node configuration
     - Firewall requirements
     - Circuit relay usage

4. Create tests/test_e2e_p2p.py with:
   - test_full_workflow_p2p_only
   - test_partition_and_heal
   - test_10_node_mesh

Run: P2P_ENABLED=true P2P_PRIMARY=true pytest tests/test_e2e_p2p.py -v
```

**Checkpoint:** System runs fully on P2P with no NATS dependency

---

## PHASE 14: INTELLIGENT ROUTING

### Command 55: Capability Filtering

```
Implement Phase 14.1 - Capability-Based Filtering:

1. Create src/routing/__init__.py

2. Create src/routing/manifests.py with:
   - AgentManifest dataclass:
     - agent_id, capabilities[], io_schema, tags, constraints
     - price_per_task, avg_latency_ms, success_rate
   - ManifestRegistry class:
     - register(manifest)
     - find_by_capability(capability) → List[AgentManifest]
     - find_by_tags(tags) → List[AgentManifest]

3. Create src/routing/filters.py with:
   - CapabilityFilter class:
     - filter_by_io(need, manifests) → List[AgentManifest]
     - filter_by_constraints(need, manifests) → List[AgentManifest]
     - filter_by_zone(need, manifests) → List[AgentManifest]
     - filter_by_budget(need, manifests) → List[AgentManifest]

4. Create tests/test_capability_filtering.py with:
   - test_io_schema_matching
   - test_constraint_filtering
   - test_budget_filtering
   - test_zone_restrictions

Run: pytest tests/test_capability_filtering.py -v
```

**Checkpoint:** Agents filtered by capabilities and constraints

---

### Command 56: Scoring & Shortlisting

```
Implement Phase 14.2 - Agent Scoring:

1. Create src/routing/scoring.py with:
   - AgentScorer class:
     - score_agent(agent_manifest, need, context) → float:
       - f(reputation, price, latency, domain_fit, stake, recency)
       - Weighted formula with configurable weights
     - adjust_for_diversity(scores, diversity_bonus) → scores:
       - Boost under-represented orgs/regions
     - select_top_k(scored_agents, k) → List[AgentManifest]

2. Create src/routing/domain_fit.py with:
   - DomainFitCalculator class:
     - Compute semantic similarity of tags
     - Check past performance in domain
     - Return fit score 0.0-1.0

3. Create src/routing/recency.py with:
   - RecencyWeighter class:
     - Boost recently active agents
     - Decay factor for inactive agents

4. Create tests/test_scoring.py with:
   - test_score_calculation
   - test_diversity_bonus
   - test_top_k_selection
   - test_tie_breaking

Run: pytest tests/test_scoring.py -v
```

**Checkpoint:** Agents scored and shortlisted by multiple factors

---

### Command 57: Canary Testing

```
Implement Phase 14.3 - Canary Micro-Tasks:

1. Create src/routing/canary.py with:
   - CanaryTest dataclass:
     - micro_task, expected_output, timeout_ms
   - CanaryRunner class:
     - create_micro_task(need) → Task:
       - Extract small test from full NEED
     - run_canary(agent_id, micro_task) → CanaryResult:
       - Send micro-task to agent
       - Wait for result (with timeout)
       - Score result quality
   - CanaryResult dataclass:
     - agent_id, latency_ms, quality_score, passed

2. Create src/routing/winner_selection.py with:
   - WinnerSelector class:
     - select_winner(canary_results) → agent_id:
       - Compare quality scores
       - Use latency as tiebreaker
       - Require minimum quality threshold

3. Create tests/test_canary.py with:
   - test_micro_task_creation
   - test_canary_execution
   - test_winner_selection
   - test_timeout_handling

Run: pytest tests/test_canary.py -v
```

**Checkpoint:** Best agents identified via canary tests

---

### Command 58: Contextual Bandit Learning

```
Implement Phase 14.4 - Bandit Routing:

1. Install bandits library:
   pip install scipy numpy
   echo "scipy>=1.9.0" >> requirements.txt
   echo "numpy>=1.23.0" >> requirements.txt

2. Create src/routing/bandit.py with:
   - ContextualBandit class:
     - arms: Dict[str, ArmStats] (agent_id → stats)
     - thompson_sampling(context) → agent_id:
       - Sample from beta distributions
       - Return agent with highest sample
     - ucb1(context, exploration_bonus=2.0) → agent_id:
       - Use UCB1 algorithm
     - update(agent_id, reward, context):
       - Update arm statistics
   - ArmStats dataclass:
     - successes, failures, contexts_seen

3. Create src/routing/features.py with:
   - FeatureExtractor class:
     - extract_context(need) → feature_vector:
       - Domain, complexity, deadline, budget
       - Convert to numeric features

4. Create src/routing/feedback.py with:
   - collect_feedback(task_id, agent_id) → reward:
     - Reward = quality × speed × (1 - cost_ratio)
     - Range: 0.0 (failure) to 1.0 (perfect)

5. Create tests/test_bandit.py with:
   - test_thompson_sampling
   - test_ucb1_exploration
   - test_feedback_updates
   - test_context_learning

Run: pytest tests/test_bandit.py -v
```

**Checkpoint:** Bandit algorithm learns best agents per domain

---

### Command 59: Router Service Integration

```
Implement Phase 14.5 - Complete Routing Pipeline:

1. Create src/routing/router.py with:
   - IntelligentRouter class:
     - Combines: Filter → Score → Canary → Bandit
     - route_need(need) → agent_id:
       1. Filter by capabilities (returns 50-100 agents)
       2. Score and shortlist (top 10)
       3. Run canary on top 2-3
       4. Use bandit to select from canary winners
       5. Fall back to auction if no winner
     - record_outcome(need_id, agent_id, reward)

2. Update src/handlers/need.py:
   - Use IntelligentRouter instead of direct auction
   - If router returns agent: fast-path assignment
   - Else: fall back to auction

3. Create src/routing/metrics.py with:
   - Track routing success rate
   - Track time-to-assignment
   - Track routing accuracy (selected vs best)

4. Create tests/test_intelligent_router.py with:
   - test_full_routing_pipeline
   - test_fallback_to_auction
   - test_routing_metrics
   - test_10x_speedup_vs_auction

Run: pytest tests/test_intelligent_router.py -v
```

**Checkpoint:** NEEDs routed intelligently, 10x faster than auctions

---

## PHASE 15: CROSS-SHARD COORDINATION

### Command 60: Shard Topology & Partitioning

```
Implement Phase 15.1 - Shard Infrastructure:

1. Create src/sharding/__init__.py

2. Create src/sharding/topology.py with:
   - ShardTopology class:
     - get_shard_for_need(need_id) → shard_id (consistent hash)
     - num_shards: int = 256
     - shard_map: Dict[shard_id, List[node_ids]]
   - ShardRegistry class:
     - register_shard(shard_id, node_id, capabilities)
     - get_shard_nodes(shard_id) → List[NodeInfo]
     - health_check(shard_id) → bool

3. Create src/sharding/router.py with:
   - CrossShardRouter class:
     - route_to_shard(need_id, message)
     - get_shard_endpoint(shard_id) → address
     - track_cross_shard_deps(need_id, dep_shard_ids)

4. Create tests/test_shard_topology.py

Run: pytest tests/test_shard_topology.py -v
```

**Checkpoint:** Shard topology operational with consistent hashing

---

### Command 61: Commit-by-Reference Protocol

```
Implement Phase 15.2 - Reference-Based Commits:

1. Create src/sharding/commitment.py with:
   - CommitmentArtifact dataclass:
     - shard_id, need_id, artifact_hash, timestamp_ns
   - CommitmentProtocol class:
     - create_commitment(shard_id, need_id, artifact_ref) → Commitment
     - publish_commitment(commitment)
     - verify_commitment(commitment) → bool
     - get_commitment(shard_id, need_id) → Optional[Commitment]

2. Update src/handlers/commit.py:
   - For cross-shard tasks, create commitment artifact
   - Publish to commitment registry

3. Create tests/test_commitment_protocol.py

Run: pytest tests/test_commitment_protocol.py -v
```

**Checkpoint:** Cross-shard commitments published and verified

---

### Command 62: Escrow Artifacts with TTL

```
Implement Phase 15.3 - Escrow System:

1. Create src/sharding/escrow.py with:
   - EscrowArtifact dataclass:
     - escrow_id, artifact_hash, ttl_ns, shard_dependencies[]
   - EscrowManager class:
     - create_escrow(artifact, dependencies, ttl) → escrow_id
     - add_ready_shard(escrow_id, shard_id)
     - check_all_ready(escrow_id) → bool
     - release_escrow(escrow_id) → artifact
     - expire_escrow(escrow_id) → rollback

2. Create src/daemons/escrow_monitor.py:
   - Monitor escrow TTLs
   - Auto-rollback on timeout

3. Create tests/test_escrow.py

Run: pytest tests/test_escrow.py -v
```

**Checkpoint:** Escrow artifacts coordinate multi-shard commits

---

### Command 63: Dependency Resolution & Rollback

```
Implement Phase 15.4 - Cross-Shard Dependencies:

1. Create src/sharding/dependencies.py with:
   - DependencyDAG class:
     - add_dependency(from_shard, to_shard, need_id)
     - get_ready_shards() → List[shard_id]
     - topo_sort_shards() → List[shard_id]
     - detect_deadlock() → bool
   - RollbackHandler class:
     - rollback_shard(shard_id, reason)
     - salvage_partial_work(shard_id) → artifacts[]

2. Update src/handlers/finalize.py:
   - Check cross-shard dependencies before FINALIZE

3. Create tests/test_cross_shard_deps.py

Run: pytest tests/test_cross_shard_deps.py -v
```

**Checkpoint:** Multi-shard workflows complete without deadlocks

---

## PHASE 16: GC & CHECKPOINTING

### Command 64: Epoch Checkpoints

```
Implement Phase 16.1 - Checkpointing:

1. Create src/checkpoint/__init__.py

2. Create src/checkpoint/merkle.py with:
   - MerkleTree class:
     - build_tree(leaves[]) → root_hash
     - get_proof(leaf_index) → proof[]
     - verify_proof(leaf, proof, root) → bool

3. Create src/checkpoint/checkpoint.py with:
   - CheckpointManager class:
     - create_checkpoint(epoch, plan_state) → Checkpoint
     - sign_checkpoint(checkpoint, verifiers) → SignedCheckpoint
     - store_checkpoint(checkpoint, path)
     - load_checkpoint(path) → Checkpoint
   - Checkpoint dataclass:
     - epoch, merkle_root, state_summary, signatures[]

4. Update src/policy.py: Add CHECKPOINT to ALLOWED_KINDS

5. Create src/handlers/checkpoint.py

6. Create tests/test_checkpointing.py

Run: pytest tests/test_checkpointing.py -v
```

**Checkpoint:** Signed checkpoints created with merkle roots

---

### Command 65: Op-Log Pruning & Tiered Storage

```
Implement Phase 16.2 - Storage Tiers:

1. Create src/checkpoint/pruning.py with:
   - PruningPolicy class:
     - keep_epochs: int = 10
     - should_prune(op, current_epoch) → bool
     - prune_before_epoch(epoch) → pruned_count
   - TieredStorage class:
     - hot_tier: MemoryStore (recent ops)
     - cold_tier: FileStore (old ops)
     - move_to_cold(ops[])
     - retrieve_from_cold(op_ids[]) → ops[]

2. Update src/plan/automerge_store.py:
   - Integrate tiered storage
   - Auto-prune on checkpoint

3. Create tests/test_pruning.py

Run: pytest tests/test_pruning.py -v
```

**Checkpoint:** Old ops pruned, storage growth bounded

---

### Command 66: Fast Sync

```
Implement Phase 16.3 - Fast Sync:

1. Create src/checkpoint/sync.py with:
   - FastSync class:
     - get_latest_checkpoint() → SignedCheckpoint
     - download_checkpoint(checkpoint_id) → bytes
     - apply_checkpoint(data) → plan_state
     - sync_ops_after_epoch(epoch) → ops[]
     - verify_continuity(checkpoint, ops) → bool

2. Update src/coordinator.py:
   - On startup, check for checkpoints
   - Use fast sync if available

3. Create tests/test_fast_sync.py

Run: pytest tests/test_fast_sync.py -v
```

**Checkpoint:** New nodes sync in <60s from checkpoints

---

### Command 67: Deterministic Compression

```
Implement Phase 16.4 - State Compression:

1. Install compression tools:
   pip install zstandard
   echo "zstandard>=0.22.0" >> requirements.txt

2. Create src/checkpoint/compression.py with:
   - DeterministicCompressor class:
     - compress_state(plan_state) → bytes
     - decompress_state(data) → plan_state
     - compress_thread(thread_ops[]) → summary
     - verify_compressed(original, decompressed) → bool

3. Update src/checkpoint/checkpoint.py:
   - Compress checkpoints before storage

4. Create tests/test_compression.py

Run: pytest tests/test_compression.py -v
```

**Checkpoint:** Finalized threads compressed deterministically

---

## PHASE 17: IDENTITY & ATTESTATION

### Command 68: DID Integration

```
Implement Phase 17.1 - Decentralized Identifiers:

1. Install DID library:
   pip install pydid
   echo "pydid>=0.4.0" >> requirements.txt

2. Create src/identity/__init__.py

3. Create src/identity/did.py with:
   - DIDManager class:
     - create_did_key(ed25519_key) → did:key:...
     - create_did_peer(libp2p_peer_id) → did:peer:...
     - resolve_did(did) → DIDDocument
     - sign_with_did(data, did) → signature
     - verify_did_signature(data, sig, did) → bool

4. Create tests/test_did.py

Run: pytest tests/test_did.py -v
```

**Checkpoint:** Agents have portable DID identities

---

### Command 69: Agent Manifests

```
Implement Phase 17.2 - Signed Manifests:

1. Create src/identity/manifest.py with:
   - AgentManifest dataclass:
     - agent_id (DID), capabilities[], io_schema
     - price_per_task, avg_latency_ms, tags[]
     - pubkey, signature
   - ManifestManager class:
     - create_manifest(agent_info) → Manifest
     - sign_manifest(manifest, key) → SignedManifest
     - verify_manifest(manifest) → bool
     - publish_manifest(manifest)

2. Create src/identity/registry.py with:
   - ManifestRegistry class:
     - register(manifest)
     - find_by_capability(cap) → manifests[]
     - get_manifest(agent_id) → Manifest

3. Create tests/test_manifests.py

Run: pytest tests/test_manifests.py -v
```

**Checkpoint:** Manifests signed and discoverable

---

### Command 70: TEE Attestation (Optional)

```
Implement Phase 17.3 - Trusted Execution:

1. Install SGX SDK (if available):
   # Platform-specific, skip if no SGX hardware

2. Create src/identity/attestation.py with:
   - AttestationReport dataclass:
     - quote, mrenclave, mrsigner, report_data
   - TEEVerifier class:
     - generate_quote(report_data) → quote
     - verify_quote(quote) → bool
     - check_mrenclave(quote, expected) → bool

3. Update src/economics/pools.py:
   - Add tee_verified field to verifier registration
   - TEE verifiers get 2x weight

4. Create tests/test_tee_attestation.py (mock)

Run: pytest tests/test_tee_attestation.py -v
```

**Checkpoint:** TEE-backed verifiers supported (optional)

---

### Command 71: Reputation Integration

```
Implement Phase 17.4 - Reputation System:

1. Update src/economics/reputation.py:
   - Integrate with DID identities
   - Track per-DID, not per agent_id
   - Reputation follows identity

2. Update src/routing/scoring.py:
   - Use DID-based reputation in scoring

3. Update src/identity/manifest.py:
   - Include reputation in manifest

4. Create tests/test_reputation_integration.py

Run: pytest tests/test_reputation_integration.py -v
```

**Checkpoint:** Reputation tied to portable DIDs

---

## PHASE 18: OBSERVABILITY & CHAOS

### Command 72: OpenTelemetry

```
Implement Phase 18.1 - Observability:

1. Install OpenTelemetry:
   pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
   echo "opentelemetry-api>=1.20.0" >> requirements.txt
   echo "opentelemetry-sdk>=1.20.0" >> requirements.txt
   echo "opentelemetry-exporter-otlp>=1.20.0" >> requirements.txt

2. Create src/observability/__init__.py

3. Create src/observability/tracing.py with:
   - setup_tracing(service_name)
   - create_span(name, attributes)
   - propagate_context(envelope) → envelope with trace_id

4. Update src/bus.py:
   - Add trace spans for publish/subscribe

5. Add to docker-compose.yml: Jaeger service

6. Create tests/test_tracing.py

Run: pytest tests/test_tracing.py -v
```

**Checkpoint:** Distributed traces collected

---

### Command 73: Deterministic Simulator

```
Implement Phase 18.2 - Replay Simulator:

1. Create tools/simulator.py with:
   - DeterministicSimulator class:
     - load_audit_log(path) → envelopes[]
     - replay_envelopes(envelopes) → final_state
     - inject_clock_skew(delta_ms)
     - inject_message_reorder()
     - verify_finalize_match(expected, actual) → bool

2. Enhance tools/replay.py:
   - Use simulator for replay
   - Support WASM policy replay

3. Create tests/test_simulator.py

Run: pytest tests/test_simulator.py -v
```

**Checkpoint:** Simulator reproduces FINALIZEs exactly

---

### Command 74: Chaos Testing

```
Implement Phase 18.3 - Chaos Harness:

1. Create tools/chaos/__init__.py

2. Create tools/chaos/nemesis.py with:
   - PartitionNemesis (split network)
   - SlowNemesis (delay messages)
   - KillNemesis (crash agents)
   - ClockSkewNemesis (time drift)

3. Create tools/chaos/runner.py:
   - Run E2E with nemeses
   - Verify properties hold

4. Create tests/test_chaos.py with scenarios

Run: pytest tests/test_chaos.py -v
```

**Checkpoint:** System survives chaos scenarios

---

### Command 75: Property Tests (P1-P8)

```
Implement Phase 18.4 - Extended Properties:

1. Update tests/test_properties.py:
   - P1: Single DECIDE ✓ (exists)
   - P2: Deterministic replay ✓ (exists)
   - P3: Challenge safety (new)
   - P4: Epoch fencing ✓ (exists)
   - P5: Lease lifetimes (new)
   - P6: Quorum validity (new)
   - P7: Merkle consistency (new)
   - P8: Cross-shard atomicity (new)

2. Run under chaos:
   pytest tests/test_properties.py --chaos -v

Run: pytest tests/test_properties.py -v
```

**Checkpoint:** All properties verified under chaos

---

## PHASE 19: OPEN AGENT ECONOMY

### Command 76: Agent Registry

```
Implement Phase 19.1 - Registry Service:

1. Create src/marketplace/__init__.py

2. Create src/marketplace/registry.py with:
   - AgentRegistry class:
     - register_agent(manifest, stake) → registration_id
     - update_manifest(agent_id, manifest)
     - search_agents(capabilities, filters) → agents[]
     - get_agent_stats(agent_id) → stats

3. Create API endpoints (FastAPI):
   - POST /agents/register
   - GET /agents/search
   - GET /agents/{id}/stats

4. Create tests/test_registry.py

Run: pytest tests/test_registry.py -v
```

**Checkpoint:** Agent registry operational

---

### Command 77: Marketplace

```
Implement Phase 19.2 - Marketplace:

1. Create src/marketplace/market.py with:
   - TaskMarketplace class:
     - list_available_tasks() → tasks[]
     - get_bid_history(task_id) → bids[]
     - track_price_trends() → analytics
     - rate_agent(agent_id, rating)

2. Create UI (optional):
   - Simple web interface for browsing tasks
   - Agent leaderboard

3. Create tests/test_marketplace.py

Run: pytest tests/test_marketplace.py -v
```

**Checkpoint:** Marketplace shows tasks and bids

---

### Command 78: Payment Channels

```
Implement Phase 19.3 - Off-Chain Payments:

1. Create src/marketplace/channels.py with:
   - PaymentChannel dataclass:
     - channel_id, sender, receiver, capacity, nonce
   - ChannelManager class:
     - open_channel(sender, receiver, deposit) → channel_id
     - send_payment(channel_id, amount, nonce, sig)
     - close_channel(channel_id) → settlement
     - verify_payment(payment) → bool

2. Create tests/test_payment_channels.py

Run: pytest tests/test_payment_channels.py -v
```

**Checkpoint:** Payment channels reduce on-chain costs

---

### Command 79: Governance

```
Implement Phase 19.4 - Governance Protocol:

1. Create src/marketplace/governance.py with:
   - Proposal dataclass:
     - proposal_id, title, description, parameter_changes
   - GovernanceSystem class:
     - submit_proposal(proposal, stake) → proposal_id
     - vote(proposal_id, voter_id, choice, weight)
     - tally_votes(proposal_id) → result
     - execute_proposal(proposal_id)

2. Parameters that can be governed:
   - K_plan, K_result thresholds
   - Bounty caps
   - Slashing percentages

3. Create tests/test_governance.py

Run: pytest tests/test_governance.py -v
```

**Checkpoint:** Governance votes execute parameter changes

---

### Command 80: Circuit Breakers

```
Implement Phase 19.5 - Safety Mechanisms:

1. Create src/marketplace/circuit_breaker.py with:
   - CircuitBreaker class:
     - check_anomaly(metric, threshold) → bool
     - trigger_breaker(reason)
     - reset_breaker()
   - EmergencyStop class:
     - pause_system(reason)
     - resume_system()
   - RateLimiter class:
     - limit_per_agent: int = 100/hour
     - check_rate(agent_id) → bool

2. Create tests/test_circuit_breakers.py

Run: pytest tests/test_circuit_breakers.py -v
```

**Checkpoint:** Circuit breakers tested and functional

---

## PHASE 20: PRODUCTION HARDENING

### Command 81: Firecracker Sandboxing

```
Implement Phase 20.1 - Execution Isolation:

1. Install Firecracker:
   # Download from https://github.com/firecracker-microvm/firecracker

2. Create src/sandbox/__init__.py

3. Create src/sandbox/firecracker.py with:
   - FirecrackerVM class:
     - start_vm(image, resources) → vm_id
     - exec_in_vm(vm_id, command) → output
     - stop_vm(vm_id)
   - ResourceLimits: cpu_cores, mem_mb, disk_mb, net_bw

4. Update agents/worker.py:
   - Run untrusted jobs in Firecracker VMs

5. Create tests/test_firecracker.py

Run: pytest tests/test_firecracker.py -v
```

**Checkpoint:** Jobs isolated in microVMs

---

### Command 82: Performance Optimization

```
Implement Phase 20.2 - Latency Optimization:

1. Profile and optimize:
   - Bus latency: Target p99 <25ms
   - DECIDE latency: Target p95 <2s
   - Policy eval: Target p95 <20ms

2. Create tools/benchmark.py with:
   - load_test(num_tasks, concurrency)
   - measure_latencies() → metrics

3. Optimizations:
   - Connection pooling
   - Message batching
   - Cache frequently accessed data

4. Create tests/test_performance.py

Run: pytest tests/test_performance.py -v
```

**Checkpoint:** Performance targets met

---

### Command 83: Monitoring & Alerting

```
Implement Phase 20.3 - Production Monitoring:

1. Add to docker-compose.yml:
   - Prometheus
   - Grafana
   - Alertmanager

2. Create src/observability/metrics.py with:
   - Export Prometheus metrics
   - Custom metrics for DECIDE latency, etc.

3. Create dashboards/:
   - grafana_dashboard.json

4. Create alerts/:
   - alerting_rules.yml

Run: docker-compose up -d prometheus grafana
```

**Checkpoint:** Dashboards and alerts operational

---

### Command 84: Kubernetes Deployment

```
Implement Phase 20.4 - Container Orchestration:

1. Create Dockerfiles:
   - docker/coordinator.Dockerfile
   - docker/agent.Dockerfile

2. Create k8s/:
   - coordinator-statefulset.yaml
   - agent-deployment.yaml
   - services.yaml
   - configmaps.yaml

3. Create tools/deploy.sh for deployment

Run: kubectl apply -f k8s/
```

**Checkpoint:** System runs on Kubernetes

---

### Command 85: CI/CD Pipeline

```
Implement Phase 20.5 - Automated Deployment:

1. Create .github/workflows/ci.yml:
   - Run tests on PR
   - Build Docker images
   - Push to registry

2. Create .github/workflows/deploy.yml:
   - Canary deployment (10% traffic)
   - Health checks
   - Auto-rollback on failure

3. Add deployment scripts:
   - tools/canary_deploy.sh
   - tools/rollback.sh

Run: git push (triggers CI/CD)
```

**Checkpoint:** CI/CD fully automated

---

## 🎯 Final Success Metrics

**Technical**:
- ✅ P1-P8 properties pass under chaos
- ✅ Bus latency: p99 <25ms
- ✅ DECIDE latency: p95 <2s
- ✅ Throughput: 1000+ tasks/sec

**Economic**:
- ✅ 50+ active staked verifiers
- ✅ <1% invalid results
- ✅ Total stake > 100× largest bounty

**Ecosystem**:
- ✅ 100+ agent capabilities
- ✅ 10+ organizations participating
- ✅ 80%+ newcomer success in 7 days

---

**Total Commands**: 85  
**Estimated Timeline**: 5-9 months  
**Current Progress**: Commands 1-59 (Phases 0-14) detailed, 60-85 (Phases 15-20) now complete
**Next**: Command 33 (etcd-raft Integration) or continue with Phase 9

**🎉 All commands now fully specified and ready for implementation!**
