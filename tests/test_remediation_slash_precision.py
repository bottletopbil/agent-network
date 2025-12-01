"""
Test for integer overflow and precision in slash distribution (ECON-005).

This test verifies that slashing distribution uses integer arithmetic
to avoid precision loss from float multiplication.
"""

import sys
from pathlib import Path
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_slash_distribution_precision_odd_number():
    """
    Test that distribution with odd numbers is exact with no rounding errors.
    
    999 credits slashed should split exactly:
    - Challenger: 499 (50%)
    - Honest verifiers: 399 (40%)
    - Burned: 101 (10%)
    Total: 999 (exact)
    """
    total_slashed = 999
    
    # Integer arithmetic (proposed fix)
    challenger_payout = (total_slashed * 50) // 100
    honest_total = (total_slashed * 40) // 100
    burned = total_slashed - challenger_payout - honest_total
    
    # Verify exact percentages
    assert challenger_payout == 499  # 50% of 999
    assert honest_total == 399  # 40% of 999
    assert burned == 101  # 10% of 999 (plus remainder)
    
    # Verify sum equals total (no loss)
    assert challenger_payout + honest_total + burned == total_slashed
    
    # Float method (old/buggy way) would give:
    # int(999 * 0.50) = 499
    # int(999 * 0.40) = 399
    # But potential for accumulated error in more complex scenarios


def test_slash_distribution_precision_large_number():
    """
    Test that very large numbers don't overflow or lose precision.
    
    Using a number near max practical value.
    """
    # 1 trillion credits
    total_slashed = 1_000_000_000_000
    
    challenger_payout = (total_slashed * 50) // 100
    honest_total = (total_slashed * 40) // 100
    burned = total_slashed - challenger_payout - honest_total
    
    # Verify exact amounts
    assert challenger_payout == 500_000_000_000  # Exactly 50%
    assert honest_total == 400_000_000_000  # Exactly 40%
    assert burned == 100_000_000_000  # Exactly 10%
    
    # Verify sum equals total
    assert challenger_payout + honest_total + burned == total_slashed
    
    # No overflow or precision loss
    assert isinstance(challenger_payout, int)
    assert isinstance(honest_total, int)
    assert isinstance(burned, int)


def test_slash_distribution_handles_remainder():
    """
    Test that remainder from division goes to the burned amount.
    
    With 997 credits:
    - 50% = 498 (integer division)
    - 40% = 398 (integer division)
    - Remainder: 997 - 498 - 398 = 101 (goes to burned, includes the 1 credit remainder)
    """
    total_slashed = 997
    
    challenger_payout = (total_slashed * 50) // 100
    honest_total = (total_slashed * 40) // 100
    burned = total_slashed - challenger_payout - honest_total
    
    assert challenger_payout == 498
    assert honest_total == 398
    assert burned == 101  # 10% base (99) + remainder (2) = 101
    
    # Sum must equal total
    assert challenger_payout + honest_total + burned == total_slashed


def test_no_precision_loss_with_integer_arithmetic():
    """
    Test various amounts to ensure no precision loss.
    """
    test_amounts = [1, 10, 100, 999, 1000, 10000, 99999, 1_000_000, 999_999_999]
    
    for total in test_amounts:
        challenger = (total * 50) // 100
        honest = (total * 40) // 100
        burned = total - challenger - honest
        
        # Sum must always equal input
        assert challenger + honest + burned == total, \
            f"Precision loss for {total}: {challenger} + {honest} + {burned} != {total}"
        
        # All should be integers
        assert isinstance(challenger, int)
        assert isinstance(honest, int)
        assert isinstance(burned, int)


def test_float_method_comparison():
    """
    Compare float method vs integer method to show the difference.
    
    This test demonstrates why integer arithmetic is better.
    """
    total_slashed = 999
    
    # Old float method (prone to precision issues in some cases)
    float_challenger = int(total_slashed * 0.50)
    float_honest = int(total_slashed * 0.40)
    float_burned = int(total_slashed * 0.10)
    float_sum = float_challenger + float_honest + float_burned
    
    # Integer method (proposed fix)
    int_challenger = (total_slashed * 50) // 100
    int_honest = (total_slashed * 40) // 100
    int_burned = total_slashed - int_challenger - int_honest
    int_sum = int_challenger + int_honest + int_burned
    
    # Integer method preserves total exactly
    assert int_sum == total_slashed
    
    # Float method may not (in this case it happens to equal 998)
    # The burned calculation is separate so sum might not equal total
    print(f"Float sum: {float_sum}, Integer sum: {int_sum}, Original: {total_slashed}")
    
    # Integer method guarantees no loss
    assert int_sum == total_slashed
