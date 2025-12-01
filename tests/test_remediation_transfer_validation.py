"""
Test for transfer recipient validation (ECON-010).

Validates that transfers require recipient account to exist.
"""

import sys
from pathlib import Path
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_transfer_to_nonexistent_account_raises_error():
    """
    Test that transferring to non-existent account raises ValueError.
    """
    from economics.ledger import CreditLedger

    ledger = CreditLedger()

    # Create sender account
    ledger.create_account("alice", 1000)

    # Try to transfer to non-existent account
    with pytest.raises(ValueError, match="Recipient account does not exist"):
        ledger.transfer("alice", "bob_typo", 100)

    # Alice's balance should be unchanged
    assert ledger.get_balance("alice") == 1000


def test_transfer_with_allow_create_works():
    """
    Test that allow_create_recipient flag enables auto-creation.
    """
    from economics.ledger import CreditLedger

    ledger = CreditLedger()

    ledger.create_account("alice", 1000)

    # Transfer with auto-create enabled
    ledger.transfer("alice", "bob", 100, allow_create_recipient=True)

    # Bob should be created with 100
    assert ledger.get_balance("bob") == 100
    assert ledger.get_balance("alice") == 900


def test_transfer_to_existing_account_works():
    """
    Test that normal transfer to existing account still works.
    """
    from economics.ledger import CreditLedger

    ledger = CreditLedger()

    ledger.create_account("alice", 1000)
    ledger.create_account("bob", 0)

    # Should work fine
    ledger.transfer("alice", "bob", 250)

    assert ledger.get_balance("alice") == 750
    assert ledger.get_balance("bob") == 250


def test_typo_prevention():
    """
    Test that typos in recipient name are caught.

    Common scenario: "user123" vs "user1234" (extra digit)
    """
    from economics.ledger import CreditLedger

    ledger = CreditLedger()

    ledger.create_account("alice", 1000)
    ledger.create_account("user123", 0)  # Correct account

    # Typo in recipient (extra 4)
    with pytest.raises(ValueError, match="Recipient account does not exist"):
        ledger.transfer("alice", "user1234", 500)

    # Funds should not be lost
    assert ledger.get_balance("alice") == 1000
    assert ledger.get_balance("user123") == 0


def test_backward_compatibility_with_flag():
    """
    Test that old code using auto-create still works with flag.
    """
    from economics.ledger import CreditLedger

    ledger = CreditLedger()

    ledger.create_account("system", 10000)

    # Old code that relied on auto-create
    ledger.transfer("system", "new_user1", 100, allow_create_recipient=True)
    ledger.transfer("system", "new_user2", 100, allow_create_recipient=True)

    assert ledger.get_balance("new_user1") == 100
    assert ledger.get_balance("new_user2") == 100
    assert ledger.get_balance("system") == 9800
