"""Decentralized Identifier (DID) management.

Provides DID creation, resolution, and cryptographic operations
for portable agent identities using did:key and did:peer methods.
"""

import base58
import hashlib
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
import nacl.signing
import nacl.encoding

logger = logging.getLogger(__name__)


@dataclass
class DIDDocument:
    """
    DID Document representation.
    
    Simplified DID Document containing essential identity information.
    """
    id: str  # The DID itself
    public_key: str  # Base58-encoded public key
    verification_method: Dict[str, Any] = field(default_factory=dict)
    authentication: list = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            "@context": ["https://www.w3.org/ns/did/v1"],
            "id": self.id,
            "verificationMethod": [self.verification_method] if self.verification_method else [],
            "authentication": self.authentication if self.authentication else [self.id + "#key-1"]
        }


class DIDManager:
    """
    Manages Decentralized Identifiers for agents.
    
    Supports:
    - did:key method (self-contained, no registry)
    - did:peer method (peer-to-peer identifiers)
    - Signature creation and verification
    """
    
    def __init__(self):
        """Initialize DID manager."""
        # Cache of resolved DID documents
        self.did_cache: Dict[str, DIDDocument] = {}
        
        # Map DIDs to their signing keys
        self.signing_keys: Dict[str, nacl.signing.SigningKey] = {}
    
    def create_did_key(self, ed25519_key: Optional[bytes] = None) -> str:
        """
        Create a did:key identifier from Ed25519 key.
        
        The did:key method embeds the public key in the DID itself,
        making it self-contained and requiring no registry.
        
        Args:
            ed25519_key: Optional 32-byte Ed25519 private key seed.
                        If None, generates a new key.
        
        Returns:
            DID string (did:key:z...)
        """
        # Create or use provided signing key
        if ed25519_key:
            signing_key = nacl.signing.SigningKey(ed25519_key)
        else:
            signing_key = nacl.signing.SigningKey.generate()
        
        # Get public key
        verify_key = signing_key.verify_key
        public_key_bytes = bytes(verify_key)
        
        # Create multicodec prefix for Ed25519 public key (0xed01)
        multicodec_prefix = b'\xed\x01'
        multikey = multicodec_prefix + public_key_bytes
        
        # Encode as base58btc with 'z' prefix
        multibase_key = 'z' + base58.b58encode(multikey).decode('ascii')
        
        # Create DID
        did = f"did:key:{multibase_key}"
        
        # Cache the signing key
        self.signing_keys[did] = signing_key
        
        # Create and cache DID document
        public_key_b58 = base58.b58encode(public_key_bytes).decode('ascii')
        
        doc = DIDDocument(
            id=did,
            public_key=public_key_b58,
            verification_method={
                "id": f"{did}#key-1",
                "type": "Ed25519VerificationKey2020",
                "controller": did,
                "publicKeyBase58": public_key_b58
            }
        )
        self.did_cache[did] = doc
        
        logger.info(f"Created did:key: {did[:50]}...")
        
        return did
    
    def create_did_peer(self, peer_id: str) -> str:
        """
        Create a did:peer identifier from libp2p peer ID.
        
        The did:peer method is designed for peer-to-peer scenarios
        where DIDs are exchanged directly between parties.
        
        Args:
            peer_id: Libp2p peer identifier (multibase encoded)
        
        Returns:
            DID string (did:peer:...)
        """
        # For did:peer, we use method 0 (inception key without doc)
        # Format: did:peer:0<multibase-encoded-key>
        
        # If peer_id is already multibase, use it
        if peer_id.startswith('z'):
            encoded = peer_id
        else:
            # Encode as base58btc
            encoded = 'z' + base58.b58encode(peer_id.encode()).decode('ascii')
        
        did = f"did:peer:0{encoded}"
        
        logger.info(f"Created did:peer: {did[:50]}...")
        
        return did
    
    def resolve_did(self, did: str) -> Optional[DIDDocument]:
        """
        Resolve a DID to its DID Document.
        
        Args:
            did: DID to resolve
        
        Returns:
            DIDDocument if resolvable, None otherwise
        """
        # Check cache first
        if did in self.did_cache:
            return self.did_cache[did]
        
        # Parse DID
        if did.startswith("did:key:"):
            return self._resolve_did_key(did)
        elif did.startswith("did:peer:"):
            return self._resolve_did_peer(did)
        else:
            logger.warning(f"Unsupported DID method: {did}")
            return None
    
    def _resolve_did_key(self, did: str) -> Optional[DIDDocument]:
        """Resolve did:key to DID Document."""
        try:
            # Extract multibase key
            method_specific_id = did.split("did:key:")[1]
            
            if not method_specific_id.startswith('z'):
                logger.error("did:key must use base58btc encoding (z prefix)")
                return None
            
            # Decode multikey
            multikey = base58.b58decode(method_specific_id[1:])
            
            # Check multicodec prefix (0xed01 for Ed25519)
            if multikey[:2] != b'\xed\x01':
                logger.error("did:key must use Ed25519 key")
                return None
            
            # Extract public key
            public_key_bytes = multikey[2:]
            public_key_b58 = base58.b58encode(public_key_bytes).decode('ascii')
            
            # Create DID document
            doc = DIDDocument(
                id=did,
                public_key=public_key_b58,
                verification_method={
                    "id": f"{did}#key-1",
                    "type": "Ed25519VerificationKey2020",
                    "controller": did,
                    "publicKeyBase58": public_key_b58
                }
            )
            
            # Cache it
            self.did_cache[did] = doc
            
            return doc
            
        except Exception as e:
            logger.error(f"Failed to resolve did:key: {e}")
            return None
    
    def _resolve_did_peer(self, did: str) -> Optional[DIDDocument]:
        """Resolve did:peer to DID Document."""
        try:
            # For did:peer:0, the document is minimal
            doc = DIDDocument(
                id=did,
                public_key="",  # Would extract from peer encoding in full implementation
                verification_method={}
            )
            
            # Cache it
            self.did_cache[did] = doc
            
            return doc
            
        except Exception as e:
            logger.error(f"Failed to resolve did:peer: {e}")
            return None
    
    def sign_with_did(self, data: bytes, did: str) -> Optional[bytes]:
        """
        Sign data using the private key associated with a DID.
        
        Args:
            data: Data to sign
            did: DID whose private key should be used
        
        Returns:
            Signature bytes, or None if DID not found or no key available
        """
        if did not in self.signing_keys:
            logger.error(f"No signing key available for DID: {did}")
            return None
        
        try:
            signing_key = self.signing_keys[did]
            
            # Sign the data
            signed = signing_key.sign(data)
            
            # Return just the signature (not the message)
            signature = signed.signature
            
            logger.debug(f"Signed {len(data)} bytes with DID {did[:50]}...")
            
            return signature
            
        except Exception as e:
            logger.error(f"Failed to sign with DID: {e}")
            return None
    
    def verify_did_signature(
        self,
        data: bytes,
        signature: bytes,
        did: str
    ) -> bool:
        """
        Verify a signature against data using a DID's public key.
        
        Args:
            data: Original data that was signed
            signature: Signature to verify
            did: DID whose public key should be used for verification
        
        Returns:
            True if signature is valid
        """
        try:
            # Resolve DID to get public key
            doc = self.resolve_did(did)
            if not doc:
                logger.error(f"Could not resolve DID: {did}")
                return False
            
            # Get public key
            public_key_b58 = doc.public_key
            if not public_key_b58:
                logger.error(f"No public key in DID document: {did}")
                return False
            
            # Decode public key
            public_key_bytes = base58.b58decode(public_key_b58)
            
            # Create verify key
            verify_key = nacl.signing.VerifyKey(public_key_bytes)
            
            # Verify signature
            verify_key.verify(data, signature)
            
            logger.debug(f"Verified signature for DID {did[:50]}...")
            
            return True
            
        except nacl.exceptions.BadSignatureError:
            logger.warning(f"Invalid signature for DID {did}")
            return False
        except Exception as e:
            logger.error(f"Failed to verify signature: {e}")
            return False
    
    def export_did_key(self, did: str) -> Optional[bytes]:
        """
        Export the private key for a DID (for backup/migration).
        
        Args:
            did: DID to export key for
        
        Returns:
            32-byte private key seed, or None if not available
        """
        if did not in self.signing_keys:
            return None
        
        signing_key = self.signing_keys[did]
        # Return the seed (private key)
        return bytes(signing_key)
    
    def import_did_key(self, did: str, private_key: bytes) -> bool:
        """
        Import a private key for an existing DID.
        
        Args:
            did: DID to import key for
            private_key: 32-byte private key seed
        
        Returns:
            True if import successful
        """
        try:
            signing_key = nacl.signing.SigningKey(private_key)
            self.signing_keys[did] = signing_key
            
            logger.info(f"Imported key for DID {did[:50]}...")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to import key: {e}")
            return False
