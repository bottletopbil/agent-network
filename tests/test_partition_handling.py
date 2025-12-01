"""
Tests for partition handling and epoch-based fencing.

Tests epoch management, deterministic merge rules, and conflict resolution.
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from consensus.epochs import EpochManager, EpochState
from consensus.merge import MergeHandler, DecideConflict


def test_epoch_advancement():
    """Test epoch increments correctly"""
    manager = EpochManager()

    initial_epoch = manager.get_current_epoch()
    assert initial_epoch == 1

    # Advance epoch
    new_epoch = manager.advance_epoch(reason="test")
    assert new_epoch == 2
    assert manager.get_current_epoch() == 2

    # Advance again
    new_epoch = manager.advance_epoch(reason="partition_heal")
    assert new_epoch == 3


def test_fence_token_creation():
    """Test fencing token generation"""
    manager = EpochManager()

    token = manager.create_fence_token()
    assert "epoch-" in token
    assert token.startswith("epoch-1-")

    # Advance and create new token
    manager.advance_epoch(reason="test")
    token2 = manager.create_fence_token()
    assert token2.startswith("epoch-2-")
    assert token != token2


def test_fence_token_validation():
    """Test fencing token validation"""
    manager = EpochManager()

    # Current epoch token is valid
    token = manager.create_fence_token(epoch=1)
    assert manager.validate_fence_token(token, current_epoch=1) is True

    # Higher epoch token is valid
    token_future = manager.create_fence_token(epoch=5)
    assert manager.validate_fence_token(token_future, current_epoch=1) is True

    # Lower epoch token is stale
    token_stale = manager.create_fence_token(epoch=1)
    assert manager.validate_fence_token(token_stale, current_epoch=2) is False

    # Invalid token format
    assert manager.validate_fence_token("invalid-token", current_epoch=1) is False


def test_highest_epoch_wins():
    """Test that higher epoch wins in conflict resolution"""
    handler = MergeHandler()

    local = {"epoch": 2, "lamport": 100, "decider_id": "a"}
    remote = {"epoch": 1, "lamport": 200, "decider_id": "b"}

    winner = handler.highest_epoch_wins(local, remote)
    assert winner == "local"  # Epoch 2 > Epoch 1

    # Flip it
    local = {"epoch": 1, "lamport": 100, "decider_id": "a"}
    remote = {"epoch": 3, "lamport": 50, "decider_id": "b"}

    winner = handler.highest_epoch_wins(local, remote)
    assert winner == "remote"  # Epoch 3 > Epoch 1


def test_lamport_tiebreaker():
    """Test lamport as tiebreaker when epochs equal"""
    handler = MergeHandler()

    # Same epoch, different lamport
    local = {"epoch": 1, "lamport": 100, "decider_id": "a"}
    remote = {"epoch": 1, "lamport": 200, "decider_id": "b"}

    winner = handler.highest_epoch_wins(local, remote)
    assert winner == "remote"  # Higher lamport wins

    # Flip it
    local = {"epoch": 2, "lamport": 500, "decider_id": "a"}
    remote = {"epoch": 2, "lamport": 100, "decider_id": "b"}

    winner = handler.highest_epoch_wins(local, remote)
    assert winner == "local"  # Higher lamport wins


def test_decider_id_tiebreaker():
    """Test decider_id as final tiebreaker"""
    handler = MergeHandler()

    # Same epoch, same lamport, different decider_id
    local = {"epoch": 1, "lamport": 100, "decider_id": "alice"}
    remote = {"epoch": 1, "lamport": 100, "decider_id": "bob"}

    winner = handler.highest_epoch_wins(local, remote)
    assert winner == "local"  # 'alice' < 'bob' lexicographically

    # Flip it
    local = {"epoch": 1, "lamport": 100, "decider_id": "zoe"}
    remote = {"epoch": 1, "lamport": 100, "decider_id": "adam"}

    winner = handler.highest_epoch_wins(local, remote)
    assert winner == "remote"  # 'adam' < 'zoe'


def test_merge_on_heal_no_conflicts():
    """Test merge when no conflicts exist"""
    handler = MergeHandler()

    # Same decisions in both partitions
    local_decides = [
        {"need_id": "n1", "proposal_id": "p1", "epoch": 1},
        {"need_id": "n2", "proposal_id": "p2", "epoch": 1},
    ]

    remote_decides = [
        {"need_id": "n1", "proposal_id": "p1", "epoch": 1},  # Same
        {"need_id": "n3", "proposal_id": "p3", "epoch": 1},  # Different need
    ]

    conflicts = handler.merge_on_heal(local_decides, remote_decides)

    assert len(conflicts) == 0  # No conflicts


def test_merge_on_heal_finds_conflicts():
    """Test merge detects conflicts"""
    handler = MergeHandler()

    local_decides = [
        {
            "need_id": "n1",
            "proposal_id": "p1",
            "epoch": 1,
            "lamport": 100,
            "decider_id": "a",
        },
        {
            "need_id": "n2",
            "proposal_id": "p2",
            "epoch": 1,
            "lamport": 101,
            "decider_id": "a",
        },
    ]

    remote_decides = [
        {
            "need_id": "n1",
            "proposal_id": "p1-alt",
            "epoch": 2,
            "lamport": 50,
            "decider_id": "b",
        },  # Conflict!
        {
            "need_id": "n3",
            "proposal_id": "p3",
            "epoch": 1,
            "lamport": 102,
            "decider_id": "b",
        },  # No conflict
    ]

    conflicts = handler.merge_on_heal(local_decides, remote_decides)

    assert len(conflicts) == 1
    assert conflicts[0].need_id == "n1"
    assert conflicts[0].winner == "remote"  # Epoch 2 > Epoch 1
    assert "Epoch 1 vs 2" in conflicts[0].reason


def test_merge_multiple_conflicts():
    """Test merge with multiple conflicts"""
    handler = MergeHandler()

    local_decides = [
        {
            "need_id": "n1",
            "proposal_id": "p1",
            "epoch": 1,
            "lamport": 100,
            "decider_id": "a",
        },
        {
            "need_id": "n2",
            "proposal_id": "p2",
            "epoch": 1,
            "lamport": 200,
            "decider_id": "a",
        },
    ]

    remote_decides = [
        {
            "need_id": "n1",
            "proposal_id": "p1-alt",
            "epoch": 2,
            "lamport": 50,
            "decider_id": "b",
        },
        {
            "need_id": "n2",
            "proposal_id": "p2-alt",
            "epoch": 1,
            "lamport": 150,
            "decider_id": "b",
        },
    ]

    conflicts = handler.merge_on_heal(local_decides, remote_decides)

    assert len(conflicts) == 2

    # Conflict 1: n1, remote wins (higher epoch)
    c1 = [c for c in conflicts if c.need_id == "n1"][0]
    assert c1.winner == "remote"

    # Conflict 2: n2, local wins (higher lamport, same epoch)
    c2 = [c for c in conflicts if c.need_id == "n2"][0]
    assert c2.winner == "local"


def test_epoch_state():
    """Test epoch state retrieval"""
    manager = EpochManager()

    state = manager.get_epoch_state()
    assert isinstance(state, EpochState)
    assert state.epoch_number == 1
    assert state.started_at_ns > 0
    assert state.coordinator_id == "system"

    # Advance and check new state
    manager.advance_epoch(reason="test")
    state2 = manager.get_epoch_state()
    assert state2.epoch_number == 2
    assert state2.started_at_ns >= state.started_at_ns


def test_decide_conflict_dataclass():
    """Test DecideConflict creation"""
    conflict = DecideConflict(
        need_id="n1",
        local_decide={"proposal_id": "p1"},
        remote_decide={"proposal_id": "p2"},
        winner="local",
        reason="Higher epoch",
    )

    assert conflict.need_id == "n1"
    assert conflict.winner == "local"
    assert "Higher epoch" in conflict.reason


def test_deterministic_tiebreaking():
    """Test that tiebreaking is deterministic (same inputs = same output)"""
    handler = MergeHandler()

    local = {"epoch": 1, "lamport": 100, "decider_id": "alpha"}
    remote = {"epoch": 1, "lamport": 100, "decider_id": "beta"}

    # Call multiple times
    results = [handler.highest_epoch_wins(local, remote) for _ in range(5)]

    # All results should be the same
    assert all(r == results[0] for r in results)
    assert results[0] == "local"  # 'alpha' < 'beta'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
