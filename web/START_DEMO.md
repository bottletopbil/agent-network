# Quick Start Guide - Investor Demo

## ✅ Fixed Port Issue
Changed from port 5000 → **8080** (avoids macOS AirPlay conflict)

## 🚀 Commands to Run

### Step 1: Navigate to project
```bash
cd "/Users/rileyhicks/Dev/Real Projects/agent-swarm"
```

### Step 2: Activate virtual environment
```bash
source .venv/bin/activate
```

### Step 3: Ensure Docker services running
```bash
docker-compose up -d
```

### Step 4: Start the API server
```bash
cd web
python api_server.py
```

You should see:
```
🐝 CAN Swarm Investor Demo API Server
📊 Dashboard: http://localhost:8080
🔌 API: http://localhost:8080/api/status

 * Serving Flask app 'api_server'
 * Debug mode: on
WARNING: This is a development server...
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:8080
 * Running on http://192.168.x.x:8080
```

### Step 5: Open dashboard in browser
```bash
open http://localhost:8080
```

## 🎨 Verify CSS is Working

When the page loads, you should see:
- **Dark background** (not white)
- **Purple gradient header** with 🐝 logo
- **Glassmorphic cards** (semi-transparent with blur effect)
- **Green pulsing dot** for "System Online"
- **Vibrant colored buttons** (purple gradient on "Start Demo")

If you see plain white background or no colors:
- Check browser console (F12) for errors
- Hard refresh: `Cmd+Shift+R`

## 🧪 Test the Demo

1. Click **"Start E2E Demo"** button
2. Watch workflow stages animate (should turn blue then green)
3. Audit log should stream events at bottom
4. Metrics should update with numbers

## 🛑 Stop the Server

Press `Ctrl+C` in the terminal where api_server.py is running

## ❓ Troubleshooting

**"Address already in use" on port 8080**
```bash
# Kill process using port 8080
lsof -ti:8080 | xargs kill -9

# Then restart
python api_server.py
```

**CSS not loading**
- Check that `styles.css` exists in `web/` directory
- Hard refresh browser: `Cmd+Shift+R`
- Check Flask output shows: `GET / 200` and `GET /styles.css 200`

**No data showing**
- Run a demo first: `cd .. && .venv/bin/python demo/e2e_flow.py`
- This creates data in `.state/plan.db` and `logs/swarm.jsonl`
