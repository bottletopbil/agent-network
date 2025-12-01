"""
Integration test for etcd consensus (DIST-001).

Validates that etcd provides distributed DECIDE consensus.
Requires etcd service to be running.
"""

import sys
from pathlib import Path
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def etcd_available():
    """Check if etcd is available and skip if not."""
    try:
        import etcd3
        client = etcd3.client(host='localhost', port=2379, timeout=2)
        # Try to connect
        client.status()
        return True
    except Exception:
        pytest.skip("etcd service not available")


def test_only_one_decide_succeeds(etcd_available):
    """
    Test that only one agent can DECIDE for the same need_id.
    
    Simulates distributed consensus where multiple agents try to DECIDE.
    """
    from consensus.raft_adapter import RaftConsensusAdapter
    
    adapter = RaftConsensusAdapter(etcd_host='localhost', etcd_port=2379)
    
    need_id = "test_need_123"
    agent1_decide = {"agent_id": "agent1", "decision": "solution1"}
    agent2_decide = {"agent_id": "agent2", "decision": "solution2"}
    
    # Agent 1 tries to DECIDE
    result1 = adapter.try_decide(need_id, agent1_decide)
    
    # Agent 2 tries to DECIDE for same need
    result2 = adapter.try_decide(need_id, agent2_decide)
    
    # Only one should succeed
    assert result1 != result2, "Results should be different"
    assert result1 or result2, "At least one should succeed"
    assert not (result1 and result2), "Both cannot succeed"
    
    print(f"Agent 1 success: {result1}, Agent 2 success: {result2}")


def test_loser_can_read_winner_decide(etcd_available):
    """
    Test that losing agent can read the winning DECIDE.
    """
    from consensus.raft_adapter import RaftConsensusAdapter
    
    adapter = RaftConsensusAdapter(etcd_host='localhost', etcd_port=2379)
    
    need_id = "test_need_456"
    winner_decide = {"agent_id": "winner", "solution": "A"}
    loser_decide = {"agent_id": "loser", "solution": "B"}
    
    # Winner DECIDEs first
    winner_success = adapter.try_decide(need_id, winner_decide)
    assert winner_success, "Winner should succeed"
    
    # Loser tries to DECIDE
    loser_success = adapter.try_decide(need_id, loser_decide)
    assert not loser_success, "Loser should fail"
    
    # Loser reads the winning DECIDE
    stored_decide = adapter.get_decide(need_id)
    
    assert stored_decide is not None
    assert stored_decide["agent_id"] == "winner"
    assert stored_decide["solution"] == "A"


def test_different_needs_independent(etcd_available):
    """
    Test that different need_ids are independent.
    """
    from consensus.raft_adapter import RaftConsensusAdapter
    
    adapter = RaftConsensusAdapter(etcd_host='localhost', etcd_port=2379)
    
    need1_decide = {"agent_id": "agent1", "solution": "X"}
    need2_decide = {"agent_id": "agent2", "solution": "Y"}
    
    # Both should succeed for different needs
    result1 = adapter.try_decide("need_1", need1_decide)
    result2 = adapter.try_decide("need_2", need2_decide)
    
    assert result1, "First DECIDE should succeed"
    assert result2, "Second DECIDE should succeed"


def test_concurrent_decide_race_condition(etcd_available):
    """
    Test that concurrent DECIDE attempts are handled correctly.
    """
    from consensus.raft_adapter import RaftConsensusAdapter
    import threading
    
    adapter = RaftConsensusAdapter(etcd_host='localhost', etcd_port=2379)
    
    need_id = "test_race_789"
    results = []
    
    def try_decide_thread(agent_id):
        decide = {"agent_id": agent_id, "attempt": True}
        success = adapter.try_decide(need_id, decide)
        results.append((agent_id, success))
    
    # Launch 5 concurrent DECIDE attempts
    threads = []
    for i in range(5):
        t = threading.Thread(target=try_decide_thread, args=(f"agent_{i}",))
        threads.append(t)
        t.start()
    
    # Wait for all threads
    for t in threads:
        t.join()
    
    # Exactly one should succeed
    successes = [r for r in results if r[1]]
    assert len(successes) == 1, f"Exactly one should succeed, got {len(successes)}"
    
    print(f"Winner: {successes[0][0]}")
