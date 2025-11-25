"""
Ledger operations: types, dataclasses, and validation rules.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any


class OpType(Enum):
    """Types of ledger operations"""
    MINT = "MINT"           # Create new credits
    TRANSFER = "TRANSFER"   # Transfer between accounts
    ESCROW = "ESCROW"       # Lock credits in escrow
    RELEASE = "RELEASE"     # Release escrowed credits
    SLASH = "SLASH"         # Slash credits as penalty


@dataclass
class LedgerOp:
    """Single operation in the ledger audit trail"""
    op_id: str                  # UUID
    account: str                # Account ID
    operation: OpType           # Type of operation
    amount: int                 # Amount in smallest credit unit
    timestamp: int              # Timestamp in nanoseconds
    metadata: Dict[str, Any]    # Operation-specific metadata


def validate_amount(amount: int) -> None:
    """Validate that amount is a positive integer"""
    if not isinstance(amount, int):
        raise ValueError(f"Amount must be integer, got {type(amount)}")
    if amount <= 0:
        raise ValueError(f"Amount must be positive, got {amount}")


def validate_account_id(account_id: str) -> None:
    """Validate account ID format"""
    if not isinstance(account_id, str):
        raise ValueError(f"Account ID must be string, got {type(account_id)}")
    if not account_id or not account_id.strip():
        raise ValueError("Account ID cannot be empty")


def validate_operation(op: LedgerOp) -> None:
    """Validate a ledger operation has required fields"""
    validate_account_id(op.account)
    validate_amount(op.amount)
    
    # Check required metadata per operation type
    if op.operation == OpType.TRANSFER:
        if "to_account" not in op.metadata:
            raise ValueError("TRANSFER requires to_account in metadata")
    elif op.operation == OpType.ESCROW:
        if "escrow_id" not in op.metadata:
            raise ValueError("ESCROW requires escrow_id in metadata")
    elif op.operation == OpType.RELEASE:
        if "escrow_id" not in op.metadata:
            raise ValueError("RELEASE requires escrow_id in metadata")
        if "to_account" not in op.metadata:
            raise ValueError("RELEASE requires to_account in metadata")
