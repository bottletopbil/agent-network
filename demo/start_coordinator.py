"""
Start Coordinator: runs the central coordinator with all handlers.

This script:
- Initializes the PlanStore and ConsensusAdapter
- Registers all verb handlers (NEED, PROPOSE, CLAIM, COMMIT, ATTEST, DECIDE, FINALIZE)
- Subscribes to all thread messages
- Routes messages to handlers to update state
"""

import sys
import os
import asyncio

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from coordinator import Coordinator

async def main():
    print("=" * 60)
    print("Starting Coordinator")
    print("=" * 60)
    
    # Initialize coordinator
    # Uses default paths: .state/plan.db and localhost redis
    coord = Coordinator()
    
    # Run indefinitely
    await coord.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCoordinator stopped.")
