"""
Check if any tasks have reached FINALIZE state.

Queries the plan store and reports success/failure.
"""

import sys
from pathlib import Path

sys.path.append("src")
from plan_store import PlanStore, TaskState

def main():
    print("=" * 60)
    print("Checking for FINALIZED tasks...")
    print("=" * 60)
    
    # Open plan store
    plan_store_path = Path(".state/plan.db")
    if not plan_store_path.exists():
        print("✗ Plan store not found")
        return 1
    
    plan_store = PlanStore(plan_store_path)
    
    # Get all tasks (we'll query via SQL directly for simplicity)
    conn = plan_store.conn
    cursor = conn.execute("""
        SELECT task_id, state, last_lamport
        FROM tasks
        WHERE state = ?
        ORDER BY last_lamport DESC
        LIMIT 10
    """, (TaskState.FINAL.value,))
    
    finalized_tasks = cursor.fetchall()
    
    if finalized_tasks:
        print(f"\n✓ Found {len(finalized_tasks)} FINALIZED task(s):")
        for task_id, state, last_lamport in finalized_tasks:
            print(f"  - Task {task_id[:8]}... (state: {state}, lamport: {last_lamport})")
        print("\n✓ SUCCESS: Flow completed to FINALIZE")
        return 0
    else:
        print("\n✗ FAILURE: No tasks in FINAL state found")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        sys.exit(1)
