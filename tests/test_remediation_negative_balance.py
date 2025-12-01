"""
Test for negative balance prevention (ECON-004).

This test verifies that the ledger prevents negative balances through both
CHECK constraints and pre-flight validation.
"""

import sys
from pathlib import Path
import pytest
import tempfile
import sqlite3

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from economics.ledger import CreditLedger, InsufficientBalanceError


def test_transfer_prevents_negative_balance():
    """
    Test that attempting to transfer more than available balance
    raises InsufficientBalanceError.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)
        
        # Create account with 100 credits
        ledger.create_account("account_a", initial_balance=100)
        ledger.create_account("account_b", initial_balance=0)
        
        # Attempt to transfer 200 credits (more than balance)
        with pytest.raises(InsufficientBalanceError) as exc_info:
            ledger.transfer("account_a", "account_b", 200)
        
        assert "Insufficient balance" in str(exc_info.value)
        
        # Verify account_a still has 100 (transfer didn't happen)
        assert ledger.get_balance("account_a") == 100
        assert ledger.get_balance("account_b") == 0


def test_escrow_prevents_negative_balance():
    """
    Test that escrowing more than available balance raises error.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)
        
        ledger.create_account("account_a", initial_balance=100)
        
        # Attempt to escrow 150 credits (more than balance)
        with pytest.raises(InsufficientBalanceError) as exc_info:
            ledger.escrow("account_a", 150, "escrow_123")
        
        assert "Insufficient balance" in str(exc_info.value)
        
        # Verify balance unchanged
        assert ledger.get_balance("account_a") == 100


def test_database_check_constraints():
    """
    Test that CHECK constraints prevent negative balances at database level.
    
    This tests that even direct SQL updates cannot create negative balances.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)
        
        ledger.create_account("account_a", initial_balance=100)
        
        # Attempt direct SQL update to create negative balance
        # This should fail due to CHECK constraint
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            with ledger.lock:
                with ledger.conn:
                    ledger.conn.execute(
                        "UPDATE accounts SET balance = -50 WHERE account_id = ?",
                        ("account_a",)
                    )
        
        # Error should mention CHECK constraint
        error_msg = str(exc_info.value).lower()
        assert "check" in error_msg or "constraint" in error_msg
        
        # Verify balance is still 100 (update was rolled back)
        assert ledger.get_balance("account_a") == 100


def test_check_constraint_on_locked():
    """
    Test CHECK constraint on locked field.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)
        
        ledger.create_account("account_a", initial_balance=100)
        
        # Attempt to set locked to negative value
        with pytest.raises(sqlite3.IntegrityError):
            with ledger.lock:
                with ledger.conn:
                    ledger.conn.execute(
                        "UPDATE accounts SET locked = -10 WHERE account_id = ?",
                        ("account_a",)
                    )


def test_check_constraint_on_unbonding():
    """
    Test CHECK constraint on unbonding field.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)
        
        ledger.create_account("account_a", initial_balance=100)
        
        # Attempt to set unbonding to negative value
        with pytest.raises(sqlite3.IntegrityError):
            with ledger.lock:
                with ledger.conn:
                    ledger.conn.execute(
                        "UPDATE accounts SET unbonding = -5 WHERE account_id = ?",
                        ("account_a",)
                    )


def test_exact_balance_transfer_works():
    """
    Sanity check: transferring exact balance should work.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)
        
        ledger.create_account("account_a", initial_balance=100)
        ledger.create_account("account_b", initial_balance=0)
        
        # Transfer exact balance - should succeed
        ledger.transfer("account_a", "account_b", 100)
        
        assert ledger.get_balance("account_a") == 0
        assert ledger.get_balance("account_b") == 100


def test_partial_balance_transfer_works():
    """
    Sanity check: transferring partial balance should work.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)
        
        ledger.create_account("account_a", initial_balance=100)
        ledger.create_account("account_b", initial_balance=0)
        
        # Transfer partial balance - should succeed
        ledger.transfer("account_a", "account_b", 60)
        
        assert ledger.get_balance("account_a") == 40
        assert ledger.get_balance("account_b") == 60
