"""
Test for escrow double-spend vulnerability (ECON-001).

This test demonstrates the race condition in release_escrow() where two concurrent
threads can both release the same escrow, causing the locked balance to be reduced twice.
"""

import sys
from pathlib import Path
import pytest
import threading
import tempfile

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from economics.ledger import CreditLedger, EscrowAlreadyReleasedError


def test_escrow_double_spend_race_condition():
    """
    Test that concurrent release_escrow calls for the same escrow_id
    only succeed once (one should raise EscrowAlreadyReleasedError).

    Currently this test FAILS because both releases succeed, demonstrating
    the double-spend vulnerability.
    """
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)

        # Set up: account with 1000 credits
        ledger.create_account("source_account", initial_balance=1000)
        ledger.create_account("dest_account", initial_balance=0)

        # Escrow 500 credits
        escrow_id = "test_escrow_123"
        ledger.escrow("source_account", 500, escrow_id)

        # Verify escrow created correctly
        source = ledger.get_account("source_account")
        assert source.balance == 500  # 1000 - 500 escrowed
        assert source.locked == 500  # 500 locked in escrow

        # Track results from concurrent threads
        results = {"success_count": 0, "errors": []}
        lock = threading.Lock()

        def try_release():
            """Attempt to release the escrow"""
            try:
                ledger.release_escrow(escrow_id, "dest_account")
                with lock:
                    results["success_count"] += 1
            except EscrowAlreadyReleasedError as e:
                with lock:
                    results["errors"].append(str(e))

        # Launch 2 concurrent threads trying to release same escrow
        thread1 = threading.Thread(target=try_release)
        thread2 = threading.Thread(target=try_release)

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # EXPECTED: Only ONE release should succeed
        # The other should raise EscrowAlreadyReleasedError
        assert (
            results["success_count"] == 1
        ), f"Expected 1 successful release, got {results['success_count']} (DOUBLE-SPEND BUG!)"
        assert len(results["errors"]) == 1, f"Expected 1 error, got {len(results['errors'])}"

        # Verify final state: locked should only be reduced by 500 (not 1000)
        source_final = ledger.get_account("source_account")
        assert (
            source_final.locked == 0
        ), f"Expected locked=0, got {source_final.locked} (double-reduced!)"

        # Destination should receive exactly 500
        dest_final = ledger.get_account("dest_account")
        assert dest_final.balance == 500, f"Expected dest balance=500, got {dest_final.balance}"


def test_escrow_release_sequential_works():
    """
    Sanity check: sequential releases should work correctly.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)

        ledger.create_account("source", initial_balance=1000)
        ledger.create_account("dest", initial_balance=0)

        # First escrow and release
        ledger.escrow("source", 300, "escrow1")
        ledger.release_escrow("escrow1", "dest")

        # Second escrow and release
        ledger.escrow("source", 200, "escrow2")
        ledger.release_escrow("escrow2", "dest")

        # Verify balances
        source = ledger.get_account("source")
        dest = ledger.get_account("dest")

        assert source.balance == 500  # 1000 - 300 - 200
        assert source.locked == 0
        assert dest.balance == 500  # 300 + 200


def test_escrow_already_released_error():
    """
    Test that releasing the same escrow twice raises an error (sequential case).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = CreditLedger(db_path)

        ledger.create_account("source", initial_balance=1000)
        ledger.create_account("dest", initial_balance=0)

        ledger.escrow("source", 500, "escrow_once")
        ledger.release_escrow("escrow_once", "dest")

        # Second release should fail
        with pytest.raises(EscrowAlreadyReleasedError):
            ledger.release_escrow("escrow_once", "dest")
