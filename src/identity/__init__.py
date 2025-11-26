"""Identity module for decentralized identifiers and attestations."""

from .did import DIDManager, DIDDocument
from .manifest import AgentManifest, ManifestManager
from .registry import ManifestRegistry
from .attestation import AttestationReport, TEEVerifier

__all__ = [
    "DIDManager",
    "DIDDocument",
    "AgentManifest",
    "ManifestManager",
    "ManifestRegistry",
    "AttestationReport",
    "TEEVerifier",
]
