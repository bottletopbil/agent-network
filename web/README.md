# CAN Swarm Investor Demo - Web Interface

Professional real-time dashboard for showcasing CAN Swarm v1 PoC to potential investors.

## Features

- **Live Workflow Visualization** - Animated NEED → FINALIZE pipeline
- **Agent Monitoring** - Real-time status of all agents (Planner, Worker, Verifier)
- **System Metrics** - Tasks completed, success rate, operations count
- **Cryptographic Audit Trail** - Live-updated signed event log
- **Interactive Demo Controls** - One-click E2E demo trigger
- **Glassmorphism Design** - Modern, professional UI with vibrant gradients

## Quick Start

### 1. Install Dependencies

```bash
cd /Users/rileyhicks/Dev/Real\ Projects/agent-swarm
source .venv/bin/activate
pip install flask==3.0.0 flask-cors==4.0.0
```

### 2. Ensure Infrastructure is Running

```bash
# Start NATS and Redis
docker-compose up -d

# Verify services
docker ps
```

### 3. Start the API Server

```bash
cd web
python api_server.py
```

Expected output:
```
🐝 CAN Swarm Investor Demo API Server
📊 Dashboard: http://localhost:5000
🔌 API: http://localhost:5000/api/status
```

### 4. Open the Dashboard

```bash
# Open in browser
open http://localhost:5000
```

Or navigate to: **http://localhost:5000**

## Using the Dashboard

### Viewing System Status

The hero section shows:
- **System Status** - Online/Offline indicator
- **Service Health** - NATS and Redis status

### Workflow Visualization

- **Blue Gradient** = Active stage
- **Green Gradient** = Completed stage
- **Gray** = Pending stage

Stages animate in real-time as tasks progress through:
NEED → PROPOSE → CLAIM → COMMIT → ATTEST → FINALIZE

### Starting a Demo

1. Click **"Start E2E Demo"** button
2. Watch workflow animate through all stages
3. Observe agents activate and process tasks
4. View audit entries stream in real-time
5. Metrics update with new task completion

### Viewing Audit Logs

- **Filter by Thread** - Select specific thread from dropdown
- **Signature Verification** - Green ✓ indicates cryptographically signed events
- **Timestamps** - All events timestamped for causal ordering

### Agent Monitoring

Each agent card shows:
- **Status** - Idle/Active with pulsing indicator
- **Type** - Planning/Execution/Verification
- **Uptime** - Availability percentage

## API Endpoints

All endpoints served from `http://localhost:5000/api/`:

### GET /status
System health and infrastructure status
```json
{
  "status": "online",
  "infrastructure": {
    "nats": "running",
    "redis": "running"
  },
  "plan_store": { ... },
  "demo_running": false
}
```

### GET /threads
Recent thread IDs with event counts
```json
{
  "threads": [
    {
      "thread_id": "abc-123...",
      "started_at": 1700000000,
      "event_count": 15
    }
  ]
}
```

### GET /workflow/:thread_id
Workflow state for specific thread
```json
{
  "thread_id": "abc-123...",
  "current_state": "FINAL",
  "current_stage": "finalize",
  "stage_index": 5,
  "completed": true
}
```

### GET /agents
Agent states and activity
```json
{
  "agents": [
    {
      "id": "planner",
      "name": "Planner",
      "status": "active",
      "type": "planning"
    }
  ]
}
```

### GET /metrics
System-wide metrics
```json
{
  "total_tasks": 42,
  "completed_tasks": 40,
  "success_rate": 95.2,
  "total_ops": 256
}
```

### GET /audit
Audit log entries
Query params: `thread_id` (optional), `limit` (default: 50)
```json
{
  "entries": [
    {
      "timestamp": 1700000000,
      "thread_id": "abc-123...",
      "kind": "BUS.PUBLISH",
      "has_signature": true
    }
  ]
}
```

### POST /demo/start
Trigger E2E demo
```json
{
  "status": "started",
  "message": "E2E demo initiated"
}
```

### GET /demo/status
Get demo execution status
```json
{
  "running": true,
  "thread_id": "abc-123...",
  "started_at": 1700000000
}
```

## Customization

### Update Interval

Change polling frequency in `app.js`:
```javascript
const UPDATE_INTERVAL = 2000; // milliseconds (default: 2 seconds)
```

### Port Configuration

Change API server port in `api_server.py`:
```python
app.run(host='0.0.0.0', port=5000, debug=True) # Default: 5000
```

Also update in `app.js`:
```javascript
const API_BASE = 'http://localhost:5000/api';
```

### Color Scheme

Modify color gradients in `styles.css`:
```css
:root {
    --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    --secondary-gradient: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
    /* ... */
}
```

## Troubleshooting

### "Cannot connect to API"

**Issue**: Dashboard shows errors or data not loading

**Solutions**:
1. Verify API server is running: `curl http://localhost:5000/api/status`
2. Check for CORS errors in browser console (F12)
3. Ensure Flask/flask-cors installed: `pip list | grep -i flask`

### "No workflows showing"

**Issue**: Workflow section shows "No active workflow"

**Solutions**:
1. Run E2E demo to generate data: `.venv/bin/python demo/e2e_flow.py`
2. Ensure `.state/plan.db` exists
3. Check audit log exists: `ls -la logs/swarm.jsonl`

### "Infrastructure showing offline"

**Issue**: NATS/Redis showing as not running

**Solutions**:
1. Start Docker services: `docker-compose up -d`
2. Verify containers: `docker ps`
3. Check logs: `docker-compose logs nats redis`

### "Demo won't start"

**Issue**: "Start Demo" button doesn't trigger workflow

**Solutions**:
1. Check only one demo runs at a time (wait for current to finish)
2. Verify infrastructure is running
3. Check API server logs for errors
4. Ensure `.venv` is activated and demo scripts are executable

## Architecture

```
┌─────────────┐
│   Browser   │
│  (index.html│
│   app.js)   │
└──────┬──────┘
       │ HTTP (polling every 2s)
       ▼
┌─────────────┐
│ Flask API   │
│ (port 5000) │
└──────┬──────┘
       │
       ├─── Reads plan.db (SQLite)
       ├─── Reads swarm.jsonl (audit log)
       ├─── Checks Docker (ps)
       └─── Triggers demo/e2e_flow.py
```

## For Investors

This dashboard demonstrates:

1. **Real-time Multi-Agent Coordination**
   - No central orchestrator
   - Agents self-organize via signed messages

2. **Cryptographic Auditability**
   - Every event Ed25519 signed
   - Complete audit trail for compliance

3. **Deterministic Replay**
   - Workflow reproducible from logs
   - Enables debugging and verification

4. **Policy Enforcement**
   - Default-deny security model
   - Validated at multiple gates

5. **Production-Ready Foundation**
   - 63/63 tests passing
   - Property tests verify invariants (P1-P4)
   - Ready for scale-out to full vision

---

**Questions?** See [docs/DEMO.md](../docs/DEMO.md) for full documentation or [ARCHITECTURE.md](../docs/ARCHITECTURE.md) for system design details.
