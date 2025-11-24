# CAN Swarm v1 PoC — Implementation Roadmap

**Goal:** Complete a working proof-of-concept demonstrating `NEED → DECIDE → FINALIZE` with deterministic replay.

**Status Legend:**
- ✅ **DONE** — Fully implemented and tested
- 🔄 **IN PROGRESS** — Partially complete
- ⏳ **BLOCKED** — Waiting on dependency
- 📋 **TODO** — Not started, ready to begin
- 🔮 **FUTURE** — Deferred to v2

---

## Technology Stack (Simplified for PoC)

Based on the analysis, here's the recommended stack that balances correctness with implementation speed:

| Component | v1 PoC Choice | Rationale | v2 Migration Path |
|-----------|---------------|-----------|-------------------|
| **Message Bus** | NATS JetStream ✅ | Already working | Keep or add libp2p |
| **CAS** | File-based ✅ | Already working; simple | MinIO/S3 → IPFS |
| **Plan Store** | SQLite op-log 📋 | Simpler than Automerge; same semantics | Automerge/OrbitDB |
| **Consensus** | Redis + Lua 📋 | At-most-once via Lua atomic scripts | etcd-raft |
| **Policy Engine** | Python + gas meter 🔄 | Extend current; add instruction counter | OPA→WASM |
| **Tracing** | OpenTelemetry 📋 | Industry standard | Keep |
| **Deployment** | Docker Compose 🔄 | Already have NATS; add Redis | Kubernetes |

---

## Phase 0: Foundation ✅ **[COMPLETED]**

### What You've Built

#### 0.1 Cryptographic Layer ✅
- **File:** `src/crypto.py`
- **Features:**
  - Ed25519 signing/verification via PyNaCl
  - Canonical JSON serialization
  - SHA256 payload hashing
  - Record signing with detached signatures

#### 0.2 Audit Logging ✅
- **File:** `src/audit.py`
- **Features:**
  - Signed JSONL writer
  - Nanosecond timestamps
  - Thread-based log organization
  - Payload hash tracking

#### 0.3 Message Envelopes ✅
- **File:** `src/envelope.py`
- **Features:**
  - Envelope creation with ID, thread, kind, lamport, sender
  - Payload hashing
  - Signature verification
  - Lamport clock integration

#### 0.4 Lamport Clock ✅
- **File:** `src/lamport.py`
- **Features:**
  - Thread-safe tick/observe operations
  - Persistent state across restarts
  - Correct causal ordering semantics

#### 0.5 Content-Addressable Storage ✅
- **File:** `src/cas.py`
- **Features:**
  - SHA256-based addressing
  - Directory sharding (aa/bb/aabbcc...)
  - Atomic writes (tmp + move)
  - JSON and bytes storage

#### 0.6 NATS JetStream Integration ✅
- **File:** `src/bus.py`
- **Features:**
  - Connection management
  - Stream creation
  - Envelope publishing with policy validation
  - Envelope subscription with verification
  - Audit logging at publish/deliver

#### 0.7 Policy Validation 🔄
- **File:** `src/policy.py`
- **Features:**
  - Kind allowlist (NEED, PLAN, COMMIT, ATTEST, FINAL)
  - Payload size limits
  - Artifact validation for COMMIT
  - Policy versioning via hash
- **Missing:** Gas metering, WASM isolation

#### 0.8 Infrastructure ✅
- **File:** `docker-compose.yml`
- **Features:** NATS container
- **File:** `src/keys.py`
- **Features:** Ed25519 keypair generation

---

## Phase 1: Fix Current Implementation 📋 **[NEXT STEPS]**

**Dependencies:** None (fixes to Phase 0)  
**Estimated Tasks:** 8 items

### 1.1 Fix Policy Hash Mismatch 📋 **[CRITICAL]**

**Problem:** `envelope.py` defaults to `policy_engine_hash="v0"`, but `policy.py` validates against the computed hash.

**File to Modify:** `src/envelope.py`

**Changes:**
```python
# Line 6: Add import
from policy import current_policy_hash

# Line 39: Change default
policy_engine_hash: Optional[str] = None,
) -> Dict[str, Any]:
    # ...
    "policy_engine_hash": policy_engine_hash or current_policy_hash(),
```

**Test:** Run `python examples/publisher_envelope.py` → should not fail policy validation

---

### 1.2 Add Missing Verbs to Policy 📋

**Problem:** README mentions DECIDE but it's not in `ALLOWED_KINDS`.

**File to Modify:** `src/policy.py`

**Changes:**
```python
# Line 9: Update allowlist
ALLOWED_KINDS = {
    "NEED", "PROPOSE", "CLAIM", "COMMIT", 
    "ATTEST", "DECIDE", "FINALIZE", 
    "YIELD", "RELEASE"
}

# Line 18: Update version
"version": 1,  # Increment from 0
```

**Test:** Create envelope with `kind="DECIDE"` → should pass validation

---

### 1.3 Create requirements.txt 📋

**New File:** `requirements.txt`

**Content:**
```
nats-py==2.9.0
pynacl==1.5.0
redis==5.0.0
opentelemetry-api==1.21.0
opentelemetry-sdk==1.21.0
```

**Test:** `pip install -r requirements.txt` in fresh venv

---

### 1.4 Add Backward-Compatible publish()/subscribe() 📋

**Problem:** `examples/publisher.py` and `examples/listener.py` reference non-existent functions.

**File to Modify:** `src/bus.py`

**Changes:**
```python
# Add at end of file

async def publish(thread_id: str, subject: str, message: dict):
    """
    Backward-compatible simple publish (no envelope, no policy).
    Still logs to audit trail.
    """
    await publish_raw(thread_id, subject, message)

async def subscribe(
    thread_id: str,
    subject: str,
    handler: Callable[[dict], Awaitable[None]]
):
    """
    Backward-compatible simple subscribe (no envelope validation).
    """
    nc, js = await connect()
    durable = subject.replace(".", "_")
    sub = await js.subscribe(subject, durable=durable)
    
    async def _runner():
        async for msg in sub.messages:
            try:
                data = json.loads(msg.data.decode())
            except Exception:
                data = {"_raw": msg.data.decode(errors="ignore")}
            
            log_event(thread_id=thread_id, subject=subject, kind="BUS.DELIVER", payload=data)
            await handler(data)
            await msg.ack()
    
    try:
        await _runner()
    finally:
        await nc.drain()
```

**Test:** Run original `publisher.py` and `listener.py` → should work

---

### 1.5 Fix Example Scripts 📋

**Files to Modify:**
- `examples/publisher_envelope.py` (remove `policy_engine_hash="v0"`)
- `examples/publisher_cas.py` (remove `policy_engine_hash="v0"`)

**Changes:** Delete the hardcoded parameter, rely on default

**Test:** All examples run without errors

---

### 1.6 Create Basic Unit Tests 📋

**New File:** `tests/test_core.py`

**Content:**
```python
import pytest
from src.crypto import sign_record, verify_record, cjson
from src.lamport import Lamport
from src.envelope import make_envelope, sign_envelope, verify_envelope
from src.policy import validate_envelope, current_policy_hash
import tempfile
from pathlib import Path

def test_sign_verify_record():
    rec = {"hello": "world", "n": 42}
    signed = sign_record(rec)
    assert verify_record(signed)
    
    # Tamper test
    signed["hello"] = "tampered"
    assert not verify_record(signed)

def test_lamport_ordering():
    clock = Lamport(path=Path(tempfile.mktemp()))
    t1 = clock.tick()
    t2 = clock.tick()
    assert t2 > t1
    
    t3 = clock.observe(100)
    assert t3 == 101

def test_envelope_creation():
    env = make_envelope(
        kind="NEED",
        thread_id="test-thread",
        sender_pk_b64="AAAA",
        payload={"task": "test"}
    )
    assert env["kind"] == "NEED"
    assert env["lamport"] > 0
    assert "payload_hash" in env

def test_policy_validation():
    from crypto import load_verifier
    import base64
    
    env = make_envelope(
        kind="NEED",
        thread_id="test",
        sender_pk_b64=base64.b64encode(bytes(load_verifier())).decode(),
        payload={"x": 1}
    )
    signed = sign_envelope(env)
    
    # Should pass
    validate_envelope(signed)
    
    # Should fail - invalid kind
    bad = sign_envelope(make_envelope(
        kind="INVALID_KIND",
        thread_id="test",
        sender_pk_b64=base64.b64encode(bytes(load_verifier())).decode(),
        payload={}
    ))
    with pytest.raises(Exception):
        validate_envelope(bad)
```

**Test:** `pytest tests/test_core.py -v`

---

### 1.7 Add Docker Compose for Redis 📋

**File to Modify:** `docker-compose.yml`

**Changes:**
```yaml
services:
  nats:
    image: nats:2.10-alpine
    container_name: nats
    command: ["-js", "-sd", "/data", "--http_port", "8222"]
    ports:
      - "4222:4222"
      - "8222:8222"
    volumes:
      - nats-data:/data
  
  redis:
    image: redis:7-alpine
    container_name: redis
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data

volumes:
  nats-data:
  redis-data:
```

**Test:** `docker-compose up -d` → both services running

---

### 1.8 Update .gitignore 📋

**File to Modify:** `.gitignore`

**Add:**
```
.venv/
*.pyc
__pycache__/
.pytest_cache/
logs/*.jsonl
.state/
.cas/
.env
```

---

## Phase 2: Core Infrastructure 📋 **[CRITICAL PATH]**

**Dependencies:** Phase 1 complete  
**Estimated Tasks:** 12 items

This phase builds the orchestration layer that's currently missing.

---

### 2.1 Plan Store Schema (SQLite Op-Log) 📋

**New File:** `src/plan_store.py`

**Purpose:** Implement the CRDT op-log using SQLite with deterministic merge semantics.

**Schema:**
```python
"""
Plan Store: append-only op-log with CRDT semantics.

Tables:
- ops: All plan operations (never deleted)
- tasks: Derived view of current task state
- edges: Derived dependency graph
"""

import sqlite3
import json
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

class OpType(Enum):
    ADD_TASK = "ADD_TASK"
    REQUIRES = "REQUIRES"
    PRODUCES = "PRODUCES"
    STATE = "STATE"
    LINK = "LINK"
    ANNOTATE = "ANNOTATE"

class TaskState(Enum):
    DRAFT = "DRAFT"
    DECIDED = "DECIDED"
    VERIFIED = "VERIFIED"
    FINAL = "FINAL"

@dataclass
class PlanOp:
    """Single operation in the plan log"""
    op_id: str          # UUID
    thread_id: str
    lamport: int
    actor_id: str       # Public key
    op_type: OpType
    task_id: str        # Subject of operation
    payload: Dict[str, Any]
    timestamp_ns: int

class PlanStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.lock = threading.Lock()
        self._init_schema()
    
    def _init_schema(self):
        with self.conn:
            # Op log (append-only)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS ops (
                    op_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    lamport INTEGER NOT NULL,
                    actor_id TEXT NOT NULL,
                    op_type TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    timestamp_ns INTEGER NOT NULL
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_thread ON ops(thread_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_lamport ON ops(lamport)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_task ON ops(task_id)")
            
            # Derived task view
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    task_type TEXT,
                    state TEXT NOT NULL DEFAULT 'DRAFT',
                    last_lamport INTEGER NOT NULL
                )
            """)
            
            # Derived edges
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    parent_id TEXT NOT NULL,
                    child_id TEXT NOT NULL,
                    PRIMARY KEY (parent_id, child_id)
                )
            """)
    
    def append_op(self, op: PlanOp) -> None:
        """Append operation and update derived views"""
        with self.lock:
            with self.conn:
                # Insert op
                self.conn.execute("""
                    INSERT INTO ops 
                    (op_id, thread_id, lamport, actor_id, op_type, task_id, payload_json, timestamp_ns)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    op.op_id, op.thread_id, op.lamport, op.actor_id,
                    op.op_type.value, op.task_id, json.dumps(op.payload), op.timestamp_ns
                ))
                
                # Update derived views
                self._apply_op(op)
    
    def _apply_op(self, op: PlanOp):
        """Update derived tables based on op type"""
        if op.op_type == OpType.ADD_TASK:
            self.conn.execute("""
                INSERT OR IGNORE INTO tasks (task_id, thread_id, task_type, last_lamport)
                VALUES (?, ?, ?, ?)
            """, (op.task_id, op.thread_id, op.payload.get("type"), op.lamport))
        
        elif op.op_type == OpType.STATE:
            # Monotonic: only advance if lamport is newer
            new_state = op.payload["state"]
            self.conn.execute("""
                UPDATE tasks 
                SET state = ?, last_lamport = ?
                WHERE task_id = ? AND last_lamport < ?
            """, (new_state, op.lamport, op.task_id, op.lamport))
        
        elif op.op_type == OpType.LINK:
            parent = op.payload["parent"]
            child = op.payload["child"]
            self.conn.execute("""
                INSERT OR IGNORE INTO edges (parent_id, child_id)
                VALUES (?, ?)
            """, (parent, child))
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get current task state"""
        cursor = self.conn.execute("""
            SELECT task_id, thread_id, task_type, state
            FROM tasks WHERE task_id = ?
        """, (task_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "task_id": row[0],
            "thread_id": row[1],
            "task_type": row[2],
            "state": row[3]
        }
    
    def get_ops_for_thread(self, thread_id: str) -> List[PlanOp]:
        """Get all ops for a thread, ordered by lamport"""
        cursor = self.conn.execute("""
            SELECT op_id, thread_id, lamport, actor_id, op_type, task_id, payload_json, timestamp_ns
            FROM ops
            WHERE thread_id = ?
            ORDER BY lamport ASC
        """, (thread_id,))
        
        ops = []
        for row in cursor:
            ops.append(PlanOp(
                op_id=row[0],
                thread_id=row[1],
                lamport=row[2],
                actor_id=row[3],
                op_type=OpType(row[4]),
                task_id=row[5],
                payload=json.loads(row[6]),
                timestamp_ns=row[7]
            ))
        return ops
```

**Test:**
```python
# tests/test_plan_store.py
import tempfile
from pathlib import Path
from src.plan_store import PlanStore, PlanOp, OpType
import uuid
import time

def test_plan_store_basic():
    db = PlanStore(Path(tempfile.mktemp()))
    
    op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id="test-thread",
        lamport=1,
        actor_id="alice",
        op_type=OpType.ADD_TASK,
        task_id="task-1",
        payload={"type": "classify"},
        timestamp_ns=time.time_ns()
    )
    
    db.append_op(op)
    task = db.get_task("task-1")
    assert task["task_id"] == "task-1"
    assert task["state"] == "DRAFT"
```

---

### 2.2 Consensus Adapter (Redis DECIDE) 📋

**New File:** `src/consensus.py`

**Purpose:** Implement at-most-once DECIDE using Redis + Lua for atomicity.

**Implementation:**
```python
"""
Consensus Adapter: at-most-once DECIDE per NEED using Redis.

Properties:
- At most one DECIDE per NEED (globally unique)
- Epoch-based fencing
- Replayable from audit log
"""

import redis
import json
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class DecideRecord:
    need_id: str
    proposal_id: str
    epoch: int
    lamport: int
    k_plan: int  # How many attestations triggered this
    decider_id: str  # Who made the call
    timestamp_ns: int

class ConsensusAdapter:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        
        # Lua script for atomic DECIDE
        self.decide_script = self.redis.register_script("""
            local need_id = KEYS[1]
            local proposal_id = ARGV[1]
            local epoch = tonumber(ARGV[2])
            local decide_json = ARGV[3]
            
            -- Check if DECIDE already exists
            local existing = redis.call('GET', need_id)
            if existing then
                local existing_data = cjson.decode(existing)
                -- Idempotent: same proposal is OK
                if existing_data.proposal_id == proposal_id and existing_data.epoch == epoch then
                    return existing
                end
                -- Conflict: different DECIDE exists
                return nil
            end
            
            -- Set DECIDE (no expiry - permanent decision)
            redis.call('SET', need_id, decide_json)
            return decide_json
        """)
    
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
        Attempt to record a DECIDE. Returns:
        - DecideRecord if successful (or idempotent retry)
        - None if another DECIDE already exists
        """
        record = DecideRecord(
            need_id=need_id,
            proposal_id=proposal_id,
            epoch=epoch,
            lamport=lamport,
            k_plan=k_plan,
            decider_id=decider_id,
            timestamp_ns=timestamp_ns
        )
        
        decide_json = json.dumps({
            "need_id": need_id,
            "proposal_id": proposal_id,
            "epoch": epoch,
            "lamport": lamport,
            "k_plan": k_plan,
            "decider_id": decider_id,
            "timestamp_ns": timestamp_ns
        })
        
        result = self.decide_script(
            keys=[f"decide:{need_id}"],
            args=[proposal_id, epoch, decide_json]
        )
        
        if result is None:
            return None
        
        return record
    
    def get_decide(self, need_id: str) -> Optional[DecideRecord]:
        """Get existing DECIDE for a NEED"""
        data = self.redis.get(f"decide:{need_id}")
        if not data:
            return None
        
        obj = json.loads(data)
        return DecideRecord(**obj)
```

**Test:**
```python
# tests/test_consensus.py
from src.consensus import ConsensusAdapter
import time

def test_at_most_once_decide():
    adapter = ConsensusAdapter()
    adapter.redis.flushdb()  # Clean slate
    
    # First DECIDE succeeds
    d1 = adapter.try_decide(
        need_id="need-123",
        proposal_id="prop-A",
        epoch=1,
        lamport=42,
        k_plan=1,
        decider_id="alice",
        timestamp_ns=time.time_ns()
    )
    assert d1 is not None
    
    # Second DECIDE for same NEED fails
    d2 = adapter.try_decide(
        need_id="need-123",
        proposal_id="prop-B",  # Different proposal
        epoch=1,
        lamport=43,
        k_plan=1,
        decider_id="bob",
        timestamp_ns=time.time_ns()
    )
    assert d2 is None
    
    # Idempotent retry succeeds
    d3 = adapter.try_decide(
        need_id="need-123",
        proposal_id="prop-A",  # Same as d1
        epoch=1,
        lamport=42,
        k_plan=1,
        decider_id="alice",
        timestamp_ns=d1.timestamp_ns
    )
    assert d3 is not None
```

---

### 2.3 Verb Dispatcher 📋

**New File:** `src/verbs.py`

**Purpose:** Route incoming envelopes to appropriate handlers based on verb/kind.

**Implementation:**
```python
"""
Verb Dispatcher: routes envelopes to handlers based on kind.
"""

from typing import Dict, Callable, Awaitable, Any
from dataclasses import dataclass
import asyncio

VerbHandler = Callable[[Dict[str, Any]], Awaitable[None]]

class VerbDispatcher:
    def __init__(self):
        self.handlers: Dict[str, VerbHandler] = {}
    
    def register(self, kind: str, handler: VerbHandler):
        """Register a handler for a verb kind"""
        self.handlers[kind] = handler
    
    async def dispatch(self, envelope: Dict[str, Any]) -> bool:
        """
        Dispatch envelope to registered handler.
        Returns True if handled, False if no handler.
        """
        kind = envelope.get("kind")
        handler = self.handlers.get(kind)
        
        if handler is None:
            return False
        
        await handler(envelope)
        return True
    
    def list_verbs(self) -> list:
        """List all registered verbs"""
        return list(self.handlers.keys())

# Global dispatcher instance
DISPATCHER = VerbDispatcher()
```

---

### 2.4-2.12 Verb Handlers 📋

Create handlers for each verb. I'll detail the structure for NEED as an example.

**New File:** `src/handlers/need.py`

```python
"""
NEED Handler: initiates a new task request.
"""

import uuid
from src.plan_store import PlanStore, PlanOp, OpType
from src.verbs import DISPATCHER
import time

plan_store: PlanStore = None  # Injected at startup

async def handle_need(envelope: dict):
    """
    Process NEED envelope:
    1. Create task in plan store
    2. Emit NEED event to audit
    3. (Agents will see this and may PROPOSE)
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    
    task_id = str(uuid.uuid4())
    
    # Add task to plan
    op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=envelope["sender_pk_b64"],
        op_type=OpType.ADD_TASK,
        task_id=task_id,
        payload={
            "type": payload.get("task_type", "generic"),
            "requires": payload.get("requires", []),
            "produces": payload.get("produces", [])
        },
        timestamp_ns=time.time_ns()
    )
    
    plan_store.append_op(op)
    print(f"[NEED] Created task {task_id} in thread {thread_id}")

# Register with dispatcher
DISPATCHER.register("NEED", handle_need)
```

**Similar handlers needed for:** PROPOSE, CLAIM, COMMIT, ATTEST, DECIDE, FINALIZE

---

## Phase 3: Agent Implementation 📋

**Dependencies:** Phase 2 complete  
**Estimated Tasks:** 10 items

---

### 3.1 Base Agent Class 📋

**New File:** `src/agent.py`

```python
"""
Base Agent: common functionality for all agent types.
"""

import asyncio
from abc import ABC, abstractmethod
from src.bus import subscribe_envelopes
from src.verbs import DISPATCHER

class BaseAgent(ABC):
    def __init__(self, agent_id: str, public_key_b64: str):
        self.agent_id = agent_id
        self.public_key_b64 = public_key_b64
    
    @abstractmethod
    async def on_envelope(self, envelope: dict):
        """Override to handle incoming envelopes"""
        pass
    
    async def run(self, thread_id: str, subject: str):
        """Main agent loop"""
        print(f"[{self.agent_id}] Starting on {subject}")
        await subscribe_envelopes(thread_id, subject, self.on_envelope)
```

---

### 3.2 Planner Agent 📋

**New File:** `agents/planner.py`

```python
"""
Planner Agent: listens for NEED, creates proposals.
"""

import uuid
import base64
from src.agent import BaseAgent
from src.envelope import make_envelope, sign_envelope
from src.bus import publish_envelope
from src.crypto import load_verifier

class PlannerAgent(BaseAgent):
    async def on_envelope(self, envelope: dict):
        kind = envelope.get("kind")
        
        if kind == "NEED":
            await self.handle_need(envelope)
    
    async def handle_need(self, envelope: dict):
        """Create a simple plan proposal"""
        thread_id = envelope["thread_id"]
        need_payload = envelope["payload"]
        
        # Simple proposal: one worker task
        proposal = {
            "plan": [
                {
                    "task_id": str(uuid.uuid4()),
                    "type": "worker",
                    "input": need_payload
                }
            ]
        }
        
        env = make_envelope(
            kind="PROPOSE",
            thread_id=thread_id,
            sender_pk_b64=self.public_key_b64,
            payload=proposal
        )
        
        signed = sign_envelope(env)
        subject = f"thread.{thread_id}.planner"
        
        await publish_envelope(thread_id, subject, signed)
        print(f"[PLANNER] Proposed plan for thread {thread_id}")

# Run as standalone process
if __name__ == "__main__":
    import asyncio
    agent = PlannerAgent(
        agent_id="planner-1",
        public_key_b64=base64.b64encode(bytes(load_verifier())).decode()
    )
    asyncio.run(agent.run("demo-thread", "thread.*.need"))
```

---

### 3.3-3.6 Worker, Verifier, Aggregator Agents 📋

Similar structure to Planner. Details in separate files.

---

## Phase 4: Integration & Demo 📋

**Dependencies:** Phase 3 complete  
**Estimated Tasks:** 6 items

---

### 4.1 End-to-End Demo Script 📋

**New File:** `demo/e2e_flow.py`

```python
"""
End-to-end demo: NEED → DECIDE → FINALIZE

Runs all agents in separate processes and orchestrates the flow.
"""

import asyncio
import subprocess
import time

async def main():
    print("Starting CAN Swarm E2E Demo")
    print("=" * 50)
    
    # 1. Start agents in background
    planner = subprocess.Popen(["python", "agents/planner.py"])
    worker = subprocess.Popen(["python", "agents/worker.py"])
    verifier = subprocess.Popen(["python", "agents/verifier.py"])
    
    time.sleep(2)  # Let agents connect
    
    # 2. Publish NEED
    print("\n[DEMO] Publishing NEED...")
    subprocess.run(["python", "demo/publish_need.py"])
    
    # 3. Wait for processing
    print("\n[DEMO] Waiting for agents to process...")
    time.sleep(10)
    
    # 4. Check final state
    print("\n[DEMO] Checking results...")
    subprocess.run(["python", "demo/check_finalize.py"])
    
    # 5. Cleanup
    planner.terminate()
    worker.terminate()
    verifier.terminate()
    
    print("\n[DEMO] Complete!")

if __name__ == "__main__":
    asyncio.run(main())
```

---

### 4.2 Deterministic Replay Tool 📋

**New File:** `tools/replay.py`

```python
"""
Deterministic Replay: verify a thread by replaying its audit log.
"""

import json
import sys
from pathlib import Path
from src.crypto import verify_record
from src.policy import validate_envelope
from src.plan_store import PlanStore, PlanOp, OpType

def replay_thread(log_path: str, thread_id: str):
    """
    Replay a thread from audit log and verify:
    1. All signatures valid
    2. All policies pass
    3. Lamport ordering correct
    4. DECIDE is unique
    5. Final state matches
    """
    
    print(f"Replaying thread {thread_id} from {log_path}")
    
    events = []
    with open(log_path) as f:
        for line in f:
            event = json.loads(line.strip())
            if event.get("thread_id") == thread_id:
                events.append(event)
    
    print(f"Found {len(events)} events")
    
    # Verify signatures
    print("\n[1/5] Verifying signatures...")
    for i, event in enumerate(events):
        if not verify_record(event):
            print(f"  ✗ Event {i}: BAD SIGNATURE")
            return False
    print(f"  ✓ All {len(events)} signatures valid")
    
    # Verify lamport ordering
    print("\n[2/5] Verifying Lamport ordering...")
    last_lamport = 0
    for event in events:
        payload = event.get("payload", {})
        if "lamport" in payload:
            if payload["lamport"] <= last_lamport:
                print(f"  ✗ Lamport not monotonic: {last_lamport} -> {payload['lamport']}")
                return False
            last_lamport = payload["lamport"]
    print(f"  ✓ Lamport ordering correct")
    
    # Verify DECIDE uniqueness
    print("\n[3/5] Verifying DECIDE uniqueness...")
    decides = [e for e in events if e.get("payload", {}).get("kind") == "DECIDE"]
    need_decides = {}
    for d in decides:
        need_id = d["payload"]["payload"].get("need_id")
        if need_id in need_decides:
            print(f"  ✗ Multiple DECIDE for NEED {need_id}")
            return False
        need_decides[need_id] = d
    print(f"  ✓ {len(decides)} DECIDE events, all unique")
    
    # Check FINALIZE
    print("\n[4/5] Checking FINALIZE...")
    finalizes = [e for e in events if e.get("payload", {}).get("kind") == "FINALIZE"]
    print(f"  Found {len(finalizes)} FINALIZE events")
    
    print("\n[5/5] Replay complete!")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/replay.py <thread_id>")
        sys.exit(1)
    
    success = replay_thread("logs/swarm.jsonl", sys.argv[1])
    sys.exit(0 if success else 1)
```

---

### 4.3-4.6 Property Tests 📋

**Files:**
- `tests/test_properties.py` - P1: Single DECIDE
- `tests/test_replay.py` - P2: Deterministic replay
- `tests/test_challenge.py` - P3: Challenge safety (stub for now)
- `tests/test_fencing.py` - P4: Lease/fencing

---

## Phase 5: Documentation & Polish 📋

**Dependencies:** Phase 4 complete  
**Estimated Tasks:** 6 items

---

### 5.1 Update README 📋

Add:
- Quick start guide
- Architecture diagram
- Demo instructions
- Links to documentation

---

### 5.2 API Documentation 📋

**New File:** `docs/API.md`

Document all modules, functions, and message schemas.

---

### 5.3 Architecture Diagrams 📋

**New File:** `docs/ARCHITECTURE.md`

Include:
- System diagram
- Message flow diagram
- State machine diagram

---

### 5.4 Demo Walkthrough 📋

**New File:** `docs/DEMO.md`

Step-by-step guide to running the E2E demo.

---

### 5.5 Migration Notes 📋

**New File:** `docs/V2_MIGRATION.md`

Document the path from current simplified stack to full v2:
- SQLite → Automerge
- Redis → etcd-raft
- File CAS → MinIO → IPFS

---

### 5.6 Contribution Guide 📋

**New File:** `CONTRIBUTING.md`

For future contributors.

---

## Success Criteria (PoC Complete)

The v1 PoC is **complete** when:

1. ✅ **Core Loop Works**
   - NEED published → agents see it
   - PROPOSE generated → stored in plan
   - DECIDE recorded → exactly once per NEED
   - COMMIT published → artifact in CAS
   - ATTEST aggregated → K threshold reached
   - FINALIZE emitted → logged to audit

2. ✅ **Replay Succeeds**
   - `tools/replay.py <thread-id>` verifies all events
   - Same inputs → same FINALIZE

3. ✅ **Tests Pass**
   - Unit tests: 100% pass
   - Integration test: E2E flow succeeds
   - Property tests: P1-P4 hold

4. ✅ **Demo Runs**
   - `python demo/e2e_flow.py` completes successfully
   - Output shows full NEED→FINALIZE trace

5. ✅ **Documentation Complete**
   - README explains project
   - API docs exist
   - Demo walkthrough works

---

## Next Immediate Actions (Start Here)

Since you're ready to begin, here's your ordered checklist for the next few days:

### Day 1: Fix Current Code
1. [ ] Fix policy hash in `envelope.py` (5 min)
2. [ ] Add DECIDE to `policy.py` allowlist (5 min)
3. [ ] Create `requirements.txt` (5 min)
4. [ ] Add `publish()`/`subscribe()` to `bus.py` (30 min)
5. [ ] Fix example scripts (15 min)
6. [ ] Test all examples run (15 min)
7. [ ] Add Redis to `docker-compose.yml` (10 min)
8. [ ] Create basic unit tests (1 hour)

**Deliverable:** All Phase 0 code works, examples run without errors.

### Day 2: Plan Store
1. [ ] Implement `src/plan_store.py` (3 hours)
2. [ ] Write tests for plan_store (1 hour)
3. [ ] Test op-log operations (30 min)

**Deliverable:** Working plan storage with CRDT semantics.

### Day 3: Consensus
1. [ ] Implement `src/consensus.py` (2 hours)
2. [ ] Write tests for DECIDE atomicity (1 hour)
3. [ ] Test epoch handling (30 min)

**Deliverable:** At-most-once DECIDE working.

### Days 4-5: Verb System
1. [ ] Implement `src/verbs.py` dispatcher (1 hour)
2. [ ] Implement NEED handler (1 hour)
3. [ ] Implement PROPOSE handler (1 hour)
4. [ ] Implement ATTEST handler (1 hour)
5. [ ] Implement DECIDE handler (2 hours)
6. [ ] Implement FINALIZE handler (1 hour)

**Deliverable:** Full verb routing pipeline.

### Days 6-8: Agents
1. [ ] Implement base agent (1 hour)
2. [ ] Implement planner agent (2 hours)
3. [ ] Implement worker agent (3 hours)
4. [ ] Implement verifier agent (2 hours)
5. [ ] Test agents independently (2 hours)

**Deliverable:** Three working agents.

### Days 9-10: Integration
1. [ ] E2E demo script (2 hours)
2. [ ] Replay tool (3 hours)
3. [ ] Property tests (2 hours)
4. [ ] Fix bugs from integration (variable)

**Deliverable:** Working end-to-end demo.

### Days 11-12: Documentation
1. [ ] Update README (2 hours)
2. [ ] Write API docs (2 hours)
3. [ ] Create diagrams (2 hours)
4. [ ] Demo walkthrough (1 hour)

**Deliverable:** Complete documentation.

---

## Questions / Decisions Needed

None at this time - you've given full autonomy on stack choices. Proceeding with:
- SQLite for plan store
- Redis for DECIDE consensus
- Python-only implementation
- File-based CAS (keep existing)
- Simplified policy (extend existing)

This gives you a clear path to a working PoC in ~2 weeks of focused work!
