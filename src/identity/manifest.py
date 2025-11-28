"""Agent manifest management with signatures.

Provides signed manifests for agent capabilities, pricing, and metadata
with verification and registry support.
"""

import json
import hashlib
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
import time

from .did import DIDManager

logger = logging.getLogger(__name__)


@dataclass
class AgentManifest:
    """
    Agent manifest with capabilities and metadata.
    
    Contains agent identity, capabilities, pricing, and performance metrics.
    """
    agent_id: str  # DID of the agent
    capabilities: List[str]  # List of capability tags
    io_schema: Dict[str, Any]  # Input/output schema
    price_per_task: float  # Cost per task execution
    avg_latency_ms: int  # Average latency in milliseconds
    tags: List[str]  # Additional tags for discovery
    pubkey: str  # Base58-encoded public key
    reputation: float = 0.8  # DID-based reputation (0.0-1.0), portable across instances
    signature: str = ""  # Hex-encoded signature
    timestamp_ns: int = 0  # Manifest creation timestamp
    version: str = "1.0"  # Manifest version
    metadata: Dict[str, Any] = field(default_factory=dict)  # Additional metadata
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'AgentManifest':
        """Create from dictionary."""
        return cls(**data)
    
    def compute_hash(self) -> str:
        """
        Compute deterministic hash of manifest (excluding signature).
        
        Returns:
            Hex-encoded SHA256 hash
        """
        # Create canonical representation without signature
        canonical = {
            "agent_id": self.agent_id,
            "capabilities": sorted(self.capabilities),
            "io_schema": self.io_schema,
            "price_per_task": self.price_per_task,
            "avg_latency_ms": self.avg_latency_ms,
            "tags": sorted(self.tags),
            "pubkey": self.pubkey,
            "timestamp_ns": self.timestamp_ns,
            "version": self.version
        }
        
        # Sort keys for determinism
        canonical_json = json.dumps(canonical, sort_keys=True)
        
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()


class ManifestManager:
    """
    Manages agent manifest creation, signing, and verification.
    
    Provides:
    - Manifest creation from agent information
    - Signature generation and verification
    - Manifest publishing to registry
    """
    
    def __init__(self, did_manager: Optional[DIDManager] = None, reputation_tracker: Optional['ReputationTracker'] = None):
        """
        Initialize manifest manager.
        
        Args:
            did_manager: Optional DIDManager for signing/verification
            reputation_tracker: Optional ReputationTracker for DID-based reputation
        """
        self.did_manager = did_manager or DIDManager()
        self.reputation_tracker = reputation_tracker
    
    def create_manifest(
        self,
        agent_id: str,
        capabilities: List[str],
        io_schema: Dict[str, Any],
        price_per_task: float = 0.0,
        avg_latency_ms: int = 1000,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ) -> AgentManifest:
        """
        Create an agent manifest.
        
        Args:
            agent_id: Agent's DID
            capabilities: List of capability identifiers
            io_schema: JSON schema for input/output
            price_per_task: Cost per task execution
            avg_latency_ms: Average latency in milliseconds
            tags: Additional discovery tags
            metadata: Additional metadata
        
        Returns:
            AgentManifest (unsigned)
        """
        # Resolve DID to get public key
        doc = self.did_manager.resolve_did(agent_id)
        if not doc:
            raise ValueError(f"Cannot resolve agent DID: {agent_id}")
        
        # Get reputation from tracker if available
        reputation = 0.8  # Default initial reputation
        if self.reputation_tracker:
            reputation = self.reputation_tracker.get_reputation(agent_id)
            if reputation == 0.0:  # No history, use default
                reputation = 0.8
        
        # Create manifest
        manifest = AgentManifest(
            agent_id=agent_id,
            capabilities=capabilities,
            io_schema=io_schema,
            price_per_task=price_per_task,
            avg_latency_ms=avg_latency_ms,
            tags=tags or [],
            pubkey=doc.public_key,
            reputation=reputation,
            timestamp_ns=int(time.time() * 1_000_000_000),
            metadata=metadata or {}
        )
        
        logger.info(
            f"Created manifest for agent {agent_id[:30]}... "
            f"with {len(capabilities)} capabilities and reputation {reputation:.2f}"
        )
        
        return manifest
    
    def sign_manifest(
        self,
        manifest: AgentManifest,
        agent_did: Optional[str] = None
    ) -> AgentManifest:
        """
        Sign a manifest with agent's private key.
        
        Args:
            manifest: Manifest to sign
            agent_did: Optional DID (defaults to manifest.agent_id)
        
        Returns:
            Signed manifest
        """
        did = agent_did or manifest.agent_id
        
        # Compute manifest hash
        manifest_hash = manifest.compute_hash()
        
        # Sign the hash
        signature = self.did_manager.sign_with_did(
            manifest_hash.encode('utf-8'),
            did
        )
        
        if not signature:
            raise ValueError(f"Failed to sign manifest with DID: {did}")
        
        # Set signature
        manifest.signature = signature.hex()
        
        logger.info(f"Signed manifest for agent {did[:30]}...")
        
        return manifest
    
    def verify_manifest(self, manifest: AgentManifest) -> bool:
        """
        Verify manifest signature.
        
        Args:
            manifest: Manifest to verify
        
        Returns:
            True if signature is valid
        """
        if not manifest.signature:
            logger.warning("Manifest has no signature")
            return False
        
        try:
            # Compute expected hash
            manifest_hash = manifest.compute_hash()
            
            # Decode signature
            signature = bytes.fromhex(manifest.signature)
            
            # Verify signature
            is_valid = self.did_manager.verify_did_signature(
                manifest_hash.encode('utf-8'),
                signature,
                manifest.agent_id
            )
            
            if is_valid:
                logger.debug(f"Verified manifest for {manifest.agent_id[:30]}...")
            else:
                logger.warning(f"Invalid signature for {manifest.agent_id[:30]}...")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Failed to verify manifest: {e}")
            return False
    
    def publish_manifest(
        self,
        manifest: AgentManifest,
        registry: Optional['ManifestRegistry'] = None
    ) -> bool:
        """
        Publish manifest to registry.
        
        Args:
            manifest: Manifest to publish
            registry: Optional ManifestRegistry instance
        
        Returns:
            True if published successfully
        """
        # Verify signature first
        if not self.verify_manifest(manifest):
            logger.error("Cannot publish manifest with invalid signature")
            return False
        
        # Publish to registry if provided
        if registry:
            try:
                registry.register(manifest)
                logger.info(f"Published manifest to registry: {manifest.agent_id[:30]}...")
                return True
            except Exception as e:
                logger.error(f"Failed to publish manifest: {e}")
                return False
        
        logger.warning("No registry provided for publishing")
        return False
