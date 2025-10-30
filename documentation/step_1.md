# 🧠 CAN Swarm – Phase 1: Intercom + CCTV

## Overview
This phase sets up the **core communication and audit layer** for CAN Swarm.

- **NATS JetStream** → acts as the **Intercom**, a message bus that lets agents publish and receive events.
- **Signed JSONL Logger** → acts as the **CCTV**, recording every message with a cryptographic signature for replay and verification.

This ensures that every message in the Swarm is observable, authentic, and reproducible.

---

## What We’ve Done So Far

### 1 · Project Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install nats-py pynacl msgpack
```
Created a folder structure:
```
agent-swarm/
 ├─ src/
 │   ├─ crypto.py
 │   ├─ audit.py
 │   ├─ bus.py
 │   └─ keys.py
 ├─ examples/
 │   ├─ publisher.py
 │   ├─ listener.py
 │   └─ verify_log.py
 ├─ logs/
 └─ docker-compose.yml
```

---

### 2 · Intercom (NATS JetStream)
We launched a local NATS JetStream server with Docker Compose:

```yaml
version: "3.8"
services:
  nats:
    image: nats:2.10-alpine
    command: ["-js", "-sd", "/data", "--http_port", "8222"]
    ports:
      - "4222:4222"
      - "8222:8222"
    volumes:
      - nats-data:/data
volumes:
  nats-data:
```

This provides a local message bus (`nats://127.0.0.1:4222`) where all agents communicate.

---

### 3 · Key Generation & Identity
We generated a cryptographic key pair using **Ed25519**:

```bash
python src/keys.py
```

This produced a `.env` file containing:
```
SWARM_SIGNING_SK_B64=<private_key>
SWARM_VERIFY_PK_B64=<public_key>
```

These environment variables act as each agent’s **digital identity** for signing and verifying logs.

---

### 4 · Crypto Module (`src/crypto.py`)
Provides helper functions for secure message signing:

- `sign_record(record)` → adds signature + public key  
- `verify_record(record)` → verifies that signature is valid  
- `sha256_hex()` → generates payload hashes  
- Ensures every logged event is cryptographically verifiable.

---

### 5 · Audit Logger (CCTV) (`src/audit.py`)
Creates a **signed JSONL audit trail** in `logs/swarm.jsonl`.

Each log line contains:
```json
{
  "ts_ns": 1730216238594927800,
  "thread_id": "demo-thread",
  "subject": "thread.demo-thread.planner",
  "kind": "BUS.PUBLISH",
  "payload_hash": "e3b0c44298...",
  "payload": {"hello": "world", "n": 1},
  "sig_pk_b64": "...",
  "sig_b64": "..."
}
```
Every entry is **tamper-evident** and **traceable**.

---

### 6 · Bus Module (Intercom) (`src/bus.py`)
Handles all communication with NATS:
- Connects to the JetStream server.  
- Ensures a stream exists (`THREADS`).  
- Publishes messages and subscribes to subjects.  
- Logs every publish and deliver event to the audit log.

---

### 7 · Example Agents
#### Publisher (`examples/publisher.py`)
Sends a simple test message through NATS:
```python
await publish(thread_id, subject, {"hello": "world", "n": 1})
```

#### Listener (`examples/listener.py`)
Receives messages on the same subject and prints them.

#### Result
When both run:
- The listener prints:  
  ```
  Got: {'hello': 'world', 'n': 1}
  ```
- The `logs/swarm.jsonl` file records both the publish and receive events.

---

### 8 · Verification Script (`examples/verify_log.py`)
Checks the authenticity of every record in the audit log:
```bash
python examples/verify_log.py
```
Example output:
```
Verified 2 records, 0 bad
```

This confirms that each message in the system was signed by a valid agent and has not been altered.

---

## ✅ Summary
We now have a **secure, auditable communication backbone** for CAN Swarm.

- Agents can send and receive messages through a verified channel.  
- Every action is logged, signed, and verifiable.  
- The system can replay its own history deterministically.

This completes **Phase 1 – Intercom + CCTV**.
