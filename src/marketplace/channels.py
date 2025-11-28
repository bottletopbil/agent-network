"""Phase 19.3 - Off-Chain Payment Channels

This module implements payment channels for off-chain payments to reduce
on-chain transaction costs.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
import hashlib
import uuid


@dataclass
class PaymentChannel:
    """Represents an off-chain payment channel between two parties."""
    channel_id: str
    sender: str
    receiver: str
    capacity: float
    nonce: int = 0
    sender_balance: float = field(init=False)
    receiver_balance: float = field(init=False)
    
    def __post_init__(self):
        """Initialize balances - sender starts with full capacity."""
        self.sender_balance = self.capacity
        self.receiver_balance = 0.0


@dataclass
class Payment:
    """Represents a payment within a channel."""
    channel_id: str
    amount: float
    nonce: int
    signature: str


class ChannelManager:
    """Manages off-chain payment channels."""
    
    def __init__(self):
        self.channels: Dict[str, PaymentChannel] = {}
        # Track total deposits per user for settlement
        self.deposits: Dict[str, float] = {}
    
    def open_channel(self, sender: str, receiver: str, deposit: float) -> str:
        """
        Open a new payment channel.
        
        Args:
            sender: Address of the sender
            receiver: Address of the receiver
            deposit: Initial deposit amount (channel capacity)
        
        Returns:
            channel_id: Unique identifier for the channel
        """
        if deposit <= 0:
            raise ValueError("Deposit must be positive")
        
        channel_id = str(uuid.uuid4())
        channel = PaymentChannel(
            channel_id=channel_id,
            sender=sender,
            receiver=receiver,
            capacity=deposit
        )
        
        self.channels[channel_id] = channel
        
        # Track deposit for settlement
        self.deposits[sender] = self.deposits.get(sender, 0.0) + deposit
        
        return channel_id
    
    def send_payment(
        self, 
        channel_id: str, 
        amount: float, 
        nonce: int, 
        signature: str
    ) -> bool:
        """
        Send a payment through a channel.
        
        Args:
            channel_id: ID of the channel
            amount: Amount to send
            nonce: Nonce for replay protection (must be > current nonce)
            signature: Cryptographic signature of the payment
        
        Returns:
            True if payment was successful
        
        Raises:
            ValueError: If channel doesn't exist or payment is invalid
        """
        if channel_id not in self.channels:
            raise ValueError(f"Channel {channel_id} does not exist")
        
        channel = self.channels[channel_id]
        
        # Validate nonce (must be strictly increasing)
        if nonce <= channel.nonce:
            raise ValueError(
                f"Invalid nonce: {nonce} (current: {channel.nonce})"
            )
        
        # Validate amount
        if amount <= 0:
            raise ValueError("Amount must be positive")
        
        if channel.sender_balance < amount:
            raise ValueError(
                f"Insufficient balance: {channel.sender_balance} < {amount}"
            )
        
        # Create payment object for verification
        payment = Payment(
            channel_id=channel_id,
            amount=amount,
            nonce=nonce,
            signature=signature
        )
        
        # Verify signature
        if not self.verify_payment(payment):
            raise ValueError("Invalid payment signature")
        
        # Update balances
        channel.sender_balance -= amount
        channel.receiver_balance += amount
        channel.nonce = nonce
        
        return True
    
    def close_channel(self, channel_id: str) -> Tuple[str, str, float, float]:
        """
        Close a channel and settle final balances.
        
        Args:
            channel_id: ID of the channel to close
        
        Returns:
            Settlement info: (sender, receiver, sender_amount, receiver_amount)
        
        Raises:
            ValueError: If channel doesn't exist
        """
        if channel_id not in self.channels:
            raise ValueError(f"Channel {channel_id} does not exist")
        
        channel = self.channels[channel_id]
        
        # Prepare settlement
        settlement = (
            channel.sender,
            channel.receiver,
            channel.sender_balance,
            channel.receiver_balance
        )
        
        # Update deposits (return unused amount to sender)
        if channel.sender in self.deposits:
            self.deposits[channel.sender] -= channel.capacity
            if self.deposits[channel.sender] <= 0:
                del self.deposits[channel.sender]
        
        # Remove channel
        del self.channels[channel_id]
        
        return settlement
    
    def verify_payment(self, payment: Payment) -> bool:
        """
        Verify a payment signature.
        
        This is a simplified implementation. In production, this would verify
        cryptographic signatures using asymmetric cryptography.
        
        Args:
            payment: Payment to verify
        
        Returns:
            True if signature is valid
        """
        # Create expected signature (simplified)
        # In production: verify actual cryptographic signature
        message = f"{payment.channel_id}:{payment.amount}:{payment.nonce}"
        expected_sig = hashlib.sha256(message.encode()).hexdigest()
        
        return payment.signature == expected_sig
    
    def get_channel(self, channel_id: str) -> Optional[PaymentChannel]:
        """Get channel by ID."""
        return self.channels.get(channel_id)
    
    def get_channels_by_sender(self, sender: str) -> list[PaymentChannel]:
        """Get all channels where sender is the sender."""
        return [
            ch for ch in self.channels.values() 
            if ch.sender == sender
        ]
    
    def get_channels_by_receiver(self, receiver: str) -> list[PaymentChannel]:
        """Get all channels where receiver is the receiver."""
        return [
            ch for ch in self.channels.values() 
            if ch.receiver == receiver
        ]


def create_payment_signature(channel_id: str, amount: float, nonce: int) -> str:
    """
    Helper function to create a payment signature.
    
    This is a simplified implementation for testing. In production, this would
    use proper asymmetric cryptography with private keys.
    
    Args:
        channel_id: Channel ID
        amount: Payment amount
        nonce: Payment nonce
    
    Returns:
        Signature string
    """
    message = f"{channel_id}:{amount}:{nonce}"
    return hashlib.sha256(message.encode()).hexdigest()
