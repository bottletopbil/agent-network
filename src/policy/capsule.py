"""
Policy Capsules & Versioning

Provides cryptographically signed policy distributions with conformance guarantees.
Capsules contain the policy WASM hash, schema version, conformance test results,
and a signature from the policy author.
"""

import json
import hashlib
import logging
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class PolicyCapsule:
    """
    A cryptographically signed policy distribution unit.
    
    Contains:
    - policy_engine_hash: SHA256 of the WASM policy
    - policy_schema_version: Semantic version of the policy schema
    - conformance_vector: List of passed conformance test IDs
    - signature: Capsule signed by policy author
    - metadata: Additional metadata (author, timestamp, etc.)
    """
    policy_engine_hash: str
    policy_schema_version: str
    conformance_vector: List[str]
    signature: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert capsule to dictionary"""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert capsule to JSON string"""
        return json.dumps(self.to_dict(), sort_keys=True)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PolicyCapsule':
        """Create capsule from dictionary"""
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'PolicyCapsule':
        """Create capsule from JSON string"""
        return cls.from_dict(json.loads(json_str))
    
    def get_canonical_bytes(self) -> bytes:
        """
        Get canonical byte representation for signing.
        Excludes the signature field itself.
        """
        unsigned_data = {
            "policy_engine_hash": self.policy_engine_hash,
            "policy_schema_version": self.policy_schema_version,
            "conformance_vector": sorted(self.conformance_vector),
            "metadata": self.metadata or {}
        }
        return json.dumps(unsigned_data, sort_keys=True).encode('utf-8')


class CapsuleManager:
    """
    Manages policy capsule lifecycle: creation, signing, distribution, and reception.
    """
    
    def __init__(self, nats_client=None):
        """
        Initialize capsule manager.
        
        Args:
            nats_client: Optional NATS client for distribution
        """
        self.nats_client = nats_client
        self.received_capsules: Dict[str, PolicyCapsule] = {}
        logger.info("CapsuleManager initialized")
    
    def create_capsule(
        self,
        wasm_path: Optional[Path],
        tests_passed: List[str],
        schema_version: str = "1.0.0",
        metadata: Optional[Dict[str, Any]] = None
    ) -> PolicyCapsule:
        """
        Create a new policy capsule.
        
        Args:
            wasm_path: Path to WASM policy file (None for Python-based policy)
            tests_passed: List of conformance test IDs that passed
            schema_version: Policy schema version
            metadata: Optional metadata
            
        Returns:
            Unsigned PolicyCapsule
        """
        # Calculate policy hash
        if wasm_path and wasm_path.exists():
            with open(wasm_path, 'rb') as f:
                policy_hash = hashlib.sha256(f.read()).hexdigest()
        else:
            # For Python-based policies, hash the policy logic representation
            from policy.opa_engine import OPAEngine
            engine = OPAEngine()
            policy_repr = json.dumps({
                "allowed_kinds": sorted(engine.ALLOWED_KINDS),
                "max_payload_size": engine.MAX_PAYLOAD_SIZE,
                "required_fields": sorted(engine.REQUIRED_FIELDS),
                "version": schema_version
            }, sort_keys=True)
            policy_hash = hashlib.sha256(policy_repr.encode()).hexdigest()
        
        capsule = PolicyCapsule(
            policy_engine_hash=policy_hash,
            policy_schema_version=schema_version,
            conformance_vector=sorted(tests_passed),
            metadata=metadata or {}
        )
        
        logger.info(
            f"Created capsule: hash={policy_hash[:16]}..., "
            f"version={schema_version}, tests={len(tests_passed)}"
        )
        
        return capsule
    
    def sign_capsule(
        self,
        capsule: PolicyCapsule,
        signer_key: Optional[str] = None
    ) -> PolicyCapsule:
        """
        Sign a policy capsule.
        
        Args:
            capsule: Capsule to sign
            signer_key: Private key for signing (simplified for demo)
            
        Returns:
            Signed PolicyCapsule
        """
        # Get canonical bytes to sign
        canonical_bytes = capsule.get_canonical_bytes()
        
        # Create signature (simplified version using hash)
        # In production, use proper Ed25519 or similar
        if signer_key:
            signature_data = canonical_bytes + signer_key.encode('utf-8')
        else:
            signature_data = canonical_bytes
        
        signature = hashlib.sha256(signature_data).hexdigest()
        
        # Create new capsule with signature
        signed_capsule = PolicyCapsule(
            policy_engine_hash=capsule.policy_engine_hash,
            policy_schema_version=capsule.policy_schema_version,
            conformance_vector=capsule.conformance_vector,
            signature=signature,
            metadata=capsule.metadata
        )
        
        logger.info(f"Signed capsule: signature={signature[:16]}...")
        
        return signed_capsule
    
    def verify_capsule(
        self,
        capsule: PolicyCapsule,
        expected_signer_key: Optional[str] = None
    ) -> bool:
        """
        Verify a policy capsule's signature.
        
        Args:
            capsule: Capsule to verify
            expected_signer_key: Expected signer's public key
            
        Returns:
            True if signature is valid
        """
        if not capsule.signature:
            logger.warning("Capsule has no signature")
            return False
        
        # Recreate signature to verify
        canonical_bytes = capsule.get_canonical_bytes()
        
        if expected_signer_key:
            signature_data = canonical_bytes + expected_signer_key.encode('utf-8')
        else:
            signature_data = canonical_bytes
        
        expected_signature = hashlib.sha256(signature_data).hexdigest()
        
        is_valid = expected_signature == capsule.signature
        
        if is_valid:
            logger.info(f"Capsule signature valid: {capsule.policy_engine_hash[:16]}...")
        else:
            logger.warning(f"Capsule signature invalid: {capsule.policy_engine_hash[:16]}...")
        
        return is_valid
    
    async def distribute_capsule(
        self,
        capsule: PolicyCapsule,
        subject: str = "policy.capsule.update"
    ) -> None:
        """
        Distribute a policy capsule to peers via NATS.
        
        Args:
            capsule: Capsule to distribute
            subject: NATS subject for distribution
        """
        if not self.nats_client:
            logger.warning("No NATS client configured, cannot distribute capsule")
            return
        
        try:
            # Publish capsule to NATS
            capsule_json = capsule.to_json()
            await self.nats_client.publish(
                subject,
                capsule_json.encode('utf-8')
            )
            
            logger.info(
                f"Distributed capsule to {subject}: "
                f"hash={capsule.policy_engine_hash[:16]}..."
            )
        except Exception as e:
            logger.error(f"Failed to distribute capsule: {e}", exc_info=True)
    
    async def receive_capsule(
        self,
        capsule: PolicyCapsule,
        conformance_checker=None,
        signer_key: Optional[str] = None
    ) -> bool:
        """
        Receive and validate a policy capsule from peers.
        
        Args:
            capsule: Received capsule
            conformance_checker: ConformanceChecker instance for validation
            signer_key: Expected signer's key for verification
            
        Returns:
            True if capsule was accepted and loaded
        """
        try:
            # 1. Verify signature
            if not self.verify_capsule(capsule, signer_key):
                logger.error("Capsule signature verification failed")
                return False
            
            # 2. Validate conformance if checker is provided
            if conformance_checker:
                # Check if checker has validate_conformance method
                if hasattr(conformance_checker, 'validate_conformance'):
                    is_conformant = conformance_checker.validate_conformance(capsule)
                    if not is_conformant:
                        logger.error("Capsule failed conformance validation")
                        return False
            
            # 3. Store the capsule
            self.received_capsules[capsule.policy_engine_hash] = capsule
            
            logger.info(
                f"Accepted capsule: hash={capsule.policy_engine_hash[:16]}..., "
                f"version={capsule.policy_schema_version}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to receive capsule: {e}", exc_info=True)
            return False
    
    def get_capsule(self, policy_hash: str) -> Optional[PolicyCapsule]:
        """Get a received capsule by its policy hash"""
        return self.received_capsules.get(policy_hash)
    
    def list_capsules(self) -> List[PolicyCapsule]:
        """List all received capsules"""
        return list(self.received_capsules.values())


# Global capsule manager instance
_capsule_manager: Optional[CapsuleManager] = None


def get_capsule_manager() -> CapsuleManager:
    """Get global capsule manager instance"""
    global _capsule_manager
    if _capsule_manager is None:
        _capsule_manager = CapsuleManager()
    return _capsule_manager


def init_capsule_manager(nats_client=None) -> CapsuleManager:
    """
    Initialize global capsule manager.
    
    Args:
        nats_client: NATS client for distribution
        
    Returns:
        CapsuleManager instance
    """
    global _capsule_manager
    _capsule_manager = CapsuleManager(nats_client)
    return _capsule_manager
