"""
Test for mint authorization (ECON-003).

This test verifies that credit minting is restricted to authorized system accounts,
preventing unlimited credit creation by arbitrary users.
"""

import sys
from pathlib import Path
import pytest
import tempfile

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from economics.ledger import CreditLedger


def test_unauthorized_mint_rejected():
    """
    Test that non-system accounts cannot mint credits via create_account.

    Currently this test will FAIL because anyone can mint unlimited credits.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)

        # Attempt to create account with initial balance as non-system user
        with pytest.raises(ValueError) as exc_info:
            ledger.create_account("user_account", initial_balance=1000, minter_id="hacker")

        assert (
            "not authorized" in str(exc_info.value).lower()
            or "system" in str(exc_info.value).lower()
        )


def test_system_mint_authorized():
    """
    Test that the system account CAN mint credits.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)

        # System account should be able to mint
        ledger.create_account("user_account", initial_balance=1000, minter_id="system")

        assert ledger.get_balance("user_account") == 1000


def test_zero_balance_any_minter():
    """
    Test that creating account with zero balance works for any minter
    (no minting happens, so authorization not needed).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)

        # Creating account with 0 balance should work regardless of minter
        ledger.create_account("user_account", initial_balance=0, minter_id="anyone")

        assert ledger.get_balance("user_account") == 0


def test_default_minter_is_system():
    """
    Test that when minter_id is not specified, it defaults to system.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)

        # Default minter should be system (authorized)
        ledger.create_account("user_account", initial_balance=500)

        assert ledger.get_balance("user_account") == 500


def test_max_supply_enforcement():
    """
    Test that minting is limited by MAX_SUPPLY constant.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)

        # Get max supply
        max_supply = ledger.MAX_SUPPLY

        # Mint near max supply
        ledger.create_account("account1", initial_balance=max_supply - 100)

        # Attempting to mint more should fail
        with pytest.raises(ValueError) as exc_info:
            ledger.create_account("account2", initial_balance=200)

        assert "supply" in str(exc_info.value).lower() or "exceeded" in str(exc_info.value).lower()


def test_total_supply_tracking():
    """
    Test that total supply is tracked correctly.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)

        # Initial supply should be 0
        assert ledger.get_total_supply() == 0

        # Mint some credits
        ledger.create_account("account1", initial_balance=1000)
        assert ledger.get_total_supply() == 1000

        ledger.create_account("account2", initial_balance=500)
        assert ledger.get_total_supply() == 1500

        ledger.create_account("account3", initial_balance=0)
        assert ledger.get_total_supply() == 1500  # Zero balance doesn't increase supply


def test_supply_not_affected_by_transfers():
    """
    Test that transfers don't affect total supply (money isn't created or destroyed).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)

        ledger.create_account("account1", initial_balance=1000)
        ledger.create_account("account2", initial_balance=500)

        initial_supply = ledger.get_total_supply()
        assert initial_supply == 1500

        # Transfer credits
        ledger.transfer("account1", "account2", 300)

        # Total supply should remain unchanged
        assert ledger.get_total_supply() == initial_supply
