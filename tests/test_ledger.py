"""
Unit tests for Credit Ledger system.

Tests account creation, transfers, escrow operations, and audit trail.
"""

import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from economics.ledger import (
    CreditLedger, Account,
    InsufficientBalanceError, AccountExistsError,
    EscrowNotFoundError, EscrowAlreadyReleasedError
)
from economics.operations import OpType
import uuid


class TestAccountCreation:
    """Test account creation and retrieval"""
    
    def test_create_account(self):
        """Test basic account creation with initial balance"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        
        # Verify account exists
        account = ledger.get_account("alice")
        assert account is not None
        assert account.account_id == "alice"
        assert account.balance == 1000
        assert account.locked == 0
        assert account.unbonding == 0
        
        # Verify balance query
        assert ledger.get_balance("alice") == 1000
    
    def test_create_account_zero_balance(self):
        """Test creating account with zero initial balance"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("bob", 0)
        
        account = ledger.get_account("bob")
        assert account.balance == 0
    
    def test_create_duplicate_account(self):
        """Test that creating duplicate account raises error"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        
        with pytest.raises(AccountExistsError):
            ledger.create_account("alice", 500)
    
    def test_get_nonexistent_account(self):
        """Test that nonexistent account returns None"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        account = ledger.get_account("nonexistent")
        assert account is None
        
        # Balance should return 0
        assert ledger.get_balance("nonexistent") == 0


class TestTransfers:
    """Test credit transfers between accounts"""
    
    def test_transfer_sufficient_balance(self):
        """Test successful transfer with sufficient balance"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        ledger.create_account("bob", 500)
        
        # Transfer 200 from alice to bob
        op_id = ledger.transfer("alice", "bob", 200)
        assert op_id is not None
        
        # Verify balances
        assert ledger.get_balance("alice") == 800
        assert ledger.get_balance("bob") == 700
    
    def test_transfer_insufficient_balance(self):
        """Test transfer fails with insufficient balance"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 100)
        ledger.create_account("bob", 0)
        
        with pytest.raises(InsufficientBalanceError):
            ledger.transfer("alice", "bob", 200)
        
        # Balances should be unchanged
        assert ledger.get_balance("alice") == 100
        assert ledger.get_balance("bob") == 0
    
    def test_transfer_updates_both_accounts(self):
        """Test that transfer atomically updates both accounts"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        ledger.create_account("bob", 500)
        
        initial_total = 1500
        
        ledger.transfer("alice", "bob", 300)
        
        # Total should be conserved
        final_total = ledger.get_balance("alice") + ledger.get_balance("bob")
        assert final_total == initial_total
    
    def test_transfer_to_new_account(self):
        """Test transfer creates recipient account if needed"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        
        # Transfer to nonexistent account
        ledger.transfer("alice", "charlie", 200)
        
        # Charlie should now exist with transferred amount
        assert ledger.get_balance("charlie") == 200
        assert ledger.get_balance("alice") == 800
    
    def test_transfer_exact_balance(self):
        """Test transferring exact account balance"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        ledger.create_account("bob", 0)
        
        ledger.transfer("alice", "bob", 1000)
        
        assert ledger.get_balance("alice") == 0
        assert ledger.get_balance("bob") == 1000


class TestEscrow:
    """Test escrow operations"""
    
    def test_escrow_and_release(self):
        """Test successful escrow and release flow"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        ledger.create_account("bob", 0)
        
        # Escrow 300 credits
        escrow_id = "escrow-1"
        ledger.escrow("alice", 300, escrow_id)
        
        # Verify balance locked
        account = ledger.get_account("alice")
        assert account.balance == 700
        assert account.locked == 300
        
        # Release to bob
        ledger.release_escrow(escrow_id, "bob")
        
        # Verify funds released
        account = ledger.get_account("alice")
        assert account.balance == 700
        assert account.locked == 0
        
        assert ledger.get_balance("bob") == 300
    
    def test_escrow_and_cancel(self):
        """Test escrow cancellation returns funds"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        
        escrow_id = "escrow-cancel"
        ledger.escrow("alice", 400, escrow_id)
        
        # Verify locked
        assert ledger.get_balance("alice") == 600
        assert ledger.get_account("alice").locked == 400
        
        # Cancel escrow
        ledger.cancel_escrow(escrow_id)
        
        # Funds should be returned
        assert ledger.get_balance("alice") == 1000
        assert ledger.get_account("alice").locked == 0
    
    def test_escrow_insufficient_balance(self):
        """Test escrow fails with insufficient balance"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 100)
        
        with pytest.raises(InsufficientBalanceError):
            ledger.escrow("alice", 200, "escrow-fail")
        
        # Balance should be unchanged
        assert ledger.get_balance("alice") == 100
        assert ledger.get_account("alice").locked == 0
    
    def test_release_to_different_account(self):
        """Test releasing escrow to third party"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        ledger.create_account("bob", 0)
        ledger.create_account("charlie", 0)
        
        # Alice escrows, release to charlie
        ledger.escrow("alice", 500, "escrow-third-party")
        ledger.release_escrow("escrow-third-party", "charlie")
        
        assert ledger.get_balance("alice") == 500
        assert ledger.get_balance("bob") == 0
        assert ledger.get_balance("charlie") == 500
    
    def test_double_release_escrow(self):
        """Test that double-releasing escrow raises error"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        ledger.create_account("bob", 0)
        
        escrow_id = "escrow-double"
        ledger.escrow("alice", 200, escrow_id)
        ledger.release_escrow(escrow_id, "bob")
        
        # Try to release again
        with pytest.raises(EscrowAlreadyReleasedError):
            ledger.release_escrow(escrow_id, "bob")
    
    def test_cancel_already_released(self):
        """Test canceling already-released escrow raises error"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        ledger.create_account("bob", 0)
        
        escrow_id = "escrow-cancel-released"
        ledger.escrow("alice", 200, escrow_id)
        ledger.release_escrow(escrow_id, "bob")
        
        # Try to cancel after release
        with pytest.raises(EscrowAlreadyReleasedError):
            ledger.cancel_escrow(escrow_id)
    
    def test_release_nonexistent_escrow(self):
        """Test releasing nonexistent escrow raises error"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        
        with pytest.raises(EscrowNotFoundError):
            ledger.release_escrow("nonexistent-escrow", "alice")
    
    def test_cancel_nonexistent_escrow(self):
        """Test canceling nonexistent escrow raises error"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        
        with pytest.raises(EscrowNotFoundError):
            ledger.cancel_escrow("nonexistent-escrow")


class TestAuditTrail:
    """Test audit trail functionality"""
    
    def test_audit_trail_records_all_ops(self):
        """Test that all operations are recorded in audit trail"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        # Perform various operations
        ledger.create_account("alice", 1000)  # MINT
        ledger.create_account("bob", 500)     # MINT
        ledger.transfer("alice", "bob", 200)  # TRANSFER (2 ops)
        ledger.escrow("alice", 100, "e1")     # ESCROW
        
        # Get audit trail
        trail = ledger.get_audit_trail()
        
        # Should have: 2 MINTs + 2 TRANSFERs + 1 ESCROW = 5 ops
        assert len(trail) >= 5
    
    def test_audit_trail_ordering(self):
        """Test audit trail is in chronological order (newest first)"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        ledger.create_account("bob", 500)
        ledger.transfer("alice", "bob", 100)
        
        trail = ledger.get_audit_trail()
        
        # Should be newest first
        for i in range(len(trail) - 1):
            assert trail[i].timestamp >= trail[i + 1].timestamp
    
    def test_audit_trail_filtering(self):
        """Test filtering audit trail by account"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        ledger.create_account("bob", 500)
        ledger.transfer("alice", "bob", 100)
        
        # Get alice's operations only
        alice_trail = ledger.get_audit_trail(account_id="alice")
        
        # All operations should be for alice
        for op in alice_trail:
            assert op.account == "alice"
        
        # Should have MINT + TRANSFER (debit)
        assert len(alice_trail) >= 2
    
    def test_mint_recorded(self):
        """Test MINT operations are recorded in audit trail"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        
        trail = ledger.get_audit_trail(account_id="alice")
        
        # Should have a MINT operation
        mint_ops = [op for op in trail if op.operation == OpType.MINT]
        assert len(mint_ops) == 1
        assert mint_ops[0].amount == 1000
        assert mint_ops[0].account == "alice"
    
    def test_audit_trail_limit(self):
        """Test audit trail respects limit parameter"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        # Create many operations
        for i in range(20):
            ledger.create_account(f"account-{i}", 100)
        
        # Request limited results
        trail = ledger.get_audit_trail(limit=5)
        assert len(trail) == 5
    
    def test_transfer_audit_metadata(self):
        """Test transfer operations have correct metadata"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        ledger.create_account("bob", 500)
        ledger.transfer("alice", "bob", 200)
        
        # Get alice's transfer operation
        alice_trail = ledger.get_audit_trail(account_id="alice", limit=10)
        transfer_ops = [op for op in alice_trail if op.operation == OpType.TRANSFER]
        
        assert len(transfer_ops) >= 1
        # Check metadata contains counterparty
        assert "to_account" in transfer_ops[0].metadata or "from_account" in transfer_ops[0].metadata
    
    def test_escrow_audit_metadata(self):
        """Test escrow operations have escrow_id in metadata"""
        ledger = CreditLedger(Path(tempfile.mktemp()))
        
        ledger.create_account("alice", 1000)
        escrow_id = "test-escrow"
        ledger.escrow("alice", 300, escrow_id)
        
        trail = ledger.get_audit_trail(account_id="alice")
        escrow_ops = [op for op in trail if op.operation == OpType.ESCROW]
        
        assert len(escrow_ops) >= 1
        assert escrow_ops[0].metadata["escrow_id"] == escrow_id


class TestConcurrency:
    """Test thread safety of ledger operations"""
    
    def test_concurrent_transfers(self):
        """Test concurrent transfers maintain consistency"""
        import threading
        
        ledger = CreditLedger(Path(tempfile.mktemp()))
        ledger.create_account("alice", 10000)
        ledger.create_account("bob", 0)
        
        # Create multiple threads doing transfers
        def do_transfer():
            for _ in range(10):
                ledger.transfer("alice", "bob", 10)
        
        threads = [threading.Thread(target=do_transfer) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All transfers should succeed, total conserved
        assert ledger.get_balance("alice") + ledger.get_balance("bob") == 10000
        assert ledger.get_balance("bob") == 500  # 5 threads × 10 transfers × 10 credits
    
    def test_escrow_race_condition(self):
        """Test concurrent escrow operations don't corrupt state"""
        import threading
        
        ledger = CreditLedger(Path(tempfile.mktemp()))
        ledger.create_account("alice", 1000)
        
        results = []
        
        def try_escrow(escrow_id):
            try:
                ledger.escrow("alice", 600, escrow_id)
                results.append(True)
            except InsufficientBalanceError:
                results.append(False)
        
        # Try to escrow 600 from two threads (only one should succeed)
        threads = [
            threading.Thread(target=try_escrow, args=(f"escrow-{i}",))
            for i in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # At most one should succeed
        assert results.count(True) <= 1
        
        # Account state should be consistent
        account = ledger.get_account("alice")
        assert account.balance + account.locked == 1000
