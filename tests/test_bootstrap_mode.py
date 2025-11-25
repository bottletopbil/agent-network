"""
Test bootstrap mode and progressive quorum calculation.

Verifies:
- Bootstrap mode detection based on verifier count
- K=1 during bootstrap, progressive K after
- Exit conditions based on stability
- Challenge reward boosting during bootstrap
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from consensus.bootstrap import BootstrapManager, bootstrap_manager
from consensus.quorum import QuorumTracker, quorum_tracker


class TestBootstrapModeDetection:
    """Test bootstrap mode detection logic"""
    
    def test_bootstrap_mode_with_few_verifiers(self):
        """Network with < 10 verifiers is in bootstrap mode"""
        manager = BootstrapManager(bootstrap_threshold=10)
        
        assert manager.is_bootstrap_mode(5) is True
        assert manager.is_bootstrap_mode(9) is True
        assert manager.is_bootstrap_mode(1) is True
    
    def test_normal_mode_with_enough_verifiers(self):
        """Network with >= 10 verifiers is NOT in bootstrap mode"""
        manager = BootstrapManager(bootstrap_threshold=10)
        
        assert manager.is_bootstrap_mode(10) is False
        assert manager.is_bootstrap_mode(15) is False
        assert manager.is_bootstrap_mode(100) is False
    
    def test_custom_bootstrap_threshold(self):
        """Bootstrap threshold can be customized"""
        manager = BootstrapManager(bootstrap_threshold=20)
        
        assert manager.is_bootstrap_mode(19) is True
        assert manager.is_bootstrap_mode(20) is False


class TestKResultCalculation:
    """Test dynamic K calculation with bootstrap mode"""
    
    def test_k_equals_1_during_bootstrap(self):
        """K=1 when in bootstrap mode"""
        manager = BootstrapManager(bootstrap_threshold=10, k_target=5)
        
        # Explicitly in bootstrap
        assert manager.calculate_k_result(5, bootstrap_mode=True) == 1
        assert manager.calculate_k_result(1, bootstrap_mode=True) == 1
        assert manager.calculate_k_result(9, bootstrap_mode=True) == 1
    
    def test_k_auto_detection_in_bootstrap(self):
        """K=1 auto-detected for < 10 verifiers"""
        manager = BootstrapManager(bootstrap_threshold=10, k_target=5)
        
        assert manager.calculate_k_result(5) == 1
        assert manager.calculate_k_result(1) == 1
        assert manager.calculate_k_result(9) == 1
    
    def test_progressive_k_after_bootstrap(self):
        """K grows progressively with verifier count after bootstrap"""
        manager = BootstrapManager(bootstrap_threshold=10, k_target=5)
        
        # 10 verifiers: floor(10 * 0.3) = 3, but min is 2
        assert manager.calculate_k_result(10) == 3
        
        # 15 verifiers: floor(15 * 0.3) = 4
        assert manager.calculate_k_result(15) == 4
        
        # 20 verifiers: floor(20 * 0.3) = 6, capped at k_target=5
        assert manager.calculate_k_result(20) == 5
        
        # 11 verifiers (just above bootstrap): floor(11 * 0.3) = 3
        assert manager.calculate_k_result(11) == 3
    
    def test_k_minimum_is_2_after_bootstrap(self):
        """K is at least 2 after bootstrap, even with few verifiers"""
        manager = BootstrapManager(bootstrap_threshold=10, k_target=5)
        
        # Just exited bootstrap: 10 verifiers
        # floor(10 * 0.3) = 3
        k = manager.calculate_k_result(10, bootstrap_mode=False)
        assert k >= 2
        
        # 11 verifiers: floor(11 * 0.3) = 3
        assert manager.calculate_k_result(11, bootstrap_mode=False) >= 2
    
    def test_k_capped_at_target(self):
        """K never exceeds k_target"""
        manager = BootstrapManager(bootstrap_threshold=10, k_target=5)
        
        # Large network: floor(100 * 0.3) = 30, but capped at 5
        assert manager.calculate_k_result(100) == 5
        assert manager.calculate_k_result(50) == 5
        assert manager.calculate_k_result(200) == 5


class TestExitConditions:
    """Test bootstrap mode exit criteria"""
    
    def test_cannot_exit_with_few_verifiers(self):
        """Cannot exit bootstrap with < threshold verifiers"""
        manager = BootstrapManager(bootstrap_threshold=10, bootstrap_stable_hours=24)
        
        # Even with 100 hours, can't exit with too few verifiers
        assert manager.should_exit_bootstrap(9, 100) is False
        assert manager.should_exit_bootstrap(5, 50) is False
    
    def test_cannot_exit_without_stability(self):
        """Cannot exit bootstrap without sufficient stable hours"""
        manager = BootstrapManager(bootstrap_threshold=10, bootstrap_stable_hours=24)
        
        # Enough verifiers, but not stable long enough
        assert manager.should_exit_bootstrap(10, 20) is False
        assert manager.should_exit_bootstrap(15, 10) is False
        assert manager.should_exit_bootstrap(10, 0) is False
    
    def test_can_exit_with_threshold_and_stability(self):
        """Can exit bootstrap with >= threshold verifiers for stable duration"""
        manager = BootstrapManager(bootstrap_threshold=10, bootstrap_stable_hours=24)
        
        # Exactly at threshold, exactly at stable hours
        assert manager.should_exit_bootstrap(10, 24) is True
        
        # Above threshold, above stable hours
        assert manager.should_exit_bootstrap(15, 30) is True
        assert manager.should_exit_bootstrap(100, 48) is True
    
    def test_custom_stability_requirement(self):
        """Stability requirement can be customized"""
        manager = BootstrapManager(
            bootstrap_threshold=10,
            bootstrap_stable_hours=48  # Require 48 hours
        )
        
        assert manager.should_exit_bootstrap(10, 24) is False
        assert manager.should_exit_bootstrap(10, 48) is True
        assert manager.should_exit_bootstrap(20, 50) is True


class TestChallengeRewardBoost:
    """Test challenge reward boosting during bootstrap"""
    
    def test_2x_reward_during_bootstrap(self):
        """Rewards are doubled during bootstrap mode"""
        manager = BootstrapManager()
        
        assert manager.boost_challenge_reward(100, bootstrap_mode=True) == 200
        assert manager.boost_challenge_reward(500, bootstrap_mode=True) == 1000
        assert manager.boost_challenge_reward(1, bootstrap_mode=True) == 2
    
    def test_normal_reward_after_bootstrap(self):
        """Rewards are unchanged after bootstrap"""
        manager = BootstrapManager()
        
        assert manager.boost_challenge_reward(100, bootstrap_mode=False) == 100
        assert manager.boost_challenge_reward(500, bootstrap_mode=False) == 500
        assert manager.boost_challenge_reward(1, bootstrap_mode=False) == 1


class TestQuorumTrackerIntegration:
    """Test QuorumTracker integration with bootstrap mode"""
    
    def test_get_k_plan_with_bootstrap_in_bootstrap_mode(self):
        """QuorumTracker returns K=1 during bootstrap"""
        tracker = QuorumTracker()
        
        # < 10 verifiers = bootstrap mode
        assert tracker.get_k_plan_with_bootstrap(5) == 1
        assert tracker.get_k_plan_with_bootstrap(1) == 1
        assert tracker.get_k_plan_with_bootstrap(9) == 1
    
    def test_get_k_plan_with_bootstrap_after_bootstrap(self):
        """QuorumTracker returns progressive K after bootstrap"""
        tracker = QuorumTracker()
        
        # >= 10 verifiers = not bootstrap
        assert tracker.get_k_plan_with_bootstrap(10) == 3  # floor(10 * 0.3)
        assert tracker.get_k_plan_with_bootstrap(15) == 4  # floor(15 * 0.3)
        assert tracker.get_k_plan_with_bootstrap(20) == 5  # capped at k_target
    
    def test_original_get_k_plan_still_works(self):
        """Original get_k_plan method still works (backward compatibility)"""
        tracker = QuorumTracker()
        
        # Original method doesn't use bootstrap logic
        assert tracker.get_k_plan(5) == 1   # floor(5 * 0.3)
        assert tracker.get_k_plan(10) == 3  # floor(10 * 0.3)
        assert tracker.get_k_plan(20) == 5  # capped at 5


class TestGlobalBootstrapManager:
    """Test global bootstrap_manager instance"""
    
    def test_global_instance_exists(self):
        """Global bootstrap_manager is available"""
        assert bootstrap_manager is not None
        assert isinstance(bootstrap_manager, BootstrapManager)
    
    def test_global_instance_has_defaults(self):
        """Global instance has correct default values"""
        assert bootstrap_manager.bootstrap_threshold == 10
        assert bootstrap_manager.bootstrap_stable_hours == 24
        assert bootstrap_manager.k_target == 5
    
    def test_global_instance_is_functional(self):
        """Global instance works correctly"""
        assert bootstrap_manager.is_bootstrap_mode(5) is True
        assert bootstrap_manager.is_bootstrap_mode(15) is False
        assert bootstrap_manager.calculate_k_result(5) == 1
        assert bootstrap_manager.calculate_k_result(15) == 4


class TestEdgeCases:
    """Test edge cases and boundary conditions"""
    
    def test_zero_verifiers(self):
        """Handle zero verifiers gracefully"""
        manager = BootstrapManager()
        
        assert manager.is_bootstrap_mode(0) is True
        assert manager.calculate_k_result(0) == 1  # Bootstrap mode
    
    def test_exactly_at_threshold(self):
        """Behavior at exact threshold boundary"""
        manager = BootstrapManager(bootstrap_threshold=10)
        
        # 9 = bootstrap, 10 = not bootstrap
        assert manager.is_bootstrap_mode(9) is True
        assert manager.is_bootstrap_mode(10) is False
        
        # K changes at boundary
        assert manager.calculate_k_result(9) == 1
        assert manager.calculate_k_result(10) == 3
    
    def test_very_large_network(self):
        """Handle very large networks correctly"""
        manager = BootstrapManager(bootstrap_threshold=10, k_target=5)
        
        # Always capped at k_target
        assert manager.calculate_k_result(1000) == 5
        assert manager.calculate_k_result(10000) == 5
    
    def test_override_bootstrap_detection(self):
        """Can override bootstrap mode detection"""
        manager = BootstrapManager(bootstrap_threshold=10)
        
        # Force bootstrap mode even with many verifiers
        assert manager.calculate_k_result(100, bootstrap_mode=True) == 1
        
        # Force normal mode even with few verifiers
        assert manager.calculate_k_result(5, bootstrap_mode=False) == 2  # min is 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
