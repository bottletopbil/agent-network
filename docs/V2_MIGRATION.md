# CAN Swarm v2 Migration Guide

**From**: v1 Proof of Concept (SQLite, Redis, File-based CAS, Python)  
**To**: v2 Production (Distributed CRDT, Raft Consensus, IPFS, WASM)

This guide provides a phased migration path from the v1 PoC to a production-ready v2 deployment with distributed infrastructure.

---

## 📋 Migration Overview

### v1 → v2 Changes Summary

| Component | v1 PoC | v2 Production | Migration Complexity |
|-----------|--------|---------------|---------------------|
| **Plan Store** | SQLite op-log | Automerge CRDT | Medium |
| **Consensus** | Redis + Lua | etcd-raft | Medium |
| **CAS** | File system | MinIO → IPFS | Low → Medium |
| **Policy Engine** | Python validator | OPA → WASM | High |
| **Deployment** | Single node | Multi-node cluster | High |
| **Message Bus** | NATS JetStream | NATS JetStream (same) | None |
| **Crypto** | Ed25519 (PyNaCl) | Ed25519 (same) | None |

### Migration Strategy

**Recommended Approach**: Progressive enhancement with backward compatibility

1. **Phase 1**: Infrastructure (CAS, Consensus)
2. **Phase 2**: Data Layer (Plan Store)
3. **Phase 3**: Policy Engine
4. **Phase 4**: Multi-node Deployment
5. **Phase 5**: Cutover and Cleanup

**Estimated Timeline**: 4-6 weeks for full migration

---

## 🗄️ Migration 1: Plan Store (SQLite → Automerge)

### Why Migrate?

**v1 Limitations:**
- Single-node SQLite doesn't support distributed writes
- Manual conflict resolution for concurrent ops
- No built-in sync protocol

**v2 Benefits:**
- CRDT guarantees eventual consistency
- Distributed append-only log
- Automatic conflict resolution
- Peer-to-peer synchronization

### Migration Steps

#### Step 1: Install Automerge

```bash
# Add to requirements.txt
automerge-py==0.2.0
```

#### Step 2: Create Automerge Adapter

Create `src/plan_store_v2.py`:

```python
import automerge
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from src.plan_store import PlanOp, OpType, TaskState

class AutomergePlanStore:
    """
    Automerge-based plan store with automatic CRDT sync.
    """
    def __init__(self, peer_id: str):
        self.peer_id = peer_id
        self.doc = automerge.init()
        
    def append_op(self, op: PlanOp) -> None:
        """Append operation to CRDT log"""
        with automerge.transaction(self.doc) as tx:
            if "ops" not in tx:
                tx["ops"] = []
            tx["ops"].append(asdict(op))
            
            # Update derived views
            self._update_task_view(tx, op)
    
    def _update_task_view(self, tx, op: PlanOp):
        """Maintain task view with LWW semantics"""
        if "tasks" not in tx:
            tx["tasks"] = {}
            
        task_id = op.task_id
        if task_id not in tx["tasks"]:
            tx["tasks"][task_id] = {
                "task_id": task_id,
                "thread_id": op.thread_id,
                "state": TaskState.DRAFT.value,
                "last_lamport": 0
            }
        
        task = tx["tasks"][task_id]
        
        # Monotonic state advancement (LWW)
        if op.op_type == OpType.STATE and op.lamport > task["last_lamport"]:
            task["state"] = op.payload["state"]
            task["last_lamport"] = op.lamport
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get current task state"""
        tasks = self.doc.get("tasks", {})
        return tasks.get(task_id)
    
    def sync_with_peer(self, peer_doc_bytes: bytes) -> bytes:
        """
        Sync with peer's document.
        Returns: our document bytes to send to peer
        """
        # Merge peer's changes
        peer_doc = automerge.load(peer_doc_bytes)
        self.doc = automerge.merge(self.doc, peer_doc)
        
        # Return our doc for peer
        return automerge.save(self.doc)
```

#### Step 3: Data Migration Script

Create `tools/migrate_sqlite_to_automerge.py`:

```python
"""
Migrate v1 SQLite plan store to v2 Automerge.

Usage: python tools/migrate_sqlite_to_automerge.py
"""

import sys
sys.path.append("src")

from pathlib import Path
from plan_store import PlanStore, PlanOp
from plan_store_v2 import AutomergePlanStore
import automerge

def migrate_plan_store():
    # Load v1 SQLite store
    v1_store = PlanStore(Path(".state/plan.db"))
    
    # Create v2 Automerge store
    v2_store = AutomergePlanStore(peer_id="migration")
    
    # Get all threads
    cursor = v1_store.conn.execute("SELECT DISTINCT thread_id FROM ops")
    threads = [row[0] for row in cursor.fetchall()]
    
    print(f"Migrating {len(threads)} thread(s)...")
    
    for thread_id in threads:
        ops = v1_store.get_ops_for_thread(thread_id)
        print(f"  Thread {thread_id[:8]}... ({len(ops)} ops)")
        
        for op in ops:
            v2_store.append_op(op)
    
    # Save Automerge document
    output_path = Path(".state/plan_automerge.bin")
    with open(output_path, "wb") as f:
        f.write(automerge.save(v2_store.doc))
    
    print(f"✓ Migration complete: {output_path}")
    print(f"  Original SQLite: .state/plan.db")
    print(f"  New Automerge: {output_path}")

if __name__ == "__main__":
    migrate_plan_store()
```

#### Step 4: Run Migration

```bash
# Backup v1 data
cp .state/plan.db .state/plan.db.v1.backup

# Run migration
.venv/bin/python tools/migrate_sqlite_to_automerge.py

# Verify
ls -lh .state/
```

#### Step 5: Update Coordinator

Modify `src/coordinator.py` to use `AutomergePlanStore`:

```python
from plan_store_v2 import AutomergePlanStore

# Replace:
# self.plan_store = PlanStore(Path(".state/plan.db"))

# With:
self.plan_store = AutomergePlanStore(peer_id=self.agent_id)
```

#### Step 6: Test

```bash
# Run E2E demo with Automerge backend
.venv/bin/python demo/e2e_flow.py

# Verify FINALIZE still works
.venv/bin/python demo/check_finalize.py
```

### Rollback Plan

If migration fails:

```bash
# Stop all services
pkill -f "python.*agents/"
pkill -f "python.*coordinator"

# Restore v1
rm .state/plan_automerge.bin
# v1 will continue using .state/plan.db

# Restart
.venv/bin/python demo/e2e_flow.py
```

---

## 🔐 Migration 2: Consensus (Redis → etcd-raft)

### Why Migrate?

**v1 Limitations:**
- Redis doesn't guarantee strong consistency across failures
- No built-in leader election
- Requires separate Redis cluster for HA

**v2 Benefits:**
- Raft consensus guarantees linearizability
- Built-in leader election and failover
- Production-ready (etcd powers Kubernetes)

### Migration Steps

#### Step 1: Install etcd

```bash
# Docker deployment
docker run -d \
  --name etcd \
  -p 2379:2379 \
  -p 2380:2380 \
  quay.io/coreos/etcd:v3.5.10 \
  /usr/local/bin/etcd \
  --listen-client-urls http://0.0.0.0:2379 \
  --advertise-client-urls http://localhost:2379
```

#### Step 2: Create etcd Consensus Adapter

Create `src/consensus_v2.py`:

```python
"""
etcd-based consensus adapter with Raft guarantees.
"""

import etcd3
import json
from typing import Optional
from dataclasses import dataclass, asdict

@dataclass
class DecideRecord:
    need_id: str
    proposal_id: str
    epoch: int
    lamport: int
    k_plan: int
    decider_id: str
    timestamp_ns: int

class EtcdConsensusAdapter:
    def __init__(self, etcd_host: str = "localhost", etcd_port: int = 2379):
        self.etcd = etcd3.client(host=etcd_host, port=etcd_port)
    
    def try_decide(
        self,
        need_id: str,
        proposal_id: str,
        epoch: int,
        lamport: int,
        k_plan: int,
        decider_id: str,
        timestamp_ns: int
    ) -> Optional[DecideRecord]:
        """
        Atomic DECIDE using etcd transaction.
        Returns DecideRecord if successful, None if conflict.
        """
        key = f"/swarm/decide/{need_id}"
        
        record = DecideRecord(
            need_id=need_id,
            proposal_id=proposal_id,
            epoch=epoch,
            lamport=lamport,
            k_plan=k_plan,
            decider_id=decider_id,
            timestamp_ns=timestamp_ns
        )
        
        value = json.dumps(asdict(record))
        
        # Compare-and-swap: only set if key doesn't exist
        success = self.etcd.transaction(
            compare=[
                self.etcd.transactions.version(key) == 0  # Key doesn't exist
            ],
            success=[
                self.etcd.transactions.put(key, value)
            ],
            failure=[]
        )
        
        if success:
            return record
        
        # Check if it's an idempotent retry
        existing = self.get_decide(need_id)
        if (existing and 
            existing.proposal_id == proposal_id and 
            existing.epoch == epoch):
            return existing
        
        return None
    
    def get_decide(self, need_id: str) -> Optional[DecideRecord]:
        """Get existing DECIDE for a NEED"""
        key = f"/swarm/decide/{need_id}"
        value, _ = self.etcd.get(key)
        
        if not value:
            return None
        
        data = json.loads(value.decode())
        return DecideRecord(**data)
```

#### Step 3: Migration Script

```python
# tools/migrate_redis_to_etcd.py
import redis
import etcd3
import json

def migrate_consensus():
    # Connect to both
    r = redis.from_url("redis://localhost:6379", decode_responses=True)
    e = etcd3.client()
    
    # Get all DECIDE keys from Redis
    keys = r.keys("decide:*")
    print(f"Migrating {len(keys)} DECIDE records...")
    
    for key in keys:
        need_id = key.replace("decide:", "")
        value = r.get(key)
        
        # Write to etcd
        etcd_key = f"/swarm/decide/{need_id}"
        e.put(etcd_key, value)
        print(f"  ✓ {need_id[:8]}...")
    
    print("✓ Migration complete")

if __name__ == "__main__":
    migrate_consensus()
```

#### Step 4: Update Handlers

Replace `ConsensusAdapter` with `EtcdConsensusAdapter` in handlers:

```python
# src/handlers/decide.py
from consensus_v2 import EtcdConsensusAdapter

# Update initialization in coordinator.py
consensus = EtcdConsensusAdapter()
```

#### Step 5: Test Atomicity

```bash
# Run property test for single DECIDE
.venv/bin/pytest tests/test_properties.py::test_p1_single_decide -v
```

---

## 📦 Migration 3: CAS (File System → MinIO → IPFS)

### Phase 3A: File System → MinIO

**Why**: Object storage with S3 API, easier multi-node access

#### Step 1: Deploy MinIO

```yaml
# docker-compose.yml
services:
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: swarm
      MINIO_ROOT_PASSWORD: swarm123
    volumes:
      - minio-data:/data

volumes:
  minio-data:
```

#### Step 2: Create MinIO CAS Adapter

```python
# src/cas_v2.py
from minio import Minio
import hashlib
import json

class MinioCAS:
    def __init__(self, endpoint="localhost:9000", bucket="swarm-cas"):
        self.client = Minio(
            endpoint,
            access_key="swarm",
            secret_key="swarm123",
            secure=False
        )
        self.bucket = bucket
        
        # Create bucket if not exists
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)
    
    def put(self, data: bytes) -> str:
        """Store data, return SHA256 hash"""
        content_hash = hashlib.sha256(data).hexdigest()
        
        self.client.put_object(
            self.bucket,
            content_hash,
            io.BytesIO(data),
            length=len(data)
        )
        
        return content_hash
    
    def get(self, content_hash: str) -> bytes:
        """Retrieve data by hash"""
        response = self.client.get_object(self.bucket, content_hash)
        return response.read()
```

#### Step 3: Migrate Artifacts

```bash
# tools/migrate_cas_to_minio.py
from pathlib import Path
from cas_v2 import MinioCAS

def migrate_cas():
    minio = MinioCAS()
    cas_dir = Path(".cas")
    
    artifacts = list(cas_dir.rglob("*"))
    files = [f for f in artifacts if f.is_file()]
    
    print(f"Migrating {len(files)} artifacts...")
    
    for file_path in files:
        content_hash = file_path.name
        data = file_path.read_bytes()
        
        minio.put(data)
        print(f"  ✓ {content_hash[:8]}...")
    
    print("✓ Migration complete")
```

### Phase 3B: MinIO → IPFS

**Why**: Content-addressed DAG, peer-to-peer, immutability guarantees

#### Step 1: Deploy IPFS

```bash
docker run -d \
  --name ipfs \
  -p 4001:4001 \
  -p 5001:5001 \
  -p 8080:8080 \
  ipfs/kubo:latest
```

#### Step 2: Create IPFS CAS Adapter

```python
# src/cas_v3.py
import ipfshttpclient

class IPFSCAS:
    def __init__(self, api="/ip4/127.0.0.1/tcp/5001"):
        self.client = ipfshttpclient.connect(api)
    
    def put(self, data: bytes) -> str:
        """Store in IPFS, return CID"""
        result = self.client.add_bytes(data)
        return result  # CID (e.g., QmYwAPJzv5CZsnA...)
    
    def get(self, cid: str) -> bytes:
        """Retrieve by CID"""
        return self.client.cat(cid)
```

#### Step 3: Pin Migration

```bash
# Migrate from MinIO to IPFS
python tools/migrate_minio_to_ipfs.py

# Pin important CIDs
ipfs pin add <cid>
```

---

## ⚖️ Migration 4: Policy Engine (Python → OPA → WASM)

### Phase 4A: Python → OPA

**Why**: Declarative Rego policies, easier auditing

#### Step 1: Install OPA

```bash
docker run -d \
  --name opa \
  -p 8181:8181 \
  openpolicyagent/opa:latest \
  run --server
```

#### Step 2: Convert Policies to Rego

```rego
# policies/envelope.rego
package swarm.envelope

default allow = false

# Allow specific envelope kinds
allowed_kinds := {
    "NEED", "PROPOSE", "CLAIM", "COMMIT",
    "ATTEST", "DECIDE", "FINALIZE",
    "YIELD", "RELEASE"
}

allow {
    input.kind in allowed_kinds
    input.payload_size_bytes <= 1048576  # 1MB
}

# COMMIT must have artifact_hash
allow {
    input.kind == "COMMIT"
    input.payload.artifact_hash != null
}
```

#### Step 3: OPA Client

```python
# src/policy_v2.py
import requests

class OPAPolicyEngine:
    def __init__(self, opa_url="http://localhost:8181"):
        self.opa_url = opa_url
    
    def validate_envelope(self, envelope: dict) -> bool:
        """Validate against OPA policy"""
        response = requests.post(
            f"{self.opa_url}/v1/data/swarm/envelope/allow",
            json={"input": envelope}
        )
        
        result = response.json()
        return result.get("result", False)
```

### Phase 4B: OPA → WASM

**Why**: Sandboxing, no remote calls, lower latency

#### Step 1: Compile Rego to WASM

```bash
opa build -t wasm -e swarm/envelope/allow policies/envelope.rego
```

#### Step 2: WASM Runtime

```python
# src/policy_v3.py
from wasmtime import Store, Module, Instance

class WASMPolicyEngine:
    def __init__(self, wasm_path: str):
        store = Store()
        module = Module.from_file(store.engine, wasm_path)
        self.instance = Instance(store, module, [])
    
    def validate_envelope(self, envelope: dict) -> bool:
        """Validate in WASM sandbox"""
        # Call WASM export
        result = self.instance.exports["evaluate"](json.dumps(envelope))
        return result == 1
```

---

## 🌐 Migration 5: Single-Node → Distributed Deployment

### Architecture Changes

**v1**: All components on one machine  
**v2**: Multi-node cluster with service mesh

#### Step 1: Kubernetes Deployment

```yaml
# k8s/coordinator-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: swarm-coordinator
spec:
  replicas: 3  # HA coordinators
  selector:
    matchLabels:
      app: coordinator
  template:
    metadata:
      labels:
        app: coordinator
    spec:
      containers:
      - name: coordinator
        image: swarm/coordinator:v2
        env:
        - name: ETCD_ENDPOINTS
          value: "etcd-0:2379,etcd-1:2379,etcd-2:2379"
        - name: NATS_URL
          value: "nats://nats-cluster:4222"
```

#### Step 2: Service Mesh

```yaml
# Istio sidecar for mutual TLS
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: coordinator
spec:
  hosts:
  - coordinator
  http:
  - route:
    - destination:
        host: coordinator
        subset: v2
      weight: 90
    - destination:
        host: coordinator
        subset: v1
      weight: 10  # Canary deployment
```

#### Step 3: Distributed Tracing

```python
# src/tracing.py with OpenTelemetry
from opentelemetry import trace
from opentelemetry.exporter.jaeger import JaegerExporter

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("handle_envelope")
def handle_envelope(envelope):
    # Traced across all nodes
    ...
```

---

## ✅ Migration Checklist

### Pre-Migration
- [ ] Backup all v1 data (`.state/`, `.cas/`, `logs/`)
- [ ] Document current thread IDs and tasks
- [ ] Run full test suite on v1
- [ ] Export critical audit logs

### During Migration
- [ ] Plan Store: SQLite → Automerge ✓
- [ ] Consensus: Redis → etcd ✓
- [ ] CAS: Files → MinIO → IPFS ✓
- [ ] Policy: Python → OPA → WASM ✓
- [ ] Deploy: Single → Multi-node ✓

### Post-Migration
- [ ] Run E2E demo on v2
- [ ] Verify deterministic replay still works
- [ ] Run property tests (P1-P4)
- [ ] Performance benchmarks
- [ ] Monitor distributed traces

### Rollback Readiness
- [ ] Keep v1 backups for 30 days
- [ ] Document v2 → v1 downgrade path
- [ ] Test rollback procedure

---

## 📊 Expected Improvements

| Metric | v1 PoC | v2 Production | Improvement |
|--------|--------|---------------|-------------|
| **Throughput** | ~10 tasks/sec | ~1000 tasks/sec | 100x |
| **Availability** | Single-node (0.95) | Multi-node (0.999) | 10x |
| **Latency (p99)** | 500ms | 50ms | 10x |
| **Storage** | Local disk | Distributed IPFS | ∞ |
| **Consensus** | Redis (eventual) | Raft (strong) | Linearizable |

---

## 🆘 Troubleshooting

### Automerge Sync Issues
```bash
# Check document size
ls -lh .state/plan_automerge.bin

# Verify CRDT merge
python -c "import automerge; doc = automerge.load(open('.state/plan_automerge.bin', 'rb').read()); print(len(doc['ops']))"
```

### etcd Consensus Failures
```bash
# Check etcd health
etcdctl endpoint health

# View all DECIDE keys
etcdctl get /swarm/decide/ --prefix
```

### IPFS Pinning
```bash
# List pinned CIDs
ipfs pin ls

# Check storage usage
ipfs repo stat
```

---

## 📚 Resources

- **Automerge**: https://automerge.org/
- **etcd**: https://etcd.io/
- **IPFS**: https://ipfs.io/
- **OPA**: https://www.openpolicyagent.org/
- **Kubernetes**: https://kubernetes.io/

---

**Migration Support**: Open an issue on GitHub with `[v2-migration]` tag
