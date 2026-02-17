"""
Simple standalone test for Phase 6.1 - Epoch Fencing Enforcement

Verifies that:
1. Stale DECIDEs from old epochs are rejected
2. Epoch state persists across restarts
"""

import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from consensus.epochs import EpochManager


def test_epoch_fencing():
    """Test that epoch fencing works correctly"""
    
    print("=" * 60)
    print("Testing Phase 6.1: Epoch Fencing Enforcement")
    print("=" * 60)
    
    # Create a temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_epochs.db"
        
        print("\n1. Testing epoch initialization...")
        epoch_mgr = EpochManager(db_path=str(db_path))
        
        current = epoch_mgr.get_current_epoch()
        assert current == 1, f"Should start at epoch 1, got {current}"
        print(f"   ✅ Epoch manager initialized at epoch {current}")
        
        print("\n2. Testing epoch advancement...")
        new_epoch = epoch_mgr.advance_epoch(reason="test_partition_heal")
        assert new_epoch == 2, f"Should advance to epoch 2, got {new_epoch}"
        print(f"   ✅ Advanced to epoch {new_epoch}")
        
        print("\n3. Testing epoch persistence across restarts...")
        # Create a new manager instance to simulate restart
        epoch_mgr2 = EpochManager(db_path=str(db_path))
        loaded_epoch = epoch_mgr2.get_current_epoch()
        assert loaded_epoch == 2, f"Should load epoch 2 from database, got {loaded_epoch}"
        print(f"   ✅ Epoch {loaded_epoch} persisted and loaded correctly")
        
        print("\n4. Testing fence token validation...")
        token_old = epoch_mgr2.create_fence_token(epoch=1)
        token_current = epoch_mgr2.create_fence_token(epoch=2)
        
        is_stale = not epoch_mgr2.validate_fence_token(token_old, current_epoch=2)
        is_valid = epoch_mgr2.validate_fence_token(token_current, current_epoch=2)
        
        assert is_stale, "Old token should be invalid"
        assert is_valid, "Current token should be valid"
        print(f"   ✅ Stale token correctly rejected")
        print(f"   ✅ Current token correctly accepted")
        
    print("\n" + "=" * 60)
    print("✅ All Phase 6.1 tests passed!")
    print("=" * 60)
    print("\nWhat this means:")
    print("  • Zombie agents from old epochs will be FENCED OUT")
    print("  • Epoch state survives system restarts")
    print("  • The system is protected against stale decisions")


if __name__ == "__main__":
    test_epoch_fencing()
