# API Documentation

Complete API reference for all CAN Swarm modules.

## Table of Contents

- [Core Modules](#core-modules)
  - [crypto](#crypto)
  - [audit](#audit)
  - [bus](#bus)
  - [envelope](#envelope)
  - [lamport](#lamport)
  - [policy](#policy)
- [Storage & State](#storage--state)
  - [cas](#cas)
  - [plan_store](#plan_store)
  - [consensus](#consensus)
- [Agent Framework](#agent-framework)
  - [agent](#agent)
  - [coordinator](#coordinator)
  - [verbs](#verbs)
  - [handlers](#handlers)

---

## Core Modules

### crypto

**Path**: `src/crypto.py`

Cryptographic primitives for signing and verification.

#### Functions

##### `generate_keypair()`
Generates an Ed25519 key pair and saves to `.secrets/`.

```python
from crypto import generate_keypair

generate_keypair()
# Creates .secrets/signing_sk.b64 and .secrets/verify_pk.b64
```

##### `load_signer() -> SigningKey`
Loads the signing key from environment or `.secrets/`.

```python
from crypto import load_signer

sk = load_signer()
```

##### `load_verifier() -> VerifyKey`
Loads the verification key from environment or `.secrets/`.

##### `sign_record(record: dict) -> dict`
Signs a dictionary and returns it with signature fields.

```python
from crypto import sign_record

record = {"data": "example"}
signed = sign_record(record)
# Returns: {..., "sig_pk_b64": "...", "sig_b64": "..."}
```

##### `verify_record(record: dict) -> bool`
Verifies a signed record.

```python
from crypto import verify_record

is_valid = verify_record(signed_record)
```

---

### audit

**Path**: `src/audit.py`

Append-only audit logging with cryptographic signatures.

#### Functions

##### `log_event(thread_id, subject, kind, payload, logfile=None) -> str`
Logs an event to the audit log.

```python
from audit import log_event

log_path = log_event(
    thread_id="abc-123",
    subject="thread.abc-123.need",
    kind="BUS.PUBLISH",
    payload={"data": "example"}
)
```

**Parameters**:
- `thread_id`: Thread identifier
- `subject`: NATS subject
- `kind`: Event type (e.g., "BUS.PUBLISH", "BUS.DELIVER")
- `payload`: Event data (will be hashed)
- `logfile`: Optional log file name (default: "swarm.jsonl")

**Returns**: Path to log file

---

### bus

**Path**: `src/bus.py`

NATS JetStream message bus abstraction.

#### Functions

##### `connect() -> tuple[Client, JetStreamContext]`
Connects to NATS and returns client and JetStream context.

```python
from bus import connect

nc, js = await connect()
```

##### `publish_envelope(thread_id, subject, envelope) -> None`
Publishes a signed envelope.

```python
from bus import publish_envelope

await publish_envelope(
    thread_id="abc-123",
    subject="thread.abc-123.need",
    envelope=signed_envelope
)
```

##### `subscribe_envelopes(thread_id, subject, handler, durable_name=None) -> None`
Subscribes to envelopes with policy validation.

```python
from bus import subscribe_envelopes

async def my_handler(envelope: dict):
    print(f"Received: {envelope['kind']}")

await subscribe_envelopes(
    thread_id="abc-123",
    subject="thread.*.need",
    handler=my_handler,
    durable_name="my-consumer"
)
```

**Parameters**:
- `thread_id`: Thread identifier
- `subject`: NATS subject pattern (supports wildcards)
- `handler`: Async function to handle envelopes
- `durable_name`: Optional durable consumer name (auto-generated if None)

---

### envelope

**Path**: `src/envelope.py`

Envelope creation and management with Lamport clocks.

#### Functions

##### `make_envelope(kind, thread_id, sender_pk_b64, payload, **kwargs) -> dict`
Creates a canonical unsigned envelope.

```python
from envelope import make_envelope
import base64
from crypto import load_verifier

sender_pk = base64.b64encode(bytes(load_verifier())).decode()

env = make_envelope(
    kind="NEED",
    thread_id="abc-123",
    sender_pk_b64=sender_pk,
    payload={"task": "classify"}
)
```

**Returns**: Envelope dict with fields:
- `v`: Version (1)
- `id`: UUID
- `thread_id`: Thread identifier
- `kind`: Message type
- `lamport`: Lamport clock value
- `ts_ns`: Timestamp in nanoseconds
- `sender_pk_b64`: Sender public key
- `payload_hash`: SHA256 of payload
- `payload`: Actual payload data
- `policy_engine_hash`: Policy version hash
- `nonce`: Unique nonce

##### `sign_envelope(envelope: dict) -> dict`
Signs an envelope.

```python
from envelope import sign_envelope

signed = sign_envelope(env)
```

##### `observe_envelope(envelope: dict) -> None`
Updates local Lamport clock based on received envelope.

```python
from envelope import observe_envelope

observe_envelope(received_envelope)
```

---

### lamport

**Path**: `src/lamport.py`

Lamport logical clock implementation.

#### Classes

##### `Lamport`
Thread-safe Lamport clock.

```python
from lamport import Lamport

clock = Lamport()
t1 = clock.tick()  # Returns monotonically increasing value
t2 = clock.tick()
assert t2 > t1

clock.observe(100)  # Update based on received timestamp
t3 = clock.tick()
assert t3 > 100
```

**Methods**:
- `tick() -> int`: Increment and return clock value
- `observe(other_time: int) -> None`: Update clock based on observed time

---

### policy

**Path**: `src/policy.py`

Envelope validation and policy enforcement.

#### Constants

```python
ALLOWED_KINDS = {"NEED", "PLAN", "COMMIT", "ATTEST", "FINAL", 
                 "FINALIZE", "DECIDE", "PROPOSE", "CLAIM", "YIELD", "RELEASE"}
MAX_PAYLOAD_SIZE = 64 * 1024  # 64 KB
```

#### Functions

##### `validate_envelope(envelope: dict) -> None`
Validates an envelope against all policies.

```python
from policy import validate_envelope, PolicyError

try:
    validate_envelope(envelope)
except PolicyError as e:
    print(f"Validation failed: {e}")
```

**Validates**:
- Signature validity
- Envelope kind in allowed list
- Lamport clock > 0
- Payload size < 64KB
- COMMIT has artifact_hash
- Required fields present

##### `current_policy_hash() -> str`
Returns SHA256 hash of current policy version.

---

## Storage & State

### cas

**Path**: `src/cas.py`

Content-Addressable Storage using SHA256.

#### Functions

##### `put(data: bytes) -> str`
Stores bytes and returns SHA256 hash.

```python
from cas import put

data = b"Hello, World!"
artifact_hash = put(data)
# Returns: "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
```

##### `get(artifact_hash: str) -> bytes`
Retrieves bytes by hash.

```python
from cas import get

data = get(artifact_hash)
```

**Raises**: `FileNotFoundError` if artifact doesn't exist

##### `put_json(obj: dict) -> str`
Stores JSON object.

```python
from cas import put_json

result = {"status": "complete", "value": 42}
artifact_hash = put_json(result)
```

##### `get_json(artifact_hash: str) -> dict`
Retrieves JSON object.

```python
from cas import get_json

obj = get_json(artifact_hash)
```

---

### plan_store

**Path**: `src/plan_store.py`

CRDT-based plan and task state management.

#### Classes

##### `OpType`
Enumeration of operation types.

```python
class OpType(Enum):
    ADD_TASK = "ADD_TASK"
    REQUIRES = "REQUIRES"
    PRODUCES = "PRODUCES"
    STATE = "STATE"
    LINK = "LINK"
    ANNOTATE = "ANNOTATE"
```

##### `TaskState`
Enumeration of task states.

```python
class TaskState(Enum):
    DRAFT = "DRAFT"
    DECIDED = "DECIDED"
    VERIFIED = "VERIFIED"
    FINAL = "FINAL"
```

##### `PlanOp`
Dataclass representing a plan operation.

```python
@dataclass
class PlanOp:
    op_id: str
    thread_id: str
    lamport: int
    actor_id: str
    op_type: OpType
    task_id: str
    payload: Dict[str, Any]
    timestamp_ns: int
```

##### `PlanStore`
SQLite-based append-only operation log.

```python
from plan_store import PlanStore, PlanOp, OpType, TaskState
from pathlib import Path
import uuid
import time

# Initialize
store = PlanStore(Path(".state/plan.db"))

# Append operation
op = PlanOp(
    op_id=str(uuid.uuid4()),
    thread_id="abc-123",
    lamport=1,
    actor_id="agent-1",
    op_type=OpType.ADD_TASK,
    task_id="task-1",
    payload={"type": "classify"},
    timestamp_ns=time.time_ns()
)
store.append_op(op)

# Query task
task = store.get_task("task-1")
# Returns: {"task_id": "...", "thread_id": "...", "state": "DRAFT", ...}

# Get operations
ops = store.get_ops_for_thread("abc-123")
```

**Methods**:
- `append_op(op: PlanOp) -> None`: Append operation to log
- `get_task(task_id: str) -> Optional[Dict]`: Get current task state
- `get_ops_for_thread(thread_id: str) -> List[PlanOp]`: Get all ops for thread

---

### consensus

**Path**: `src/consensus.py`

Redis-based consensus for at-most-once DECIDE.

#### Classes

##### `DecideRecord`
Dataclass for DECIDE records.

```python
@dataclass
class DecideRecord:
    need_id: str
    proposal_id: str
    epoch: int
    lamport: int
    k_plan: int
    decider_id: str
    timestamp_ns: int
```

##### `ConsensusAdapter`
Redis-based atomic DECIDE.

```python
from consensus import ConsensusAdapter
import time

consensus = ConsensusAdapter("redis://localhost:6379")

# Try to record DECIDE
result = consensus.try_decide(
    need_id="need-1",
    proposal_id="prop-1",
    epoch=1,
    lamport=10,
    k_plan=1,
    decider_id="verifier-1",
    timestamp_ns=time.time_ns()
)

if result:
    print("DECIDE recorded")
else:
    print("DECIDE already exists for this need")

# Get existing DECIDE
decide = consensus.get_decide("need-1")
if decide:
    print(f"Proposal: {decide.proposal_id}")
```

**Methods**:
- `try_decide(...) -> Optional[DecideRecord]`: Atomically record DECIDE
- `get_decide(need_id: str) -> Optional[DecideRecord]`: Get existing DECIDE

---

## Agent Framework

### agent

**Path**: `src/agent.py`

Base class for all agents.

```python
from agent import BaseAgent

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="my-agent")
    
    async def on_envelope(self, envelope: dict):
        kind = envelope["kind"]
        if kind == "NEED":
            await self.handle_need(envelope)
    
    async def handle_need(self, envelope: dict):
        print(f"Processing NEED: {envelope['payload']}")

# Run agent
agent = MyAgent()
await agent.run(thread_id="abc-123", subject="thread.*.need")
```

---

### coordinator

**Path**: `src/coordinator.py`

Central coordinator managing handlers and stores.

```python
from coordinator import Coordinator
from pathlib import Path

coordinator = Coordinator(
    plan_store_path=Path(".state/plan.db"),
    redis_url="redis://localhost:6379"
)

await coordinator.run(thread_id="abc-123", subject="thread.*.*")
```

---

### verbs

**Path**: `src/verbs.py`

Message dispatcher for verb handlers.

```python
from verbs import DISPATCHER

# Register handler
async def handle_custom(envelope: dict):
    print(f"Handling CUSTOM: {envelope}")

DISPATCHER.register("CUSTOM", handle_custom)

# Dispatch envelope
await DISPATCHER.dispatch(envelope)
```

---

### handlers

**Path**: `src/handlers/`

Individual verb handlers for each message type.

All handlers follow the same pattern:

```python
async def handle_<verb>(envelope: dict):
    """Process <VERB> envelope"""
    # 1. Extract payload
    # 2. Validate
    # 3. Update state
    # 4. Publish response (if needed)
```

Available handlers:
- `need.py`: Handle NEED messages
- `propose.py`: Handle PROPOSE messages
- `claim.py`: Handle CLAIM messages
- `commit.py`: Handle COMMIT messages
- `attest.py`: Handle ATTEST messages
- `decide.py`: Handle DECIDE messages
- `finalize.py`: Handle FINALIZE messages

---

## Usage Examples

### Complete Workflow Example

```python
import asyncio
import uuid
import base64
from crypto import load_verifier
from envelope import make_envelope, sign_envelope
from bus import publish_envelope

async def publish_need():
    thread_id = str(uuid.uuid4())
    sender_pk = base64.b64encode(bytes(load_verifier())).decode()
    
    # Create envelope
    env = make_envelope(
        kind="NEED",
        thread_id=thread_id,
        sender_pk_b64=sender_pk,
        payload={"task": "classify", "data": "sample"}
    )
    
    # Sign and publish
    signed = sign_envelope(env)
    await publish_envelope(
        thread_id=thread_id,
        subject=f"thread.{thread_id}.need",
        envelope=signed
    )
    
    print(f"Published NEED to thread {thread_id}")

asyncio.run(publish_need())
```

---

## Error Handling

### PolicyError

Raised when envelope validation fails.

```python
from policy import PolicyError

try:
    validate_envelope(envelope)
except PolicyError as e:
    print(f"Policy violation: {e}")
```

### Common Exceptions

- `FileNotFoundError`: CAS artifact not found
- `json.JSONDecodeError`: Invalid JSON in log
- `ValueError`: Invalid parameters
- `redis.exceptions.ConnectionError`: Redis unavailable

---

## Best Practices

1. **Always validate envelopes** before processing
2. **Use durable consumer names** for agents to avoid conflicts
3. **Sign all envelopes** before publishing
4. **Store large data in CAS**, not in payloads
5. **Check consensus** before making decisions
6. **Log all operations** to plan store
7. **Handle errors gracefully** and log failures

---

## See Also

- [Architecture Documentation](ARCHITECTURE.md)
- [Implementation Roadmap](../IMPLEMENTATION_ROADMAP.md)
- [README](../README.md)
