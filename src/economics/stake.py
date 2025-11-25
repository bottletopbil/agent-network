"""
Stake System: staking, unbonding, and stake management.

Integrates with CreditLedger to manage verifier stakes with time-locked unbonding.
"""

import sqlite3
import threading
import uuid
import time
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

from economics.ledger import CreditLedger, InsufficientBalanceError


class InsufficientStakeError(Exception):
    """Raised when account has insufficient staked amount"""
    pass


@dataclass
class UnbondingRecord:
    """Record of credits in unbonding period"""
    unbonding_id: str
    account_id: str
    amount: int
    started_at: int       # Nanosecond timestamp
    completed_at: int     # Nanosecond timestamp when unbonding completes
    completed: bool       # Whether unbonding has been finalized


class StakeManager:
    """
    Manage verifier stakes with unbonding periods.
    
    Integrates with CreditLedger to track staked (locked) and unbonding credits.
    """
    
    def __init__(self, ledger: CreditLedger, unbonding_days: float = 7.0):
        """
        Initialize stake manager.
        
        Args:
            ledger: CreditLedger instance
            unbonding_days: Days required for unbonding (default 7)
        """
        self.ledger = ledger
        self.unbonding_days = unbonding_days
        self.unbonding_seconds = int(unbonding_days * 24 * 3600)
        
        # Use same database as ledger for consistency
        self.conn = ledger.conn
        self.lock = ledger.lock
        self._init_schema()
    
    def _init_schema(self):
        """Initialize unbonding tracking table"""
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS unbonding (
                    unbonding_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    started_at INTEGER NOT NULL,
                    completed_at INTEGER NOT NULL,
                    completed BOOLEAN NOT NULL DEFAULT 0
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_unbonding_account ON unbonding(account_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_unbonding_completed ON unbonding(completed)")
    
    def stake(self, account_id: str, amount: int) -> None:
        """
        Stake credits (move from balance to locked).
        
        Args:
            account_id: Account to stake from
            amount: Amount to stake
        
        Raises:
            InsufficientBalanceError: If insufficient balance
        """
        if amount <= 0:
            raise ValueError(f"Stake amount must be positive: {amount}")
        
        with self.lock:
            # Check balance
            balance = self.ledger.get_balance(account_id)
            if balance < amount:
                raise InsufficientBalanceError(
                    f"Insufficient balance to stake: {balance} < {amount}"
                )
            
            with self.conn:
                # Move from balance to locked using direct SQL
                # (ledger doesn't have a direct stake method)
                self.conn.execute(
                    "UPDATE accounts SET balance = balance - ?, locked = locked + ? WHERE account_id = ?",
                    (amount, amount, account_id)
                )
                
                # Record in operations audit trail
                self.conn.execute("""
                    INSERT INTO operations (op_id, account_id, op_type, amount, timestamp_ns, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()),
                    account_id,
                    "STAKE",
                    amount,
                    time.time_ns(),
                    '{"action": "stake"}'
                ))
    
    def unstake(self, account_id: str, amount: int) -> str:
        """
        Begin unstaking (move from locked to unbonding).
        
        Args:
            account_id: Account to unstake from
            amount: Amount to unstake
        
        Returns:
            unbonding_id for tracking
        
        Raises:
            InsufficientStakeError: If insufficient staked amount
        """
        if amount <= 0:
            raise ValueError(f"Unstake amount must be positive: {amount}")
        
        with self.lock:
            # Check staked amount
            staked = self.get_staked_amount(account_id)
            if staked < amount:
                raise InsufficientStakeError(
                    f"Insufficient stake to unstake: {staked} < {amount}"
                )
            
            # Calculate completion time
            started_at = time.time_ns()
            completed_at = started_at + (self.unbonding_seconds * 1_000_000_000)
            
            unbonding_id = str(uuid.uuid4())
            
            with self.conn:
                # Move from locked to unbonding
                self.conn.execute(
                    "UPDATE accounts SET locked = locked - ?, unbonding = unbonding + ? WHERE account_id = ?",
                    (amount, amount, account_id)
                )
                
                # Create unbonding record
                self.conn.execute("""
                    INSERT INTO unbonding (unbonding_id, account_id, amount, started_at, completed_at, completed)
                    VALUES (?, ?, ?, ?, ?, 0)
                """, (unbonding_id, account_id, amount, started_at, completed_at))
                
                # Audit trail
                self.conn.execute("""
                    INSERT INTO operations (op_id, account_id, op_type, amount, timestamp_ns, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()),
                    account_id,
                    "UNSTAKE",
                    amount,
                    started_at,
                    f'{{"unbonding_id": "{unbonding_id}", "completed_at": {completed_at}}}'
                ))
            
            return unbonding_id
    
    def complete_unbonding(self, account_id: str) -> int:
        """
        Complete all eligible unbonding periods for an account.
        
        Args:
            account_id: Account to complete unbonding for
        
        Returns:
            Total amount released from unbonding
        """
        with self.lock:
            current_time = time.time_ns()
            
            # Find completed unbonding records
            cursor = self.conn.execute("""
                SELECT unbonding_id, amount
                FROM unbonding
                WHERE account_id = ? AND completed = 0 AND completed_at <= ?
            """, (account_id, current_time))
            
            records = cursor.fetchall()
            if not records:
                return 0
            
            total_released = sum(amount for _, amount in records)
            
            with self.conn:
                # Move from unbonding to balance
                self.conn.execute(
                    "UPDATE accounts SET unbonding = unbonding - ?, balance = balance + ? WHERE account_id = ?",
                    (total_released, total_released, account_id)
                )
                
                # Mark unbonding records as completed
                for unbonding_id, amount in records:
                    self.conn.execute(
                        "UPDATE unbonding SET completed = 1 WHERE unbonding_id = ?",
                        (unbonding_id,)
                    )
                    
                    # Audit trail
                    self.conn.execute("""
                        INSERT INTO operations (op_id, account_id, op_type, amount, timestamp_ns, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        str(uuid.uuid4()),
                        account_id,
                        "COMPLETE_UNBONDING",
                        amount,
                        current_time,
                        f'{{"unbonding_id": "{unbonding_id}"}}'
                    ))
            
            return total_released
    
    def get_staked_amount(self, account_id: str) -> int:
        """
        Get currently staked (locked) amount.
        
        Args:
            account_id: Account to query
        
        Returns:
            Staked amount (0 if account doesn't exist)
        """
        account = self.ledger.get_account(account_id)
        return account.locked if account else 0
    
    def get_unbonding_amount(self, account_id: str) -> int:
        """
        Get amount currently unbonding.
        
        Args:
            account_id: Account to query
        
        Returns:
            Unbonding amount (0 if account doesn't exist)
        """
        account = self.ledger.get_account(account_id)
        return account.unbonding if account else 0
    
    def get_unbonding_records(self, account_id: str, include_completed: bool = False) -> List[UnbondingRecord]:
        """
        Get unbonding records for an account.
        
        Args:
            account_id: Account to query
            include_completed: Whether to include already-completed records
        
        Returns:
            List of unbonding records
        """
        if include_completed:
            cursor = self.conn.execute("""
                SELECT unbonding_id, account_id, amount, started_at, completed_at, completed
                FROM unbonding
                WHERE account_id = ?
                ORDER BY started_at DESC
            """, (account_id,))
        else:
            cursor = self.conn.execute("""
                SELECT unbonding_id, account_id, amount, started_at, completed_at, completed
                FROM unbonding
                WHERE account_id = ? AND completed = 0
                ORDER BY started_at DESC
            """, (account_id,))
        
        records = []
        for row in cursor:
            records.append(UnbondingRecord(
                unbonding_id=row[0],
                account_id=row[1],
                amount=row[2],
                started_at=row[3],
                completed_at=row[4],
                completed=bool(row[5])
            ))
        return records
