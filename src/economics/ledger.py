"""
Credit Ledger: account balances, transfers, and escrow with SQLite persistence.
"""

import sqlite3
import json
import threading
import uuid
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from economics.operations import OpType, LedgerOp, validate_amount, validate_account_id


# Custom exceptions
class InsufficientBalanceError(Exception):
    """Raised when account has insufficient balance for operation"""
    pass


class AccountExistsError(Exception):
    """Raised when attempting to create duplicate account"""
    pass


class EscrowNotFoundError(Exception):
    """Raised when escrow ID not found"""
    pass


class EscrowAlreadyReleasedError(Exception):
    """Raised when attempting to operate on already-released escrow"""
    pass


@dataclass
class Account:
    """Account state"""
    account_id: str
    balance: int        # Available credits
    locked: int         # Escrowed credits
    unbonding: int      # Credits in unbonding period


class CreditLedger:
    """
    Credit ledger with SQLite persistence and audit trail.
    
    Thread-safe operations with full audit logging.
    """
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.lock = threading.Lock()
        self._init_schema()
    
    def _init_schema(self):
        """Initialize database schema"""
        with self.conn:
            # Accounts table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id TEXT PRIMARY KEY,
                    balance INTEGER NOT NULL DEFAULT 0,
                    locked INTEGER NOT NULL DEFAULT 0,
                    unbonding INTEGER NOT NULL DEFAULT 0
                )
            """)
            
            # Operations audit trail (append-only)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS operations (
                    op_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    op_type TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    timestamp_ns INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL
                )
            """)
            
            # Escrows tracking table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS escrows (
                    escrow_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    released BOOLEAN NOT NULL DEFAULT 0,
                    released_to TEXT
                )
            """)
            
            # Indexes
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_account ON operations(account_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_timestamp ON operations(timestamp_ns)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_type ON operations(op_type)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_escrows_account ON escrows(account_id)")
    
    def create_account(self, account_id: str, initial_balance: int = 0) -> None:
        """
        Create a new account with initial balance.
        
        Args:
            account_id: Unique account identifier
            initial_balance: Starting balance (default 0)
        
        Raises:
            AccountExistsError: If account already exists
            ValueError: If initial_balance is negative
        """
        validate_account_id(account_id)
        if initial_balance < 0:
            raise ValueError(f"Initial balance cannot be negative: {initial_balance}")
        
        with self.lock:
            # Check if account exists
            cursor = self.conn.execute(
                "SELECT account_id FROM accounts WHERE account_id = ?",
                (account_id,)
            )
            if cursor.fetchone():
                raise AccountExistsError(f"Account already exists: {account_id}")
            
            with self.conn:
                # Create account
                self.conn.execute(
                    "INSERT INTO accounts (account_id, balance, locked, unbonding) VALUES (?, ?, 0, 0)",
                    (account_id, initial_balance)
                )
                
                # Record MINT operation if initial balance > 0
                if initial_balance > 0:
                    op_id = str(uuid.uuid4())
                    self.conn.execute("""
                        INSERT INTO operations (op_id, account_id, op_type, amount, timestamp_ns, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        op_id,
                        account_id,
                        OpType.MINT.value,
                        initial_balance,
                        time.time_ns(),
                        json.dumps({"reason": "initial_balance"})
                    ))
    
    def get_balance(self, account_id: str) -> int:
        """
        Get available (non-locked) balance for account.
        
        Args:
            account_id: Account identifier
        
        Returns:
            Available balance (0 if account doesn't exist)
        """
        cursor = self.conn.execute(
            "SELECT balance FROM accounts WHERE account_id = ?",
            (account_id,)
        )
        row = cursor.fetchone()
        return row[0] if row else 0
    
    def get_account(self, account_id: str) -> Optional[Account]:
        """
        Get full account details.
        
        Args:
            account_id: Account identifier
        
        Returns:
            Account object or None if not found
        """
        cursor = self.conn.execute(
            "SELECT account_id, balance, locked, unbonding FROM accounts WHERE account_id = ?",
            (account_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return Account(
            account_id=row[0],
            balance=row[1],
            locked=row[2],
            unbonding=row[3]
        )
    
    def transfer(self, from_id: str, to_id: str, amount: int) -> str:
        """
        Transfer credits between accounts.
        
        Args:
            from_id: Source account
            to_id: Destination account
            amount: Amount to transfer
        
        Returns:
            Operation ID
        
        Raises:
            InsufficientBalanceError: If source has insufficient balance
        """
        validate_account_id(from_id)
        validate_account_id(to_id)
        validate_amount(amount)
        
        with self.lock:
            # Check source balance
            from_balance = self.get_balance(from_id)
            if from_balance < amount:
                raise InsufficientBalanceError(
                    f"Insufficient balance: {from_balance} < {amount}"
                )
            
            with self.conn:
                # Deduct from source
                self.conn.execute(
                    "UPDATE accounts SET balance = balance - ? WHERE account_id = ?",
                    (amount, from_id)
                )
                
                # Add to destination (create account if needed)
                cursor = self.conn.execute(
                    "SELECT account_id FROM accounts WHERE account_id = ?",
                    (to_id,)
                )
                if cursor.fetchone():
                    self.conn.execute(
                        "UPDATE accounts SET balance = balance + ? WHERE account_id = ?",
                        (amount, to_id)
                    )
                else:
                    self.conn.execute(
                        "INSERT INTO accounts (account_id, balance, locked, unbonding) VALUES (?, ?, 0, 0)",
                        (to_id, amount)
                    )
                
                # Record operations in audit trail
                op_id = str(uuid.uuid4())
                timestamp = time.time_ns()
                
                # Debit from source
                self.conn.execute("""
                    INSERT INTO operations (op_id, account_id, op_type, amount, timestamp_ns, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()),
                    from_id,
                    OpType.TRANSFER.value,
                    -amount,
                    timestamp,
                    json.dumps({"to_account": to_id, "transfer_id": op_id})
                ))
                
                # Credit to destination
                self.conn.execute("""
                    INSERT INTO operations (op_id, account_id, op_type, amount, timestamp_ns, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()),
                    to_id,
                    OpType.TRANSFER.value,
                    amount,
                    timestamp,
                    json.dumps({"from_account": from_id, "transfer_id": op_id})
                ))
                
                return op_id
    
    def escrow(self, account_id: str, amount: int, escrow_id: str) -> None:
        """
        Lock credits in escrow.
        
        Args:
            account_id: Account to escrow from
            amount: Amount to escrow
            escrow_id: Unique escrow identifier
        
        Raises:
            InsufficientBalanceError: If account has insufficient balance
        """
        validate_account_id(account_id)
        validate_amount(amount)
        
        with self.lock:
            # Check balance
            balance = self.get_balance(account_id)
            if balance < amount:
                raise InsufficientBalanceError(
                    f"Insufficient balance for escrow: {balance} < {amount}"
                )
            
            with self.conn:
                # Move from balance to locked
                self.conn.execute(
                    "UPDATE accounts SET balance = balance - ?, locked = locked + ? WHERE account_id = ?",
                    (amount, amount, account_id)
                )
                
                # Record escrow
                self.conn.execute("""
                    INSERT INTO escrows (escrow_id, account_id, amount, created_at, released)
                    VALUES (?, ?, ?, ?, 0)
                """, (escrow_id, account_id, amount, time.time_ns()))
                
                # Audit trail
                self.conn.execute("""
                    INSERT INTO operations (op_id, account_id, op_type, amount, timestamp_ns, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()),
                    account_id,
                    OpType.ESCROW.value,
                    amount,
                    time.time_ns(),
                    json.dumps({"escrow_id": escrow_id})
                ))
    
    def release_escrow(self, escrow_id: str, to_id: str) -> None:
        """
        Release escrowed credits to an account.
        
        Args:
            escrow_id: Escrow to release
            to_id: Destination account
        
        Raises:
            EscrowNotFoundError: If escrow doesn't exist
            EscrowAlreadyReleasedError: If escrow already released
        """
        validate_account_id(to_id)
        
        with self.lock:
            # Get escrow details
            cursor = self.conn.execute(
                "SELECT account_id, amount, released FROM escrows WHERE escrow_id = ?",
                (escrow_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise EscrowNotFoundError(f"Escrow not found: {escrow_id}")
            
            from_id, amount, released = row
            if released:
                raise EscrowAlreadyReleasedError(f"Escrow already released: {escrow_id}")
            
            with self.conn:
                # Unlock from source account
                self.conn.execute(
                    "UPDATE accounts SET locked = locked - ? WHERE account_id = ?",
                    (amount, from_id)
                )
                
                # Add to destination (create if needed)
                cursor = self.conn.execute(
                    "SELECT account_id FROM accounts WHERE account_id = ?",
                    (to_id,)
                )
                if cursor.fetchone():
                    self.conn.execute(
                        "UPDATE accounts SET balance = balance + ? WHERE account_id = ?",
                        (amount, to_id)
                    )
                else:
                    self.conn.execute(
                        "INSERT INTO accounts (account_id, balance, locked, unbonding) VALUES (?, ?, 0, 0)",
                        (to_id, amount)
                    )
                
                # Mark escrow as released
                self.conn.execute(
                    "UPDATE escrows SET released = 1, released_to = ? WHERE escrow_id = ?",
                    (to_id, escrow_id)
                )
                
                # Audit trail
                timestamp = time.time_ns()
                self.conn.execute("""
                    INSERT INTO operations (op_id, account_id, op_type, amount, timestamp_ns, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()),
                    to_id,
                    OpType.RELEASE.value,
                    amount,
                    timestamp,
                    json.dumps({"escrow_id": escrow_id, "from_account": from_id})
                ))
    
    def cancel_escrow(self, escrow_id: str) -> None:
        """
        Cancel escrow and return credits to original account.
        
        Args:
            escrow_id: Escrow to cancel
        
        Raises:
            EscrowNotFoundError: If escrow doesn't exist
            EscrowAlreadyReleasedError: If escrow already released
        """
        with self.lock:
            # Get escrow details
            cursor = self.conn.execute(
                "SELECT account_id, amount, released FROM escrows WHERE escrow_id = ?",
                (escrow_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise EscrowNotFoundError(f"Escrow not found: {escrow_id}")
            
            account_id, amount, released = row
            if released:
                raise EscrowAlreadyReleasedError(f"Escrow already released: {escrow_id}")
            
            with self.conn:
                # Return to balance
                self.conn.execute(
                    "UPDATE accounts SET balance = balance + ?, locked = locked - ? WHERE account_id = ?",
                    (amount, amount, account_id)
                )
                
                # Mark as released (to prevent double-cancel)
                self.conn.execute(
                    "UPDATE escrows SET released = 1, released_to = ? WHERE escrow_id = ?",
                    (account_id, escrow_id)
                )
                
                # Audit trail (negative ESCROW represents cancellation)
                self.conn.execute("""
                    INSERT INTO operations (op_id, account_id, op_type, amount, timestamp_ns, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()),
                    account_id,
                    OpType.ESCROW.value,
                    -amount,
                    time.time_ns(),
                    json.dumps({"escrow_id": escrow_id, "action": "cancel"})
                ))
    
    def get_audit_trail(self, account_id: Optional[str] = None, limit: int = 100) -> List[LedgerOp]:
        """
        Get audit trail of operations.
        
        Args:
            account_id: Filter by account (None for all)
            limit: Maximum number of operations to return
        
        Returns:
            List of LedgerOp objects, newest first
        """
        if account_id:
            cursor = self.conn.execute("""
                SELECT op_id, account_id, op_type, amount, timestamp_ns, metadata_json
                FROM operations
                WHERE account_id = ?
                ORDER BY timestamp_ns DESC
                LIMIT ?
            """, (account_id, limit))
        else:
            cursor = self.conn.execute("""
                SELECT op_id, account_id, op_type, amount, timestamp_ns, metadata_json
                FROM operations
                ORDER BY timestamp_ns DESC
                LIMIT ?
            """, (limit,))
        
        ops = []
        for row in cursor:
            ops.append(LedgerOp(
                op_id=row[0],
                account=row[1],
                operation=OpType(row[2]),
                amount=row[3],
                timestamp=row[4],
                metadata=json.loads(row[5])
            ))
        return ops
