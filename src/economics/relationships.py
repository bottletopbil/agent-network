"""
Related-Party Detection: identify potential collusion between verifiers and challengers.

Detects organizational affiliations, network proximity, and identity linkages.
"""

from typing import List, Dict, Optional, Set
from dataclasses import dataclass


@dataclass
class PartyInfo:
    """Information about a party for relationship detection"""

    account_id: str
    org_domain: Optional[str] = None  # e.g., "acme.com"
    asn: Optional[int] = None  # Autonomous System Number
    identity_hash: Optional[str] = None  # Hash of identity proof


class RelationshipDetector:
    """
    Detect relationships between parties that may indicate collusion.

    Detection strategies:
    - Same organization (via domain)
    - Same ASN (network proximity)
    - Identity linkage (shared identity proof hash)
    """

    def __init__(self):
        """Initialize relationship detector"""
        # In-memory cache of party information
        self._party_cache: Dict[str, PartyInfo] = {}

    def register_party(self, party_info: PartyInfo) -> None:
        """
        Register party information for future detection.

        Args:
            party_info: PartyInfo object with account details
        """
        self._party_cache[party_info.account_id] = party_info

    def get_party_info(self, account_id: str) -> Optional[PartyInfo]:
        """
        Get registered party information.

        Args:
            account_id: Account ID to query

        Returns:
            PartyInfo if registered, None otherwise
        """
        return self._party_cache.get(account_id)

    def detect_same_org(self, verifiers: List[str], challenger: Optional[str] = None) -> bool:
        """
        Detect if any verifiers share organization with challenger.

        Args:
            verifiers: List of verifier account IDs
            challenger: Optional challenger account ID

        Returns:
            True if same organization detected, False otherwise
        """
        if not challenger:
            return False

        challenger_info = self.get_party_info(challenger)
        if not challenger_info or not challenger_info.org_domain:
            return False

        for verifier_id in verifiers:
            verifier_info = self.get_party_info(verifier_id)
            if verifier_info and verifier_info.org_domain:
                if verifier_info.org_domain == challenger_info.org_domain:
                    return True

        return False

    def detect_same_asn(self, verifiers: List[str], challenger: Optional[str] = None) -> bool:
        """
        Detect if any verifiers share ASN with challenger.

        Args:
            verifiers: List of verifier account IDs
            challenger: Optional challenger account ID

        Returns:
            True if same ASN detected, False otherwise
        """
        if not challenger:
            return False

        challenger_info = self.get_party_info(challenger)
        if not challenger_info or challenger_info.asn is None:
            return False

        for verifier_id in verifiers:
            verifier_info = self.get_party_info(verifier_id)
            if verifier_info and verifier_info.asn is not None:
                if verifier_info.asn == challenger_info.asn:
                    return True

        return False

    def detect_identity_links(self, verifiers: List[str], challenger: Optional[str] = None) -> bool:
        """
        Detect if any verifiers share identity proof hash with challenger.

        Args:
            verifiers: List of verifier account IDs
            challenger: Optional challenger account ID

        Returns:
            True if identity linkage detected, False otherwise
        """
        if not challenger:
            return False

        challenger_info = self.get_party_info(challenger)
        if not challenger_info or not challenger_info.identity_hash:
            return False

        for verifier_id in verifiers:
            verifier_info = self.get_party_info(verifier_id)
            if verifier_info and verifier_info.identity_hash:
                if verifier_info.identity_hash == challenger_info.identity_hash:
                    return True

        return False

    def detect_any_relationship(
        self, verifiers: List[str], challenger: Optional[str] = None
    ) -> bool:
        """
        Detect if any relationship exists between verifiers and challenger.

        Args:
            verifiers: List of verifier account IDs
            challenger: Optional challenger account ID

        Returns:
            True if any relationship detected, False otherwise
        """
        return (
            self.detect_same_org(verifiers, challenger)
            or self.detect_same_asn(verifiers, challenger)
            or self.detect_identity_links(verifiers, challenger)
        )

    def get_related_parties(
        self, verifiers: List[str], challenger: Optional[str] = None
    ) -> Set[str]:
        """
        Get set of verifiers that have relationships with challenger.

        Args:
            verifiers: List of verifier account IDs
            challenger: Optional challenger account ID

        Returns:
            Set of verifier account IDs with detected relationships
        """
        if not challenger:
            return set()

        related = set()
        challenger_info = self.get_party_info(challenger)

        if not challenger_info:
            return related

        for verifier_id in verifiers:
            verifier_info = self.get_party_info(verifier_id)
            if not verifier_info:
                continue

            # Check organization
            if (
                challenger_info.org_domain
                and verifier_info.org_domain
                and challenger_info.org_domain == verifier_info.org_domain
            ):
                related.add(verifier_id)
                continue

            # Check ASN
            if (
                challenger_info.asn is not None
                and verifier_info.asn is not None
                and challenger_info.asn == verifier_info.asn
            ):
                related.add(verifier_id)
                continue

            # Check identity
            if (
                challenger_info.identity_hash
                and verifier_info.identity_hash
                and challenger_info.identity_hash == verifier_info.identity_hash
            ):
                related.add(verifier_id)

        return related
