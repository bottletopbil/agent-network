# Contributing to CAN Swarm

Thank you for your interest in contributing to CAN Swarm! This document provides guidelines and instructions for contributing to the project.

---

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Code Style Guidelines](#code-style-guidelines)
- [Adding New Verbs](#adding-new-verbs)
- [Adding New Agent Types](#adding-new-agent-types)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Documentation](#documentation)

---

## 🤝 Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Prioritize system correctness and auditability
- Document all design decisions

---

## 🚀 Getting Started

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR_USERNAME/agent-swarm.git
cd agent-swarm
git remote add upstream https://github.com/original/agent-swarm.git
```

### 2. Set Up Development Environment

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt  # (if available)

# Generate keys
python3 -c "from src.keys import *"

# Start infrastructure
docker-compose up -d
```

### 3. Run Tests

```bash
# Ensure everything works
pytest tests/ -v

# Run E2E demo
.venv/bin/python demo/e2e_flow.py
```

---

## 🔄 Development Workflow

### Branch Naming

- `feature/` - New features (e.g., `feature/add-retry-verb`)
- `fix/` - Bug fixes (e.g., `fix/lamport-race-condition`)
- `docs/` - Documentation (e.g., `docs/improve-api-reference`)
- `refactor/` - Code refactoring (e.g., `refactor/simplify-consensus`)

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `test`: Adding/updating tests
- `refactor`: Code refactoring
- `perf`: Performance improvement
- `chore`: Maintenance tasks

**Examples:**

```
feat(handlers): add RETRY verb for failed tasks

Implements exponential backoff retry mechanism for tasks
that fail verification.

Closes #42
```

```
fix(lamport): prevent race condition in concurrent ticks

Thread-safe Lamport clock now uses file-based locking
instead of in-memory counter.
```

---

## 📐 Code Style Guidelines

### Python Style

Follow [PEP 8](https://pep8.org/) with these specific guidelines:

#### Imports

```python
# Standard library
import json
import time
from pathlib import Path

# Third-party
import redis
from nacl.signing import SigningKey

# Local
from src.crypto import sign_record
from src.audit import log_event
```

#### Type Hints

Always use type hints for function signatures:

```python
from typing import Dict, List, Optional, Any

def handle_envelope(envelope: Dict[str, Any]) -> Optional[str]:
    """Process envelope and return thread ID if successful."""
    thread_id: str = envelope["thread_id"]
    return thread_id
```

#### Docstrings

Use Google-style docstrings:

```python
def validate_envelope(envelope: dict) -> bool:
    """
    Validate envelope against current policy.
    
    Args:
        envelope: Envelope dictionary with kind, payload, etc.
    
    Returns:
        True if envelope passes all policy checks.
    
    Raises:
        PolicyViolationError: If envelope violates policy.
    
    Example:
        >>> env = make_envelope("NEED", "thread-1", "pk", {"x": 1})
        >>> validate_envelope(env)
        True
    """
    ...
```

#### Error Handling

Be explicit about error cases:

```python
# Good: Specific exception
try:
    envelope = json.loads(msg.data)
except json.JSONDecodeError as e:
    log_event(thread_id, subject, "ERROR", {"msg": str(e)})
    return None

# Bad: Bare except
try:
    envelope = json.loads(msg.data)
except:  # Don't do this
    pass
```

#### Constants

Use uppercase for module-level constants:

```python
# Good
MAX_PAYLOAD_SIZE = 1048576  # 1MB
DEFAULT_TIMEOUT_MS = 5000

# Bad
maxPayloadSize = 1048576
default_timeout_ms = 5000
```

---

## ➕ Adding New Verbs

Verbs are the core message types in CAN Swarm. Follow this process to add a new verb.

### Step 1: Update Policy

Add the new verb to allowed kinds:

```python
# src/policy.py

ALLOWED_KINDS = {
    "NEED", "PROPOSE", "CLAIM", "COMMIT",
    "ATTEST", "DECIDE", "FINALIZE",
    "YIELD", "RELEASE",
    "RETRY",  # ← New verb
}

# Increment version
POLICY_RULES = {
    "version": 2,  # Was 1
    ...
}
```

### Step 2: Create Handler

Create `src/handlers/retry.py`:

```python
"""
RETRY Handler: allows agents to retry failed tasks.

Verb Structure:
{
  "kind": "RETRY",
  "thread_id": "...",
  "payload": {
    "task_id": "...",
    "original_commit_hash": "...",
    "reason": "verification_failed",
    "attempt": 2
  }
}
"""

import uuid
import time
from typing import Dict, Any
from src.plan_store import PlanStore, PlanOp, OpType
from src.verbs import DISPATCHER

async def handle_retry(envelope: Dict[str, Any]):
    """
    Handle RETRY verb.
    
    Args:
        envelope: Signed envelope with RETRY kind
    """
    payload = envelope["payload"]
    task_id = payload["task_id"]
    attempt = payload.get("attempt", 1)
    
    # Get plan store (injected by coordinator)
    plan_store: PlanStore = DISPATCHER.plan_store
    
    # Record retry attempt
    op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=envelope["thread_id"],
        lamport=envelope["lamport"],
        actor_id=envelope["sender_pk_b64"],
        op_type=OpType.ANNOTATE,
        task_id=task_id,
        payload={"retry_attempt": attempt, "reason": payload.get("reason")},
        timestamp_ns=time.time_ns()
    )
    
    plan_store.append_op(op)
    
    # TODO: Implement exponential backoff
    # TODO: Notify worker to re-execute

# Register handler
DISPATCHER.register("RETRY", handle_retry)
```

### Step 3: Add Tests

Create `tests/test_retry_handler.py`:

```python
import pytest
import tempfile
from pathlib import Path
from src.handlers.retry import handle_retry
from src.plan_store import PlanStore
from src.envelope import make_envelope, sign_envelope
from src.verbs import DISPATCHER

@pytest.fixture
def plan_store():
    db_path = Path(tempfile.mktemp())
    store = PlanStore(db_path)
    DISPATCHER.plan_store = store
    yield store
    db_path.unlink()

@pytest.mark.asyncio
async def test_retry_handler(plan_store):
    """Test RETRY handler records retry attempt"""
    env = make_envelope(
        kind="RETRY",
        thread_id="test-thread",
        sender_pk_b64="test-pk",
        payload={
            "task_id": "task-123",
            "attempt": 2,
            "reason": "timeout"
        }
    )
    signed = sign_envelope(env)
    
    await handle_retry(signed)
    
    # Verify retry was recorded
    ops = plan_store.get_ops_for_thread("test-thread")
    assert len(ops) == 1
    assert ops[0].payload["retry_attempt"] == 2
```

### Step 4: Update Documentation

Add to `docs/API.md`:

```markdown
## RETRY

Allows agents to retry failed tasks with exponential backoff.

**Payload:**
- `task_id`: Task to retry
- `original_commit_hash`: Hash of failed commit
- `reason`: Why retry is needed
- `attempt`: Retry attempt number (1-indexed)

**Example:**
```json
{
  "kind": "RETRY",
  "payload": {
    "task_id": "6282f4e4-...",
    "original_commit_hash": "abc123...",
    "reason": "verification_failed",
    "attempt": 2
  }
}
```
```

### Step 5: Update Workflow Diagram

Update `docs/ARCHITECTURE.md` to show where RETRY fits in the flow.

---

## 🤖 Adding New Agent Types

Agent types implement specific behaviors in the swarm.

### Step 1: Create Agent Class

Create `agents/scheduler.py`:

```python
"""
Scheduler Agent: assigns tasks based on agent capabilities.

Listens for: NEED messages
Publishes: ASSIGN messages (custom verb)
"""

import asyncio
import sys
import uuid
import base64

sys.path.append("src")
from agent import BaseAgent
from envelope import make_envelope, sign_envelope
from bus import publish_envelope
from crypto import load_verifier

class SchedulerAgent(BaseAgent):
    def __init__(self, agent_id: str):
        super().__init__(
            agent_id=agent_id,
            public_key_b64=base64.b64encode(bytes(load_verifier())).decode()
        )
        
        # Track agent capabilities
        self.agent_registry = {}
    
    async def on_envelope(self, envelope: dict):
        """Handle incoming envelopes"""
        kind = envelope.get("kind")
        
        if kind == "NEED":
            await self._handle_need(envelope)
        elif kind == "REGISTER":
            await self._handle_register(envelope)
    
    async def _handle_need(self, envelope: dict):
        """Assign NEED to best available agent"""
        need_payload = envelope["payload"]
        task_type = need_payload.get("task")
        
        # Find agent with matching capability
        best_agent = self._find_best_agent(task_type)
        
        if not best_agent:
            print(f"No agent available for task: {task_type}")
            return
        
        # Publish ASSIGN
        assign_env = make_envelope(
            kind="ASSIGN",
            thread_id=envelope["thread_id"],
            sender_pk_b64=self.public_key_b64,
            payload={
                "task_id": envelope["id"],
                "assigned_to": best_agent,
                "task_type": task_type
            }
        )
        
        signed = sign_envelope(assign_env)
        subject = f"thread.{envelope['thread_id']}.assign"
        
        await publish_envelope(envelope["thread_id"], subject, signed)
        print(f"✓ Assigned {task_type} to {best_agent}")
    
    async def _handle_register(self, envelope: dict):
        """Register agent capabilities"""
        agent_id = envelope["payload"]["agent_id"]
        capabilities = envelope["payload"]["capabilities"]
        
        self.agent_registry[agent_id] = capabilities
        print(f"✓ Registered {agent_id} with capabilities: {capabilities}")
    
    def _find_best_agent(self, task_type: str) -> str:
        """Find agent with matching capability"""
        for agent_id, capabilities in self.agent_registry.items():
            if task_type in capabilities:
                return agent_id
        return None

async def main():
    agent = SchedulerAgent(agent_id=f"scheduler-{uuid.uuid4()}")
    
    print(f"Scheduler agent started (ID: {agent.agent_id})")
    print("Subscribed to: thread.*.need, thread.*.register")
    
    # Subscribe to both NEED and REGISTER
    await asyncio.gather(
        agent.run(thread_id="*", subject="thread.*.need"),
        agent.run(thread_id="*", subject="thread.*.register")
    )

if __name__ == "__main__":
    asyncio.run(main())
```

### Step 2: Add Tests

```python
# tests/test_scheduler_agent.py
@pytest.mark.asyncio
async def test_scheduler_assigns_tasks():
    """Test scheduler assigns tasks to capable agents"""
    # ... test implementation
```

### Step 3: Document Agent

Add to `docs/API.md`:

```markdown
## Scheduler Agent

**Purpose**: Intelligently assigns tasks to agents based on capabilities.

**Subscribes to**: `thread.*.need`, `thread.*.register`
**Publishes**: `ASSIGN` envelopes

**Usage:**
```bash
.venv/bin/python agents/scheduler.py
```
```

---

## 🧪 Testing Requirements

All contributions must include appropriate tests.

### Test Categories

1. **Unit Tests** (`tests/test_*.py`): Test individual functions
2. **Integration Tests** (`tests/test_integration_*.py`): Test component interactions
3. **Property Tests** (`tests/test_properties.py`): Test system invariants (P1-P4)
4. **E2E Tests** (`demo/e2e_flow.py`): Test complete workflows

### Coverage Requirements

- **Minimum**: 80% code coverage
- **Critical paths**: 100% coverage (crypto, consensus, policy)

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_core.py -v

# With coverage
pytest tests/ --cov=src --cov-report=html

# Property tests only
pytest tests/test_properties.py -v
```

### Test Naming

```python
# Good: Descriptive test names
def test_lamport_clock_advances_monotonically():
    ...

def test_consensus_rejects_duplicate_decide():
    ...

# Bad: Vague names
def test_clock():
    ...

def test_consensus():
    ...
```

### Fixtures

Use pytest fixtures for common setup:

```python
@pytest.fixture
def temp_plan_store():
    """Temporary plan store for testing"""
    db_path = Path(tempfile.mktemp())
    store = PlanStore(db_path)
    yield store
    db_path.unlink()
```

---

## 🔀 Pull Request Process

### Before Submitting

- [ ] Code follows style guidelines
- [ ] All tests pass (`pytest tests/ -v`)
- [ ] E2E demo works (`.venv/bin/python demo/e2e_flow.py`)
- [ ] Documentation updated
- [ ] Commit messages follow conventions
- [ ] No merge conflicts with `main`

### PR Template

```markdown
## Description
Brief description of changes.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] E2E demo verified

## Checklist
- [ ] Code follows style guide
- [ ] Documentation updated
- [ ] Tests added/updated
- [ ] All tests pass

## Related Issues
Closes #123
```

### Review Process

1. **Automated Checks**: CI runs tests, linting
2. **Code Review**: At least one maintainer approval required
3. **Testing**: Reviewer runs E2E demo
4. **Merge**: Squash and merge to `main`

### CI/CD Pipeline

GitHub Actions runs:
- Linting (flake8, mypy)
- Unit tests
- Integration tests
- E2E demo
- Coverage report

---

## 📚 Documentation

### Documentation Standards

- **Code**: Inline docstrings (Google style)
- **APIs**: Update `docs/API.md`
- **Architecture**: Update `docs/ARCHITECTURE.md` for design changes
- **Examples**: Add to `examples/` if demonstrating new feature

### Documentation Checklist

When adding features:

- [ ] Docstrings for all public functions/classes
- [ ] API documentation updated
- [ ] Architecture diagrams updated (if needed)
- [ ] Example code provided
- [ ] README updated (if major feature)

---

## 🎯 Contribution Ideas

Looking for something to work on? Check these areas:

### Good First Issues
- Add more example scripts
- Improve error messages
- Add unit tests for uncovered code
- Fix typos in documentation

### Intermediate
- Implement new verbs (RETRY, CANCEL, DELEGATE)
- Add new agent types (Router, Aggregator, Monitor)
- Performance optimizations
- Better logging/observability

### Advanced
- v2 migration tools (see `docs/V2_MIGRATION.md`)
- Multi-tenancy support
- Policy engine improvements
- Distributed deployment guides

---

## 💬 Getting Help

- **Questions**: Open a discussion on GitHub
- **Bugs**: Open an issue with reproduction steps
- **Features**: Open an issue with use case description
- **Security**: Email security@example.com (do not open public issue)

---

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for contributing to CAN Swarm!** 🐝
