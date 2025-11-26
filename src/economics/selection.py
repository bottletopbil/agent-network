"""
Committee Selection: diversity-aware weighted selection of verifiers.

Integrates with VerifierPool and ReputationTracker for committee formation.
"""

import random
import math
import time
from typing import List, Optional
from dataclasses import dataclass
from collections import Counter

from economics.pools import VerifierPool, VerifierRecord
from economics.reputation import ReputationTracker


@dataclass
class DiversityConstraints:
    """Diversity constraints for committee selection"""
    max_org_percentage: float = 0.30    # Max 30% from same org
    max_asn_percentage: float = 0.40    # Max 40% from same ASN
    max_region_percentage: float = 0.50  # Max 50% from same region


class VerifierSelector:
    """
    Select committees with weighted selection and diversity constraints.
    
    Weight formula: sqrt(stake) × reputation × recency_factor
    """
    
    def __init__(self, pool: VerifierPool, reputation_tracker: ReputationTracker):
        """
        Initialize verifier selector.
        
        Args:
            pool: VerifierPool for candidate verifiers
            reputation_tracker: ReputationTracker for reputation scores
        """
        self.pool = pool
        self.reputation_tracker = reputation_tracker
    
    def calculate_weight(self, verifier: VerifierRecord) -> float:
        """
        Calculate selection weight for a verifier.
        
        Formula: sqrt(stake) × reputation × recency_factor × tee_multiplier
        - recency_factor = 1.0 - (age_days / 365) × 0.2 (20% decay over a year)
        - tee_multiplier = 2.0 if TEE-verified, else 1.0
        
        Args:
            verifier: VerifierRecord to calculate weight for
        
        Returns:
            Selection weight (higher = more likely to be selected)
        """
        # Stake component (sqrt to reduce whale advantage)
        stake_weight = math.sqrt(verifier.stake)
        
        # Reputation component (with decay)
        reputation = self.reputation_tracker.get_reputation(verifier.verifier_id)
        
        # Recency component (newer verifiers weighted slightly higher)
        age_ns = time.time_ns() - verifier.registered_at
        age_days = age_ns / (24 * 3600 * 1e9)
        recency_factor = 1.0 - min((age_days / 365.0) * 0.2, 0.2)  # Max 20% decay
        
        # TEE verification bonus (2x weight for TEE-verified verifiers)
        tee_multiplier = 2.0 if verifier.metadata.tee_verified else 1.0
        
        return stake_weight * reputation * recency_factor * tee_multiplier
    
    def select_committee(
        self,
        k: int,
        min_stake: int = 0,
        constraints: Optional[DiversityConstraints] = None
    ) -> List[VerifierRecord]:
        """
        Select committee of k verifiers with diversity constraints.
        
        Uses weighted random selection with rejection sampling for diversity.
        
        Args:
            k: Committee size
            min_stake: Minimum stake requirement
            constraints: Diversity constraints (defaults if None)
        
        Returns:
            List of k selected verifiers
        
        Raises:
            ValueError: If insufficient qualified verifiers
        """
        if constraints is None:
            constraints = DiversityConstraints()
        
        # Get qualified verifiers
        candidates = self.pool.get_active_verifiers(min_stake=min_stake)
        
        if len(candidates) < k:
            raise ValueError(
                f"Insufficient qualified verifiers: need {k}, have {len(candidates)}"
            )
        
        # Calculate weights
        weights = [self.calculate_weight(v) for v in candidates]
        
        # Try weighted random selection with diversity enforcement
        max_attempts = 1000
        for attempt in range(max_attempts):
            # Weighted random selection
            committee = random.choices(candidates, weights=weights, k=k)
            
            # Check diversity
            if self.enforce_diversity(committee, constraints):
                return committee
        
        # If we failed to find diverse committee, fall back to deterministic selection
        # Sort by weight and greedily select diverse verifiers
        sorted_candidates = sorted(
            zip(candidates, weights),
            key=lambda x: x[1],
            reverse=True
        )
        
        committee = []
        for candidate, _ in sorted_candidates:
            if len(committee) >= k:
                break
            
            # Try adding this candidate
            test_committee = committee + [candidate]
            if self.enforce_diversity(test_committee, constraints):
                committee.append(candidate)
        
        if len(committee) < k:
            # Still can't meet diversity, relax constraints and return top by weight
            return [c for c, _ in sorted_candidates[:k]]
        
        return committee
    
    def enforce_diversity(
        self,
        committee: List[VerifierRecord],
        constraints: DiversityConstraints
    ) -> bool:
        """
        Check if committee satisfies diversity constraints.
        
        Args:
            committee: List of verifiers to check
            constraints: Diversity constraints
        
        Returns:
            True if committee satisfies all constraints
        """
        if not committee:
            return True
        
        # Check org diversity
        if not self._check_org_diversity(committee, constraints.max_org_percentage):
            return False
        
        # Check ASN diversity
        if not self._check_asn_diversity(committee, constraints.max_asn_percentage):
            return False
        
        # Check region diversity
        if not self._check_region_diversity(committee, constraints.max_region_percentage):
            return False
        
        return True
    
    def _check_org_diversity(self, committee: List[VerifierRecord], max_pct: float) -> bool:
        """Check organization diversity constraint"""
        org_counts = Counter(v.metadata.org_id for v in committee)
        max_allowed = math.ceil(len(committee) * max_pct)
        return all(count <= max_allowed for count in org_counts.values())
    
    def _check_asn_diversity(self, committee: List[VerifierRecord], max_pct: float) -> bool:
        """Check ASN diversity constraint"""
        asn_counts = Counter(v.metadata.asn for v in committee)
        max_allowed = math.ceil(len(committee) * max_pct)
        return all(count <= max_allowed for count in asn_counts.values())
    
    def _check_region_diversity(self, committee: List[VerifierRecord], max_pct: float) -> bool:
        """Check region diversity constraint"""
        region_counts = Counter(v.metadata.region for v in committee)
        max_allowed = math.ceil(len(committee) * max_pct)
        return all(count <= max_allowed for count in region_counts.values())
