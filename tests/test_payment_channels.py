"""Tests for Phase 19.3 - Payment Channels"""

import pytest
from src.marketplace.channels import (
    PaymentChannel,
    ChannelManager,
    Payment,
    create_payment_signature
)


@pytest.fixture
def manager():
    """Create a fresh ChannelManager for each test."""
    return ChannelManager()


class TestPaymentChannel:
    """Test PaymentChannel dataclass."""
    
    def test_channel_creation(self):
        """Test creating a payment channel."""
        channel = PaymentChannel(
            channel_id="test-123",
            sender="alice",
            receiver="bob",
            capacity=100.0
        )
        
        assert channel.channel_id == "test-123"
        assert channel.sender == "alice"
        assert channel.receiver == "bob"
        assert channel.capacity == 100.0
        assert channel.nonce == 0
        assert channel.sender_balance == 100.0
        assert channel.receiver_balance == 0.0
    
    def test_channel_balances_initialized(self):
        """Test that balances are properly initialized."""
        channel = PaymentChannel(
            channel_id="ch1",
            sender="alice",
            receiver="bob",
            capacity=50.0
        )
        
        # Sender starts with full capacity
        assert channel.sender_balance == channel.capacity
        assert channel.receiver_balance == 0.0


class TestChannelManager:
    """Test ChannelManager functionality."""
    
    def test_open_channel(self, manager):
        """Test opening a new channel."""
        channel_id = manager.open_channel(
            sender="alice",
            receiver="bob",
            deposit=100.0
        )
        
        assert channel_id is not None
        assert channel_id in manager.channels
        
        channel = manager.get_channel(channel_id)
        assert channel.sender == "alice"
        assert channel.receiver == "bob"
        assert channel.capacity == 100.0
        assert channel.sender_balance == 100.0
        assert channel.receiver_balance == 0.0
    
    def test_open_channel_invalid_deposit(self, manager):
        """Test that opening a channel with invalid deposit fails."""
        with pytest.raises(ValueError, match="Deposit must be positive"):
            manager.open_channel("alice", "bob", 0.0)
        
        with pytest.raises(ValueError, match="Deposit must be positive"):
            manager.open_channel("alice", "bob", -10.0)
    
    def test_send_payment(self, manager):
        """Test sending a payment through a channel."""
        channel_id = manager.open_channel("alice", "bob", 100.0)
        
        # Create signature
        sig = create_payment_signature(channel_id, 30.0, 1)
        
        # Send payment
        result = manager.send_payment(channel_id, 30.0, 1, sig)
        assert result is True
        
        # Check balances updated
        channel = manager.get_channel(channel_id)
        assert channel.sender_balance == 70.0
        assert channel.receiver_balance == 30.0
        assert channel.nonce == 1
    
    def test_send_multiple_payments(self, manager):
        """Test sending multiple payments through a channel."""
        channel_id = manager.open_channel("alice", "bob", 100.0)
        
        # First payment
        sig1 = create_payment_signature(channel_id, 20.0, 1)
        manager.send_payment(channel_id, 20.0, 1, sig1)
        
        # Second payment
        sig2 = create_payment_signature(channel_id, 30.0, 2)
        manager.send_payment(channel_id, 30.0, 2, sig2)
        
        # Third payment
        sig3 = create_payment_signature(channel_id, 10.0, 3)
        manager.send_payment(channel_id, 10.0, 3, sig3)
        
        channel = manager.get_channel(channel_id)
        assert channel.sender_balance == 40.0  # 100 - 20 - 30 - 10
        assert channel.receiver_balance == 60.0
        assert channel.nonce == 3
    
    def test_send_payment_insufficient_balance(self, manager):
        """Test that sending more than balance fails."""
        channel_id = manager.open_channel("alice", "bob", 50.0)
        
        sig = create_payment_signature(channel_id, 60.0, 1)
        
        with pytest.raises(ValueError, match="Insufficient balance"):
            manager.send_payment(channel_id, 60.0, 1, sig)
    
    def test_send_payment_invalid_nonce(self, manager):
        """Test that invalid nonces are rejected."""
        channel_id = manager.open_channel("alice", "bob", 100.0)
        
        # Send first payment (nonce=1)
        sig1 = create_payment_signature(channel_id, 10.0, 1)
        manager.send_payment(channel_id, 10.0, 1, sig1)
        
        # Try to send with same nonce (replay attack)
        sig2 = create_payment_signature(channel_id, 10.0, 1)
        with pytest.raises(ValueError, match="Invalid nonce"):
            manager.send_payment(channel_id, 10.0, 1, sig2)
        
        # Try to send with lower nonce
        sig3 = create_payment_signature(channel_id, 10.0, 0)
        with pytest.raises(ValueError, match="Invalid nonce"):
            manager.send_payment(channel_id, 10.0, 0, sig3)
    
    def test_send_payment_invalid_signature(self, manager):
        """Test that invalid signatures are rejected."""
        channel_id = manager.open_channel("alice", "bob", 100.0)
        
        # Use wrong signature
        with pytest.raises(ValueError, match="Invalid payment signature"):
            manager.send_payment(channel_id, 30.0, 1, "invalid-sig")
    
    def test_send_payment_channel_not_found(self, manager):
        """Test sending payment to non-existent channel."""
        with pytest.raises(ValueError, match="does not exist"):
            sig = create_payment_signature("fake-id", 10.0, 1)
            manager.send_payment("fake-id", 10.0, 1, sig)
    
    def test_send_payment_negative_amount(self, manager):
        """Test that negative amounts are rejected."""
        channel_id = manager.open_channel("alice", "bob", 100.0)
        
        sig = create_payment_signature(channel_id, -10.0, 1)
        with pytest.raises(ValueError, match="Amount must be positive"):
            manager.send_payment(channel_id, -10.0, 1, sig)
    
    def test_close_channel(self, manager):
        """Test closing a channel and settling balances."""
        channel_id = manager.open_channel("alice", "bob", 100.0)
        
        # Send some payments
        sig1 = create_payment_signature(channel_id, 30.0, 1)
        manager.send_payment(channel_id, 30.0, 1, sig1)
        
        sig2 = create_payment_signature(channel_id, 20.0, 2)
        manager.send_payment(channel_id, 20.0, 2, sig2)
        
        # Close channel
        settlement = manager.close_channel(channel_id)
        
        sender, receiver, sender_amount, receiver_amount = settlement
        assert sender == "alice"
        assert receiver == "bob"
        assert sender_amount == 50.0  # 100 - 30 - 20
        assert receiver_amount == 50.0  # 30 + 20
        
        # Channel should be removed
        assert channel_id not in manager.channels
        assert manager.get_channel(channel_id) is None
    
    def test_close_channel_not_found(self, manager):
        """Test closing non-existent channel."""
        with pytest.raises(ValueError, match="does not exist"):
            manager.close_channel("fake-id")
    
    def test_verify_payment(self, manager):
        """Test payment verification."""
        channel_id = manager.open_channel("alice", "bob", 100.0)
        
        # Create valid payment
        valid_sig = create_payment_signature(channel_id, 30.0, 1)
        valid_payment = Payment(
            channel_id=channel_id,
            amount=30.0,
            nonce=1,
            signature=valid_sig
        )
        
        assert manager.verify_payment(valid_payment) is True
        
        # Create invalid payment (wrong signature)
        invalid_payment = Payment(
            channel_id=channel_id,
            amount=30.0,
            nonce=1,
            signature="wrong-signature"
        )
        
        assert manager.verify_payment(invalid_payment) is False
    
    def test_get_channels_by_sender(self, manager):
        """Test retrieving channels by sender."""
        ch1 = manager.open_channel("alice", "bob", 100.0)
        ch2 = manager.open_channel("alice", "charlie", 50.0)
        ch3 = manager.open_channel("bob", "alice", 75.0)
        
        alice_channels = manager.get_channels_by_sender("alice")
        assert len(alice_channels) == 2
        assert all(ch.sender == "alice" for ch in alice_channels)
        
        bob_channels = manager.get_channels_by_sender("bob")
        assert len(bob_channels) == 1
        assert bob_channels[0].sender == "bob"
    
    def test_get_channels_by_receiver(self, manager):
        """Test retrieving channels by receiver."""
        ch1 = manager.open_channel("alice", "bob", 100.0)
        ch2 = manager.open_channel("charlie", "bob", 50.0)
        ch3 = manager.open_channel("bob", "alice", 75.0)
        
        bob_received = manager.get_channels_by_receiver("bob")
        assert len(bob_received) == 2
        assert all(ch.receiver == "bob" for ch in bob_received)
        
        alice_received = manager.get_channels_by_receiver("alice")
        assert len(alice_received) == 1
        assert alice_received[0].receiver == "alice"
    
    def test_deposits_tracking(self, manager):
        """Test that deposits are tracked correctly."""
        # Open channel
        channel_id = manager.open_channel("alice", "bob", 100.0)
        assert manager.deposits["alice"] == 100.0
        
        # Open another channel from same sender
        channel_id2 = manager.open_channel("alice", "charlie", 50.0)
        assert manager.deposits["alice"] == 150.0
        
        # Close first channel
        manager.close_channel(channel_id)
        assert manager.deposits["alice"] == 50.0
        
        # Close second channel
        manager.close_channel(channel_id2)
        assert "alice" not in manager.deposits


class TestPaymentSignature:
    """Test payment signature creation."""
    
    def test_create_signature_deterministic(self):
        """Test that signature creation is deterministic."""
        sig1 = create_payment_signature("ch1", 100.0, 1)
        sig2 = create_payment_signature("ch1", 100.0, 1)
        
        assert sig1 == sig2
    
    def test_different_params_different_signature(self):
        """Test that different parameters create different signatures."""
        sig1 = create_payment_signature("ch1", 100.0, 1)
        sig2 = create_payment_signature("ch1", 100.0, 2)  # Different nonce
        sig3 = create_payment_signature("ch1", 50.0, 1)   # Different amount
        sig4 = create_payment_signature("ch2", 100.0, 1)  # Different channel
        
        assert sig1 != sig2
        assert sig1 != sig3
        assert sig1 != sig4
        assert sig2 != sig3


class TestEndToEnd:
    """End-to-end payment channel scenarios."""
    
    def test_complete_channel_lifecycle(self, manager):
        """Test complete lifecycle: open, payments, close."""
        # Alice opens channel to Bob with 1000 tokens
        channel_id = manager.open_channel("alice", "bob", 1000.0)
        
        # Alice sends multiple payments to Bob
        payments = [
            (100.0, 1),
            (50.0, 2),
            (200.0, 3),
            (150.0, 4),
            (75.0, 5),
        ]
        
        for amount, nonce in payments:
            sig = create_payment_signature(channel_id, amount, nonce)
            manager.send_payment(channel_id, amount, nonce, sig)
        
        # Check intermediate state
        channel = manager.get_channel(channel_id)
        total_sent = sum(amt for amt, _ in payments)
        assert channel.sender_balance == 1000.0 - total_sent
        assert channel.receiver_balance == total_sent
        
        # Close and settle
        sender, receiver, sender_final, receiver_final = manager.close_channel(channel_id)
        
        assert sender == "alice"
        assert receiver == "bob"
        assert sender_final == 1000.0 - total_sent
        assert receiver_final == total_sent
        assert sender_final + receiver_final == 1000.0  # Conservation
    
    def test_multiple_concurrent_channels(self, manager):
        """Test multiple channels operating concurrently."""
        # Alice has channels with Bob and Charlie
        ch_ab = manager.open_channel("alice", "bob", 500.0)
        ch_ac = manager.open_channel("alice", "charlie", 300.0)
        
        # Bob has channel with Charlie
        ch_bc = manager.open_channel("bob", "charlie", 200.0)
        
        # Payments across channels
        sig1 = create_payment_signature(ch_ab, 100.0, 1)
        manager.send_payment(ch_ab, 100.0, 1, sig1)
        
        sig2 = create_payment_signature(ch_ac, 50.0, 1)
        manager.send_payment(ch_ac, 50.0, 1, sig2)
        
        sig3 = create_payment_signature(ch_bc, 75.0, 1)
        manager.send_payment(ch_bc, 75.0, 1, sig3)
        
        # Verify all channels maintain correct state
        assert manager.get_channel(ch_ab).sender_balance == 400.0
        assert manager.get_channel(ch_ab).receiver_balance == 100.0
        
        assert manager.get_channel(ch_ac).sender_balance == 250.0
        assert manager.get_channel(ch_ac).receiver_balance == 50.0
        
        assert manager.get_channel(ch_bc).sender_balance == 125.0
        assert manager.get_channel(ch_bc).receiver_balance == 75.0
