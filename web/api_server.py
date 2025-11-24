"""
CAN Swarm Investor Demo - API Server

Flask REST API providing real-time data for the investor dashboard.
Serves system status, workflow state, agent activity, metrics, and audit logs.
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import sqlite3
import json
import subprocess
import os
import time
from pathlib import Path
from datetime import datetime
import threading

app = Flask(__name__, static_folder='.')
CORS(app)

# Configuration
PROJECT_ROOT = Path(__file__).parent.parent
STATE_DB = PROJECT_ROOT / '.state' / 'plan.db'
AUDIT_LOG = PROJECT_ROOT / 'logs' / 'swarm.jsonl'

# In-memory demo state
demo_state = {
    'running': False,
    'thread_id': None,
    'started_at': None,
    'process': None
}

def get_docker_status():
    """Check if Docker containers are running"""
    try:
        result = subprocess.run(
            ['docker', 'ps', '--filter', 'name=nats', '--filter', 'name=redis', '--format', '{{.Names}}:{{.Status}}'],
            capture_output=True, text=True, timeout=5
        )
        containers = {}
        for line in result.stdout.strip().split('\n'):
            if ':' in line:
                name, status = line.split(':', 1)
                containers[name] = 'running' if 'Up' in status else 'stopped'
        return containers
    except:
        return {}

def get_plan_store_stats():
    """Get statistics from plan store"""
    if not STATE_DB.exists():
        return {}
    
    try:
        conn = sqlite3.connect(str(STATE_DB))
        cursor = conn.cursor()
        
        # Total tasks
        cursor.execute("SELECT COUNT(*) FROM tasks")
        total_tasks = cursor.fetchone()[0]
        
        # Tasks by state
        cursor.execute("SELECT state, COUNT(*) FROM tasks GROUP BY state")
        states = dict(cursor.fetchall())
        
        # Total ops
        cursor.execute("SELECT COUNT(*) FROM ops")
        total_ops = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_tasks': total_tasks,
            'states': states,
            'total_ops': total_ops
        }
    except Exception as e:
        return {'error': str(e)}

def get_recent_threads(limit=10):
    """Get recent thread IDs from audit log"""
    if not AUDIT_LOG.exists():
        return []
    
    threads = {}
    try:
        with open(AUDIT_LOG, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        event = json.loads(line)
                        thread_id = event.get('thread_id')
                        if thread_id and thread_id not in threads:
                            threads[thread_id] = {
                                'thread_id': thread_id,
                                'started_at': event.get('timestamp_ns', 0) / 1e9,
                                'event_count': 0
                            }
                        if thread_id:
                            threads[thread_id]['event_count'] += 1
                    except:
                        continue
        
        # Sort by started_at descending
        sorted_threads = sorted(threads.values(), key=lambda x: x['started_at'], reverse=True)
        return sorted_threads[:limit]
    except:
        return []

def get_workflow_for_thread(thread_id):
    """Get workflow state for a specific thread"""
    if not STATE_DB.exists():
        return None
    
    try:
        conn = sqlite3.connect(str(STATE_DB))
        cursor = conn.cursor()
        
        # Get task for thread
        cursor.execute("SELECT task_id, state, last_lamport FROM tasks WHERE thread_id = ? ORDER BY last_lamport DESC LIMIT 1", (thread_id,))
        row = cursor.fetchone()
        
        if row:
            task_id, state, lamport = row
            conn.close()
            
            # Map state to workflow stage
            stage_order = ['DRAFT', 'DECIDED', 'VERIFIED', 'FINAL']
            current_stage = state if state in stage_order else 'DRAFT'
            stage_index = stage_order.index(current_stage)
            
            return {
                'thread_id': thread_id,
                'task_id': task_id,
                'current_state': state,
                'current_stage': current_stage,
                'stage_index': stage_index,
                'total_stages': len(stage_order),
                'lamport': lamport,
                'completed': state == 'FINAL'
            }
        
        conn.close()
        return None
    except Exception as e:
        return {'error': str(e)}

def get_audit_entries(thread_id=None, limit=50):
    """Get audit log entries"""
    if not AUDIT_LOG.exists():
        return []
    
    entries = []
    try:
        with open(AUDIT_LOG, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        event = json.loads(line)
                        if thread_id is None or event.get('thread_id') == thread_id:
                            entries.append({
                                'timestamp': event.get('timestamp_ns', 0) / 1e9,
                                'thread_id': event.get('thread_id'),
                                'kind': event.get('kind'),
                                'subject': event.get('subject'),
                                'has_signature': 'sig_b64' in event,
                                'payload_preview': str(event.get('payload', {}))[:100]
                            })
                    except:
                        continue
        
        # Sort by timestamp descending, limit
        entries.sort(key=lambda x: x['timestamp'], reverse=True)
        return entries[:limit]
    except:
        return []

# API Routes

@app.route('/')
def index():
    """Serve the main dashboard"""
    return send_from_directory('.', 'index.html')

@app.route('/styles.css')
def styles():
    """Serve CSS file"""
    return send_from_directory('.', 'styles.css', mimetype='text/css')

@app.route('/app.js')
def app_js():
    """Serve JavaScript file"""
    return send_from_directory('.', 'app.js', mimetype='application/javascript')

@app.route('/api/status')
def api_status():
    """Get overall system status"""
    containers = get_docker_status()
    plan_stats = get_plan_store_stats()
    
    return jsonify({
        'status': 'online',
        'timestamp': time.time(),
        'infrastructure': {
            'nats': containers.get('nats', 'unknown'),
            'redis': containers.get('redis', 'unknown'),
        },
        'plan_store': plan_stats,
        'demo_running': demo_state['running']
    })

@app.route('/api/threads')
def api_threads():
    """Get recent threads"""
    threads = get_recent_threads(limit=20)
    return jsonify({'threads': threads})

@app.route('/api/workflow/<thread_id>')
def api_workflow(thread_id):
    """Get workflow state for a thread"""
    workflow = get_workflow_for_thread(thread_id)
    if workflow:
        return jsonify(workflow)
    else:
        return jsonify({'error': 'Thread not found'}), 404

@app.route('/api/agents')
def api_agents():
    """Get agent states (simulated)"""
    # In real implementation, would query agent health/activity
    # For demo, return mock data based on recent activity
    
    recent_threads = get_recent_threads(limit=1)
    has_recent_activity = len(recent_threads) > 0 and (time.time() - recent_threads[0]['started_at']) < 300
    
    agents = [
        {
            'id': 'planner',
            'name': 'Planner',
            'type': 'planning',
            'status': 'active' if has_recent_activity else 'idle',
            'tasks_handled': 0,
            'uptime': '100%'
        },
        {
            'id': 'worker',
            'name': 'Worker',
            'type': 'execution',
            'status': 'active' if has_recent_activity else 'idle',
            'tasks_handled': 0,
            'uptime': '100%'
        },
        {
            'id': 'verifier',
            'name': 'Verifier',
            'type': 'verification',
            'status': 'active' if has_recent_activity else 'idle',
            'tasks_handled': 0,
            'uptime': '100%'
        }
    ]
    
    return jsonify({'agents': agents})

@app.route('/api/metrics')
def api_metrics():
    """Get system metrics"""
    plan_stats = get_plan_store_stats()
    threads = get_recent_threads()
    
    total_tasks = plan_stats.get('total_tasks', 0)
    final_tasks = plan_stats.get('states', {}).get('FINAL', 0)
    success_rate = (final_tasks / total_tasks * 100) if total_tasks > 0 else 0
    
    return jsonify({
        'total_tasks': total_tasks,
        'completed_tasks': final_tasks,
        'success_rate': round(success_rate, 1),
        'active_threads': len(threads),
        'total_ops': plan_stats.get('total_ops', 0)
    })

@app.route('/api/audit')
def api_audit():
    """Get audit log entries"""
    thread_id = request.args.get('thread_id')
    limit = int(request.args.get('limit', 50))
    
    entries = get_audit_entries(thread_id=thread_id, limit=limit)
    return jsonify({'entries': entries, 'total': len(entries)})

@app.route('/api/demo/start', methods=['POST'])
def api_demo_start():
    """Start E2E demo"""
    global demo_state
    
    if demo_state['running']:
        return jsonify({'error': 'Demo already running'}), 400
    
    try:
        # Start E2E demo in background
        demo_state['running'] = True
        demo_state['started_at'] = time.time()
        
        # Run demo asynchronously
        def run_demo():
            global demo_state
            try:
                result = subprocess.run(
                    ['.venv/bin/python', 'demo/e2e_flow.py'],
                    capture_output=True,
                    text=True,
                    cwd=str(PROJECT_ROOT),
                    timeout=60
                )
                
                # Extract thread ID from output
                for line in result.stdout.split('\n'):
                    if 'Thread ID:' in line:
                        demo_state['thread_id'] = line.split('Thread ID:')[1].strip()
                        break
                
            except Exception as e:
                print(f"Demo error: {e}")
            finally:
                demo_state['running'] = False
        
        thread = threading.Thread(target=run_demo)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'started',
            'message': 'E2E demo initiated'
        })
    
    except Exception as e:
        demo_state['running'] = False
        return jsonify({'error': str(e)}), 500

@app.route('/api/demo/status')
def api_demo_status():
    """Get demo execution status"""
    return jsonify({
        'running': demo_state['running'],
        'thread_id': demo_state['thread_id'],
        'started_at': demo_state['started_at'],
        'duration': time.time() - demo_state['started_at'] if demo_state['started_at'] else None
    })

if __name__ == '__main__':
    print("🐝 CAN Swarm Investor Demo API Server")
    print(f"📊 Dashboard: http://localhost:8080")
    print(f"🔌 API: http://localhost:8080/api/status")
    print()
    app.run(host='0.0.0.0', port=8080, debug=True, threaded=True)
