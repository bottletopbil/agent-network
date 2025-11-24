"""
End-to-end demo: NEED → PROPOSE → CLAIM → COMMIT → ATTEST → FINALIZE

Runs all agents in separate processes and orchestrates the flow.
"""

import subprocess
import time
import sys
import os

def main():
    print("=" * 60)
    print("CAN Swarm End-to-End Demo")
    print("=" * 60)
    
    processes = []
    
    try:
        # 1. Start Coordinator
        print("\n[1/5] Starting Coordinator...")
        env = os.environ.copy()
        if os.path.exists(".env"):
            # Load environment variables from .env file
            with open(".env") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        env[key] = value
        
        coordinator = subprocess.Popen(
            [".venv/bin/python", "-u", "demo/start_coordinator.py"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        processes.append(("Coordinator", coordinator))
        time.sleep(2)
        
        # 2. Start agents in background
        print("[2/5] Starting agents (Planner, Worker, Verifier)...")
        
        planner = subprocess.Popen(
            [".venv/bin/python", "-u", "agents/planner.py"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        processes.append(("Planner", planner))
        
        worker = subprocess.Popen(
            [".venv/bin/python", "-u", "agents/worker.py"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        processes.append(("Worker", worker))
        
        verifier = subprocess.Popen(
            [".venv/bin/python", "-u", "agents/verifier.py"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        processes.append(("Verifier", verifier))
        
        # Let agents connect
        time.sleep(3)
        
        # 3. Publish NEED
        print("[3/5] Publishing NEED message...")
        result = subprocess.run(
            [".venv/bin/python", "demo/publish_need.py"],
            env=env,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"✗ Failed to publish NEED: {result.stderr}")
            return 1
        
        # 4. Wait for processing
        print("[4/5] Waiting for agents to process (15 seconds)...")
        time.sleep(15)
        
        # 5. Check final state
        print("[5/5] Checking results...")
        result = subprocess.run(
            [".venv/bin/python", "demo/check_finalize.py"],
            capture_output=True,
            text=True
        )
        print(result.stdout)
        
        if result.returncode == 0:
            print("\n" + "=" * 60)
            print("✓ E2E DEMO PASSED")
            print("=" * 60)
            return 0
        else:
            print("\n" + "=" * 60)
            print("✗ E2E DEMO FAILED")
            print("=" * 60)
            return 1
            
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        return 1
        
    finally:
        # Cleanup all processes
        print("\nCleaning up processes...")
        for name, process in processes:
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"  ✓ Stopped {name}")
            except Exception as e:
                print(f"  ✗ Error stopping {name}: {e}")
                try:
                    process.kill()
                except:
                    pass

if __name__ == "__main__":
    sys.exit(main())
