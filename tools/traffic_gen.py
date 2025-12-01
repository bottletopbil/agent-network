
import sys
import os
import time
import random
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from observability.metrics import metrics_collector

class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; version=0.0.4')
            self.end_headers()
            self.wfile.write(metrics_collector.get_metrics())
        else:
            self.send_response(404)
            self.end_headers()

def run_server():
    print("Starting metrics server on port 8000...")
    httpd = HTTPServer(('0.0.0.0', 8000), MetricsHandler)
    httpd.serve_forever()

def simulate_traffic():
    print("Simulating traffic...")
    
    agents = ["planner", "worker", "verifier"]
    tasks = ["research", "code", "review"]
    
    # Set initial state
    metrics_collector.set_active_agents("planner", 3)
    metrics_collector.set_active_agents("worker", 5)
    metrics_collector.set_active_agents("verifier", 10)
    
    while True:
        # Simulate message traffic
        kind = random.choice(["NEED", "BID", "DECIDE", "FINALIZE"])
        subject = f"thread.{random.randint(1000, 9999)}"
        metrics_collector.record_message_published(kind, subject)
        metrics_collector.record_message_received(kind, subject)
        
        # Simulate latencies
        if random.random() < 0.1:
            # Occasional spike
            latency = random.uniform(0.5, 2.0)
        else:
            latency = random.uniform(0.01, 0.1)
            
        # We can't easily inject into the histograms directly without using the decorators or context managers
        # But we can use the private methods or just rely on the fact that we are importing the objects
        # Actually metrics_collector doesn't expose the histograms directly in the public API I saw earlier
        # Let's check src/observability/metrics.py again to see if we can import the histograms directly
        # Yes, we can import them from the module
        
        # Simulate tasks
        if random.random() < 0.2:
            task = random.choice(tasks)
            metrics_collector.record_task_created(task)
            if random.random() < 0.8:
                metrics_collector.record_task_completed(task, "success")
            else:
                metrics_collector.record_task_completed(task, "failed")
                metrics_collector.record_agent_error("agent-1", "timeout")
        
        time.sleep(random.uniform(0.1, 0.5))

if __name__ == "__main__":
    # Start server in background thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Run traffic simulation
    try:
        simulate_traffic()
    except KeyboardInterrupt:
        print("\nStopping traffic generation...")
