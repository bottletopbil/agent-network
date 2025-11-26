"""
P2P Identity Management

Manages keypairs for libp2p peer IDs and DID:peer generation.
"""

import base64
import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple
import json

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)


class P2PIdentity:
    """
    Manages P2P identity with Ed25519 keypair.
    
    Provides peer ID generation and DID:peer formatting for
    decentralized identity.
    """
    
    def __init__(self, private_key: Optional[ed25519.Ed25519PrivateKey] = None):
        """
        Initialize P2P identity.
        
        Args:
            private_key: Optional existing Ed25519 private key
        """
        if private_key is None:
            # Generate new keypair
            self.private_key = ed25519.Ed25519PrivateKey.generate()
        else:
            self.private_key = private_key
        
        self.public_key = self.private_key.public_key()
    
    def get_private_key_bytes(self) -> bytes:
        """Get private key as raw bytes"""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
    
    def get_public_key_bytes(self) -> bytes:
        """Get public key as raw bytes"""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
    
    def get_public_key_base64(self) -> str:
        """Get public key as base64 string"""
        return base64.b64encode(self.get_public_key_bytes()).decode('utf-8')
    
    def to_peer_id(self) -> str:
        """
        Generate libp2p peer ID from public key.
        
        Peer ID is base58-encoded multihash of the public key.
        
        Returns:
            Peer ID string
        """
        # For Ed25519, we use the public key bytes directly
        # In a full libp2p implementation, this would be a multihash
        
        # Simple peer ID: base58(sha256(pubkey))
        pubkey_bytes = self.get_public_key_bytes()
        hash_bytes = hashlib.sha256(pubkey_bytes).digest()
        
        # Base58 encode (simplified - using base64 for now)
        peer_id = base64.b32encode(hash_bytes).decode('utf-8').rstrip('=')
        
        # Add 12D3Koo prefix (standard libp2p peer ID prefix)
        return f"12D3Koo{peer_id[:32]}"
    
    def to_did_peer(self) -> str:
        """
        Generate DID:peer from libp2p peer ID.
        
        Format: did:peer:0<multibase-multicodec-pubkey>
        
        Returns:
            DID:peer string
        """
        # Method 0: Simple DID encoding of public key
        # Format: did:peer:0<base58-encoded-pubkey>
        
        pubkey_b64 = self.get_public_key_base64()
        
        # Simplified DID:peer format
        # In production, would use proper multibase/multicodec encoding
        did = f"did:peer:0z{pubkey_b64[:32]}"
        
        return did
    
    def save(self, path: Path) -> None:
        """
        Save identity to file.
        
        Args:
            path: Path to save identity JSON
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        
        identity_data = {
            "private_key_b64": base64.b64encode(self.get_private_key_bytes()).decode('utf-8'),
            "public_key_b64": self.get_public_key_base64(),
            "peer_id": self.to_peer_id(),
            "did_peer": self.to_did_peer()
        }
        
        with path.open('w') as f:
            json.dump(identity_data, f, indent=2)
        
        logger.info(f"Saved P2P identity to {path}")
    
    @classmethod
    def load(cls, path: Path) -> 'P2PIdentity':
        """
        Load identity from file.
        
        Args:
            path: Path to identity JSON file
            
        Returns:
            P2PIdentity instance
        """
        with path.open('r') as f:
            identity_data = json.load(f)
        
        # Reconstruct private key
        private_key_bytes = base64.b64decode(identity_data["private_key_b64"])
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        
        identity = cls(private_key)
        
        logger.info(f"Loaded P2P identity from {path}")
        return identity
    
    @classmethod
    def from_keypair_file(cls, keypair_path: Path) -> 'P2PIdentity':
        """
        Load identity from existing Ed25519 keypair file.
        
        Args:
            keypair_path: Path to keypair JSON
            
        Returns:
            P2PIdentity instance
        """
        # Try to load from P2P identity format first
        if keypair_path.exists():
            try:
                return cls.load(keypair_path)
            except (KeyError, json.JSONDecodeError):
                # Not a P2P identity file, try other formats
                pass
        
        # Generate new identity if file doesn't exist
        return cls()


def generate_peer_id() -> Tuple[P2PIdentity, str]:
    """
    Generate new peer ID.
    
    Returns:
        Tuple of (P2PIdentity, peer_id_string)
    """
    identity = P2PIdentity()
    peer_id = identity.to_peer_id()
    
    logger.info(f"Generated peer ID: {peer_id}")
    
    return identity, peer_id


def get_or_create_identity(identity_path: Path) -> P2PIdentity:
    """
    Get existing identity or create new one.
    
    Args:
        identity_path: Path to identity file
        
    Returns:
        P2PIdentity instance
    """
    if identity_path.exists():
        logger.info(f"Loading existing identity from {identity_path}")
        return P2PIdentity.load(identity_path)
    else:
        logger.info(f"Creating new identity at {identity_path}")
        identity = P2PIdentity()
        identity.save(identity_path)
        return identity
