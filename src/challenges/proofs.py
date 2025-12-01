"""
Proof schemas and types for challenge protocol.

Defines:
- ProofType: Enum of supported proof types
- ProofSchema: Dataclass for proof metadata
- Proof size and gas limits
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


# Proof size limits
MAX_PROOF_SIZE_BYTES = 10 * 1024  # 10 KB
MAX_GAS_ESTIMATE = 100_000  # 100k gas


class ProofType(Enum):
    """Types of proofs that can be submitted for challenges"""

    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
    MISSING_CITATION = "MISSING_CITATION"
    SEMANTIC_CONTRADICTION = "SEMANTIC_CONTRADICTION"
    OUTPUT_MISMATCH = "OUTPUT_MISMATCH"
    POLICY_BREACH = "POLICY_BREACH"


@dataclass
class ProofSchema:
    """
    Metadata for a challenge proof.

    Fields:
        proof_type: Type of proof being submitted
        evidence_hash: Hash of evidence stored in CAS
        size_bytes: Size of proof data in bytes
        gas_estimate: Estimated gas for verification
    """

    proof_type: ProofType
    evidence_hash: str
    size_bytes: int
    gas_estimate: int
    metadata: Optional[dict] = None

    def validate(self) -> tuple[bool, Optional[str]]:
        """
        Validate proof schema against limits.

        Returns:
            (is_valid, error_message)
        """
        # Validate size limit
        if self.size_bytes > MAX_PROOF_SIZE_BYTES:
            return (
                False,
                f"Proof size {self.size_bytes} exceeds max {MAX_PROOF_SIZE_BYTES} bytes",
            )

        if self.size_bytes <= 0:
            return False, "Proof size must be positive"

        # Validate gas estimate
        if self.gas_estimate > MAX_GAS_ESTIMATE:
            return (
                False,
                f"Gas estimate {self.gas_estimate} exceeds max {MAX_GAS_ESTIMATE}",
            )

        if self.gas_estimate < 0:
            return False, "Gas estimate must be non-negative"

        # Validate evidence hash
        if not self.evidence_hash or len(self.evidence_hash) != 64:
            return False, "Evidence hash must be 64-character SHA256 hex string"

        # Validate proof type
        if not isinstance(self.proof_type, ProofType):
            return False, "Invalid proof type"

        return True, None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "proof_type": self.proof_type.value,
            "evidence_hash": self.evidence_hash,
            "size_bytes": self.size_bytes,
            "gas_estimate": self.gas_estimate,
            "metadata": self.metadata or {},
        }

    @staticmethod
    def from_dict(data: dict) -> "ProofSchema":
        """Create ProofSchema from dictionary"""
        return ProofSchema(
            proof_type=ProofType(data["proof_type"]),
            evidence_hash=data["evidence_hash"],
            size_bytes=data["size_bytes"],
            gas_estimate=data["gas_estimate"],
            metadata=data.get("metadata"),
        )
