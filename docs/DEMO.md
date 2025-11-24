# CAN Swarm v1 PoC — Demo Walkthrough

**Welcome!** This guide will walk you through setting up and running the CAN Swarm v1 Proof of Concept from scratch. You'll see the complete `NEED → PROPOSE → CLAIM → COMMIT → ATTEST → FINALIZE` workflow in action.

---

## 📋 Prerequisites

Before starting, ensure you have:

### Required Software
- **Python 3.9+** ([Download](https://www.python.org/downloads/))
- **Docker** and **Docker Compose** ([Download](https://docs.docker.com/get-docker/))
- **Git** ([Download](https://git-scm.com/downloads))

### Verify Installations
```bash
python3 --version  # Should show 3.9 or higher
docker --version   # Should show Docker version
docker-compose --version  # Should show Docker Compose version
git --version      # Should show Git version
```

### System Requirements
- **OS**: macOS, Linux, or Windows (with WSL2)
- **RAM**: 2GB minimum
- **Disk**: 500MB free space

---

## 🚀 Step-by-Step Setup

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/agent-swarm.git
cd agent-swarm
```

**Expected output:**
```
Cloning into 'agent-swarm'...
```

---

### 2. Create Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

**Expected output:**
```
# Your prompt should now show (.venv) prefix
(.venv) user@machine:~/agent-swarm$
```

> **Note**: You need to activate the virtual environment in every new terminal session before running commands.

---

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

**Expected output:**
```
Collecting nats-py==2.9.0
Collecting pynacl==1.5.0
Collecting redis==5.0.0
...
Successfully installed nats-py-2.9.0 pynacl-1.5.0 redis-5.0.0 ...
```

**Verify installation:**
```bash
pip list | grep -E "nats-py|pynacl|redis|pytest"
```

---

### 4. Generate Cryptographic Keys

The system uses Ed25519 signatures. Generate your signing keys:

```bash
python3 -c "from src.keys import *"
```

**Expected output:**
```
Wrote .env with SWARM_SIGNING_SK_B64 and SWARM_VERIFY_PK_B64
```

This creates a `.env` file with your private signing key and public verification key.

> **Security Note**: The `.env` file contains your secret key. Never commit it to version control (it's already in `.gitignore`).

**Verify:**
```bash
cat .env
```

Should show:
```
SWARM_SIGNING_SK_B64=<base64-string>
SWARM_VERIFY_PK_B64=<base64-string>
```

---

### 5. Start Infrastructure Services

Start NATS JetStream and Redis using Docker Compose:

```bash
docker-compose up -d
```

**Expected output:**
```
Creating network "agent-swarm_default" with the default driver
Creating volume "agent-swarm_nats-data" with default driver
Creating volume "agent-swarm_redis-data" with default driver
Creating nats  ... done
Creating redis ... done
```

**Verify services are running:**
```bash
docker ps
```

Should show:
```
CONTAINER ID   IMAGE                COMMAND                  PORTS
abc123...      nats:2.10-alpine     "nats-server -js ..."    0.0.0.0:4222->4222/tcp, 0.0.0.0:8222->8222/tcp
def456...      redis:7-alpine       "redis-server ..."       0.0.0.0:6379->6379/tcp
```

**Test connectivity:**
```bash
# Test NATS (should return server info)
curl http://localhost:8222/varz

# Test Redis (should return PONG)
docker exec redis redis-cli ping
```

---

## 🎬 Running the Demo

You have two options: **Automated E2E Demo** (recommended for first-time users) or **Manual Step-by-Step** (to see each component).

### Option A: Automated End-to-End Demo (Recommended)

This runs the complete flow automatically.

```bash
.venv/bin/python demo/e2e_flow.py
```

**Expected output:**
```
============================================================
CAN Swarm End-to-End Demo
============================================================

[1/5] Starting Coordinator...
[2/5] Starting agents (Planner, Worker, Verifier)...
[3/5] Publishing NEED message...
✓ Published NEED to thread.{uuid}.need
  Thread ID: {uuid}
  Payload: {'task': 'classify', 'data': 'sample input'}

[4/5] Waiting for agents to process (15 seconds)...
[5/5] Checking results...
============================================================
Checking for FINALIZED tasks...
============================================================

✓ Found 1 FINALIZED task(s):
  - Task {task-id}... (state: FINAL, lamport: 42)

✓ SUCCESS: Flow completed to FINALIZE

============================================================
✓ E2E DEMO PASSED
============================================================

Cleaning up processes...
  ✓ Stopped Coordinator
  ✓ Stopped Planner
  ✓ Stopped Worker
  ✓ Stopped Verifier
```

**What just happened?**
1. Coordinator subscribed to all thread messages
2. Planner, Worker, and Verifier agents started
3. A NEED message was published
4. Planner created a PROPOSE
5. Worker claimed, executed, and published COMMIT
6. Verifier validated and published ATTEST
7. Task reached FINAL state

**Next step:** Run replay to verify determinism (see [Replay Tool](#🔬-deterministic-replay) section below).

---

### Option B: Manual Step-by-Step

To see each component in action, run them in separate terminal windows.

> **Important**: Activate the virtual environment in each terminal with `source .venv/bin/activate`

#### Terminal 1: Start Coordinator

```bash
.venv/bin/python demo/start_coordinator.py
```

**Expected output:**
```
Coordinator started
Subscribing to: thread.>
Waiting for envelopes...
```

Leave this running.

---

#### Terminal 2: Start Planner Agent

```bash
.venv/bin/python agents/planner.py
```

**Expected output:**
```
Planner agent started (ID: planner-{uuid})
Subscribed to: thread.*.need
Waiting for NEED messages...
```

Leave this running.

---

#### Terminal 3: Start Worker Agent

```bash
.venv/bin/python agents/worker.py
```

**Expected output:**
```
Worker agent started (ID: worker-{uuid})
Subscribed to: thread.*.propose
Waiting for PROPOSE messages...
```

Leave this running.

---

#### Terminal 4: Start Verifier Agent

```bash
.venv/bin/python agents/verifier.py
```

**Expected output:**
```
Verifier agent started (ID: verifier-{uuid})
Subscribed to: thread.*.commit
Waiting for COMMIT messages...
```

Leave this running.

---

#### Terminal 5: Publish a NEED

```bash
.venv/bin/python demo/publish_need.py
```

**Expected output:**
```
✓ Published NEED to thread.{uuid}.need
  Thread ID: {uuid}
  Payload: {'task': 'classify', 'data': 'sample input'}
```

**Save the Thread ID** — you'll need it for replay.

---

#### Watch the Flow

In the previous terminals, you should now see:

**Terminal 1 (Coordinator):**
```
Received: NEED from thread.{uuid}.need
Received: PROPOSE from thread.{uuid}.propose
Received: CLAIM from thread.{uuid}.claim
Received: COMMIT from thread.{uuid}.commit
Received: ATTEST from thread.{uuid}.attest
Received: FINALIZE from thread.{uuid}.finalize
```

**Terminal 2 (Planner):**
```
Received NEED: {'task': 'classify', 'data': 'sample input'}
Created proposal for task {task-id}
Published PROPOSE
```

**Terminal 3 (Worker):**
```
Received PROPOSE for task {task-id}
Claiming task...
Executing task...
Stored artifact in CAS: {hash}
Published COMMIT
```

**Terminal 4 (Verifier):**
```
Received COMMIT for task {task-id}
Validating artifact {hash}...
Validation passed
Published ATTEST
Published FINALIZE
```

---

#### Terminal 6: Check Results

```bash
.venv/bin/python demo/check_finalize.py
```

**Expected output:**
```
============================================================
Checking for FINALIZED tasks...
============================================================

✓ Found 1 FINALIZED task(s):
  - Task {task-id}... (state: FINAL, lamport: 42)

✓ SUCCESS: Flow completed to FINALIZE
```

---

## 🔬 Deterministic Replay

One of CAN Swarm's key features is **deterministic replay** — the ability to reconstruct the entire workflow from the audit log.

### Run Replay

First, find your thread ID from the E2E demo or publish_need output. Then:

```bash
.venv/bin/python tools/replay.py <thread-id>
```

**Example:**
```bash
.venv/bin/python tools/replay.py bb9f19b0-acf1-4597-8b0f-529d62d9d3dc
```

**Expected output:**
```
============================================================
Replaying thread: bb9f19b0-acf1-4597-8b0f-529d62d9d3dc
Audit log: logs/swarm.jsonl
============================================================

✓ Found 15 events for thread

[1/5] Verifying signatures...
  ✓ All 15 signatures valid

[2/5] Verifying Lamport ordering...
  ✓ Lamport ordering correct (8 envelopes)

[3/5] Verifying DECIDE uniqueness...
  ✓ 1 DECIDE event(s), all unique

[4/5] Validating policy compliance...
  ✓ All 8 envelopes pass policy

[5/5] Checking final state...
  ✓ Found 1 FINALIZE event(s)

============================================================
✓ REPLAY SUCCESSFUL
============================================================
Events processed: 15
Envelopes validated: 8
DECIDE events: 1
FINALIZE events: 1
============================================================
```

**What was verified?**
- ✅ All cryptographic signatures are valid
- ✅ Lamport clocks maintain causal ordering
- ✅ Only one DECIDE per NEED (consensus uniqueness)
- ✅ All messages comply with policy
- ✅ Final state reached correctly

---

## 🧪 Running Tests

CAN Swarm includes comprehensive tests covering core functionality and system properties.

### Run All Tests

```bash
.venv/bin/pytest tests/ -v
```

**Expected output:**
```
tests/test_consensus.py::test_at_most_once_decide PASSED
tests/test_core.py::test_sign_verify_record PASSED
tests/test_core.py::test_lamport_ordering PASSED
tests/test_core.py::test_envelope_creation PASSED
tests/test_plan_store.py::test_plan_store_basic PASSED
tests/test_plan_store.py::test_state_monotonic PASSED
tests/test_properties.py::test_p1_single_decide PASSED
tests/test_properties.py::test_p2_deterministic_replay PASSED
tests/test_properties.py::test_p3_lamport_ordering PASSED
tests/test_properties.py::test_p4_policy_enforcement PASSED
...

==================== 10 passed in 2.34s ====================
```

### Run Property Tests Only

```bash
.venv/bin/pytest tests/test_properties.py -v
```

These tests verify the four critical properties:
- **P1**: Single DECIDE per NEED (consensus)
- **P2**: Deterministic replay
- **P3**: Lamport ordering
- **P4**: Policy enforcement

---

## 🛠️ Troubleshooting

### Issue: "Missing env var: SWARM_SIGNING_SK_B64"

**Cause:** Keys not generated or `.env` file missing.

**Solution:**
```bash
python3 -c "from src.keys import *"
```

If you see "`.env` already exists", either:
1. Use the existing keys (recommended)
2. Delete `.env` and regenerate: `rm .env && python3 -c "from src.keys import *"`

---

### Issue: "Connection refused" errors from NATS or Redis

**Cause:** Docker services not running.

**Solution:**
```bash
# Check if containers are running
docker ps

# If not running, start them
docker-compose up -d

# Check logs for errors
docker-compose logs nats
docker-compose logs redis
```

**Alternative:** If Docker Compose isn't working, start services manually:
```bash
# Start NATS
docker run -d --name nats -p 4222:4222 -p 8222:8222 nats:2.10-alpine -js

# Start Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

---

### Issue: "No module named 'nats'"

**Cause:** Dependencies not installed or virtual environment not activated.

**Solution:**
```bash
# Ensure venv is activated (you should see (.venv) in prompt)
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

---

### Issue: E2E demo hangs or times out

**Possible causes and solutions:**

**1. Agents not connecting to NATS**
```bash
# Check NATS monitoring UI
curl http://localhost:8222/connz
```

**2. Old NATS consumers blocking**
```bash
# Clean up NATS state
.venv/bin/python tools/cleanup_nats.py
```

**3. Redis state from previous runs**
```bash
# Flush Redis
docker exec redis redis-cli FLUSHDB
```

**4. Check agent logs**
```bash
# If using manual mode, check each terminal for errors
# If using E2E demo, check process outputs
```

---

### Issue: "Plan store not found" when checking finalize

**Cause:** Coordinator hasn't initialized the plan store yet.

**Solution:**
```bash
# Ensure coordinator is running
.venv/bin/python demo/start_coordinator.py

# Wait a few seconds, then try again
```

---

### Issue: "No events found for thread" during replay

**Cause:** Thread ID is incorrect or audit log is missing.

**Solution:**
```bash
# Check if audit log exists
ls -lh logs/swarm.jsonl

# Extract thread IDs from log
grep -o '"thread_id":"[^"]*"' logs/swarm.jsonl | sort -u

# Use the correct thread ID
.venv/bin/python tools/replay.py <correct-thread-id>
```

---

### Issue: Tests fail with "sqlite3.OperationalError: database is locked"

**Cause:** Multiple processes accessing the same SQLite database.

**Solution:**
```bash
# Stop all running agents and coordinator
pkill -f "python.*agents/"
pkill -f "python.*demo/start_coordinator"

# Remove state and try again
rm -rf .state/
```

---

### Issue: Permission denied errors on macOS

**Cause:** Python not allowed to access directories.

**Solution:**
```bash
# Grant full disk access to Terminal in System Preferences
# Or run with explicit permissions:
chmod -R u+w .state/ .cas/ logs/
```

---

## 📊 Understanding the Output

### Audit Log Structure

The audit log at `logs/swarm.jsonl` contains all system events:

```json
{
  "timestamp_ns": 1700000000000000000,
  "thread_id": "bb9f19b0-acf1-4597-8b0f-529d62d9d3dc",
  "subject": "thread.bb9f19b0.need",
  "kind": "BUS.PUBLISH",
  "payload": {
    "id": "msg-123",
    "kind": "NEED",
    "lamport": 1,
    ...
  },
  "sig_pk_b64": "...",
  "sig_b64": "..."
}
```

Every event is cryptographically signed.

---

### Plan Store Schema

The SQLite database at `.state/plan.db` tracks task state:

**Query tasks:**
```bash
sqlite3 .state/plan.db "SELECT task_id, state, last_lamport FROM tasks;"
```

**Query operations:**
```bash
sqlite3 .state/plan.db "SELECT op_type, task_id, lamport FROM ops ORDER BY lamport;"
```

---

### Content-Addressable Storage (CAS)

Artifacts are stored at `.cas/` with SHA256-based addressing:

```bash
# List all artifacts
find .cas -type f

# View an artifact (requires hash from COMMIT message)
cat .cas/ab/cd/abcd1234...
```

---

## 🎓 Next Steps

Congratulations! You've successfully run the CAN Swarm v1 PoC. Here's what to explore next:

### Learn More
- Read [docs/ARCHITECTURE.md](ARCHITECTURE.md) for system design details
- Read [docs/API.md](API.md) for module documentation
- Read [IMPLEMENTATION_ROADMAP.md](../IMPLEMENTATION_ROADMAP.md) for development phases

### Experiment
- Modify `demo/publish_need.py` to send different tasks
- Create your own agent by extending `src/agent.py`
- Add custom handlers in `src/handlers/`

### Test Properties
- Run property tests: `pytest tests/test_properties.py -v`
- Try violating invariants to see safeguards work
- Generate malformed messages to test policy enforcement

### Clean Up

When done, stop services:
```bash
# Stop Docker containers
docker-compose down

# Deactivate virtual environment
deactivate

# Optional: Remove state and logs
rm -rf .state/ .cas/ logs/swarm.jsonl
```

---

## 📞 Getting Help

- **Documentation**: Check [docs/](.) folder
- **Issues**: Open a GitHub issue
- **Logs**: Check `logs/swarm.jsonl` and `*.log` files
- **Tests**: Run `pytest -v` to identify failures

---

**Happy Swarming! 🐝**
