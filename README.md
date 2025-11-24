# CAN Swarm v1 PoC

> **Cognitive Agent Network** — A verifiable, deterministic, and auditable cooperative AI system

[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)]() [![Python](https://img.shields.io/badge/python-3.9+-blue.svg)]() [![License](https://img.shields.io/badge/license-MIT-blue.svg)]()

## 🎯 What is CAN Swarm?

CAN Swarm is a framework for building **cooperative AI systems** where autonomous agents coordinate, verify, and execute tasks collectively in a transparent and auditable way.

The v1 Proof of Concept demonstrates the core principles of:
- **Auditability**: Every action is cryptographically signed and logged
- **Determinism**: Same inputs always produce same outputs
- **Replayability**: Complete workflow can be replayed from audit logs

## ✨ Key Features

- ✅ **Cryptographic Authenticity**: Ed25519 signatures on all messages
- ✅ **Deterministic Replay**: Full workflow reproduction from audit logs
- ✅ **Policy Enforcement**: Validation of all envelopes before processing
- ✅ **Consensus Mechanism**: At-most-once DECIDE per NEED via Redis
- ✅ **Content-Addressable Storage**: SHA256-based artifact storage
- ✅ **Lamport Clocks**: Causal ordering of events
- ✅ **CRDT Plan Store**: Conflict-free task state management

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- NATS Server
- Redis Server
- Docker (optional, for services)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/agent-swarm.git
cd agent-swarm
```

2. **Create virtual environment**
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Start infrastructure services**
```bash
docker-compose up -d
# Or manually:
# nats-server -js
# redis-server
```

5. **Generate signing keys**
```bash
python3 -c "from src.crypto import generate_keypair; generate_keypair()"
```

### Running the E2E Demo

The easiest way to see CAN Swarm in action:

```bash
.venv/bin/python demo/e2e_flow.py
```

This will:
1. Start the Coordinator, Planner, Worker, and Verifier agents
2. Publish a NEED message
3. Complete the full NEED→PROPOSE→CLAIM→COMMIT→ATTEST→FINALIZE workflow
4. Verify the task reached FINAL state
5. Clean up all processes

Expected output:
```
============================================================
CAN Swarm End-to-End Demo
============================================================

[1/5] Starting Coordinator...
[2/5] Starting agents (Planner, Worker, Verifier)...
[3/5] Publishing NEED message...
✓ Published NEED to thread.xxx.need

[4/5] Waiting for agents to process (15 seconds)...
[5/5] Checking results...
✓ Found 1 FINALIZED task(s)
✓ SUCCESS: Flow completed to FINALIZE

============================================================
✓ E2E DEMO PASSED
============================================================
```

## 📖 Documentation

- **[API Reference](docs/API.md)** - Detailed module and function documentation
- **[Architecture](docs/ARCHITECTURE.md)** - System design and data flow diagrams
- **[Implementation Roadmap](IMPLEMENTATION_ROADMAP.md)** - Phase-by-phase development guide

## 🏗️ Architecture Overview

```
┌─────────────┐
│    NEED     │  User publishes a task request
└──────┬──────┘
       │
       v
┌─────────────┐
│  PLANNER    │  Creates execution proposal
└──────┬──────┘
       │
       v
┌─────────────┐
│   WORKER    │  Claims → Executes → Commits result
└──────┬──────┘
       │
       v
┌─────────────┐
│  VERIFIER   │  Validates → Attests → Finalizes
└──────┬──────┘
       │
       v
┌─────────────┐
│  FINALIZE   │  Task marked as FINAL in Plan Store
└─────────────┘
```

All communication flows through:
- **NATS JetStream**: Message bus
- **Signed Audit Log**: Cryptographic event trail
- **Plan Store**: SQLite CRDT for task state
- **Consensus**: Redis for DECIDE uniqueness
- **CAS**: SHA256-addressed artifact storage

## 🧪 Testing

### Run All Tests
```bash
.venv/bin/pytest tests/ -v
```

### Run Property Tests
```bash
.venv/bin/pytest tests/test_properties.py -v
```

Property tests verify:
- **P1**: Single DECIDE (consensus uniqueness)
- **P2**: Deterministic replay
- **P3**: Lamport ordering
- **P4**: Policy enforcement

### Deterministic Replay
```bash
# Get thread ID from E2E demo or logs
.venv/bin/python tools/replay.py <thread-id>
```

## 📦 Project Structure

```
agent-swarm/
├── src/                 # Core framework
│   ├── crypto.py       # Ed25519 signing & verification
│   ├── audit.py        # Signed audit logging
│   ├── bus.py          # NATS message bus
│   ├── envelope.py     # Message envelope creation
│   ├── lamport.py      # Lamport clock
│   ├── policy.py       # Validation rules
│   ├── cas.py          # Content-addressable storage
│   ├── plan_store.py   # CRDT task state
│   ├── consensus.py    # Redis-based DECIDE
│   ├── agent.py        # Base agent class
│   ├── coordinator.py  # Central coordinator
│   ├── verbs.py        # Message dispatcher
│   └── handlers/       # Verb handlers (NEED, PROPOSE, etc.)
├── agents/             # Agent implementations
│   ├── planner.py     # Proposal generation
│   ├── worker.py      # Task execution
│   └── verifier.py    # Result validation
├── demo/              # Demo scripts
│   ├── e2e_flow.py   # Automated full workflow
│   ├── start_coordinator.py
│   ├── publish_need.py
│   └── check_finalize.py
├── tools/             # Utilities
│   ├── replay.py     # Deterministic replay
│   └── cleanup_nats.py
├── tests/            # Test suite
│   └── test_properties.py  # Property-based tests
└── docs/             # Documentation
    ├── API.md
    └── ARCHITECTURE.md
```

## ✅ Implementation Status

### Phase 0: Foundation (Complete ✓)
- ✅ NATS JetStream setup
- ✅ Ed25519 key generation
- ✅ Basic publisher/subscriber

### Phase 1: Core Infrastructure (Complete ✓)
- ✅ Signed audit logging
- ✅ Message bus abstraction
- ✅ Cryptographic verification

### Phase 2: Coordination Layer (Complete ✓)
- ✅ Envelope schema
- ✅ Lamport clocks
- ✅ Policy engine
- ✅ Plan Store (SQLite CRDT)
- ✅ Consensus adapter (Redis)
- ✅ All verb handlers

### Phase 3: Agent Implementation (Complete ✓)
- ✅ Base agent framework
- ✅ Planner agent
- ✅ Worker agent
- ✅ Verifier agent
- ✅ Coordinator script

### Phase 4: Integration & Testing (Complete ✓)
- ✅ E2E demo
- ✅ Deterministic replay tool
- ✅ Property tests (10/10 passing)

### Phase 5: Documentation (Complete ✓)
- ✅ README update
- ✅ API documentation
- ✅ Architecture diagrams
- ✅ Demo walkthrough

## 🔬 Example Usage

### Manual Workflow

```bash
# Terminal 1: Start Coordinator
.venv/bin/python demo/start_coordinator.py

# Terminal 2: Start Planner
.venv/bin/python agents/planner.py

# Terminal 3: Start Worker
.venv/bin/python agents/worker.py

# Terminal 4: Start Verifier
.venv/bin/python agents/verifier.py

# Terminal 5: Publish a NEED
.venv/bin/python demo/publish_need.py

# Terminal 6: Check results
.venv/bin/python demo/check_finalize.py
```

## 🛠️ Development

### Running Individual Components

```bash
# Start NATS
nats-server -js

# Start Redis
redis-server

# Clean NATS consumers (between test runs)
.venv/bin/python tools/cleanup_nats.py

# Verify audit log signatures
.venv/bin/python tools/verify_signatures.py
```

## 🎓 Learn More

- **CAN Swarm Vision**: See the [original README](README.md) for the long-term vision
- **Implementation Details**: Check [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md)
- **Demo Walkthrough**: Step-by-step guide in [docs/DEMO.md](docs/DEMO.md)

## 📄 License

MIT License - see [LICENSE](LICENSE) for details

## 🤝 Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📧 Contact

For questions or feedback, please open an issue on GitHub.

---

**Status**: v1 PoC Complete ✨
**Last Updated**: 2025-11-24