"""
NEED Handler: initiates a new task request with auction.
"""

import uuid
import asyncio
from plan_store import PlanStore, PlanOp, OpType
from verbs import DISPATCHER
import time

plan_store: PlanStore = None  # Injected at startup
auction_manager = None  # Injected at startup

async def handle_need(envelope: dict):
    """
    Process NEED envelope with auction:
    1. Create task in plan store
    2. Start auction
    3. Wait for bid window
    4. Close auction and select winner
    5. Emit DECIDE if winner exists
    """
    thread_id = envelope["thread_id"]
    payload = envelope["payload"]
    
    task_id = str(uuid.uuid4())
    
    # Add task to plan
    op = PlanOp(
        op_id=str(uuid.uuid4()),
        thread_id=thread_id,
        lamport=envelope["lamport"],
        actor_id=envelope["sender_pk_b64"],
        op_type=OpType.ADD_TASK,
        task_id=task_id,
        payload={
            "type": payload.get("task_type", "generic"),
            "requires": payload.get("requires", []),
            "produces": payload.get("produces", [])
        },
        timestamp_ns=time.time_ns()
    )
    
    await plan_store.append_op(op)
    print(f"[NEED] Created task {task_id} in thread {thread_id}")
    
    # Start auction if auction_manager available
    if auction_manager:
        budget = payload.get("budget", 1000.0)
        auction = auction_manager.start_auction(task_id, budget)
        
        bid_window = auction_manager.config.bid_window if hasattr(auction_manager, 'config') else 30
        print(f"[NEED] Started auction for task {task_id} (budget: {budget}, window: {bid_window}s)")
        
        # Wait for bid window
        await asyncio.sleep(bid_window)
        
        # Close auction and get winner
        winner = auction_manager.close_auction(task_id)
        
        if winner:
            print(f"[NEED] Auction winner: {winner['agent_id']} (cost: {winner['cost']}, eta: {winner['eta']})")
            # Future: Emit DECIDE message with winner
        else:
            print(f"[NEED] No bids received for task {task_id}")
            auction_manager.timeout_auction(task_id)
    else:
        print(f"[NEED] No auction manager configured, task created without auction")

# Register with dispatcher
DISPATCHER.register("NEED", handle_need)
