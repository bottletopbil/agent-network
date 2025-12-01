"""
Quorum tracking for K_plan attestations in distributed consensus.

Tracks verifier attestations for proposals and determines when quorum
is reached to trigger DECIDE operations.
"""

from typing import Dict, Set, Tuple
from dataclasses import dataclass, field
import threading
from consensus.bootstrap import bootstrap_manager


@dataclass
class QuorumState:
    """
    Track attestations for a single proposal.

    Maintains set of verifier IDs who have attested and checks
    if quorum (K_plan) threshold has been reached.
    """

    need_id: str
    proposal_id: str
    attestations: Set[str] = field(default_factory=set)  # verifier_ids
    k_plan_required: int = 3

    def add_attestation(self, verifier_id: str) -> bool:
        """
        Add attestation from a verifier.

        Args:
            verifier_id: ID of verifier attesting

        Returns:
            True if this attestation completes quorum, False otherwise
        """
        was_quorum = self.has_quorum()
        self.attestations.add(verifier_id)
        is_quorum = self.has_quorum()

        # Return True only if THIS attestation completed quorum
        return is_quorum and not was_quorum

    def has_quorum(self) -> bool:
        """Check if quorum threshold has been reached"""
        return len(self.attestations) >= self.k_plan_required


class QuorumTracker:
    """
    Tracks quorum for multiple proposals across different NEEDs.

    Thread-safe tracking of attestations with automatic quorum detection.
    Used by ATTEST_PLAN handler to trigger DECIDE when K_plan is reached.
    """

    def __init__(self):
        """Initialize quorum tracker with empty state"""
        self.states: Dict[Tuple[str, str], QuorumState] = {}
        self.lock = threading.Lock()

    def record_attestation(
        self, need_id: str, proposal_id: str, verifier_id: str, k_plan: int = 3
    ) -> bool:
        """
        Record an attestation for a proposal.

        Args:
            need_id: NEED being voted on
            proposal_id: Specific proposal being attested
            verifier_id: ID of verifier providing attestation
            k_plan: Required quorum size (default: 3)

        Returns:
            True if this attestation completes quorum (first time),
            False otherwise
        """
        with self.lock:
            key = (need_id, proposal_id)

            if key not in self.states:
                self.states[key] = QuorumState(
                    need_id=need_id, proposal_id=proposal_id, k_plan_required=k_plan
                )

            state = self.states[key]
            return state.add_attestation(verifier_id)

    def check_quorum(self, need_id: str, proposal_id: str) -> bool:
        """
        Check if quorum has been reached for a proposal.

        Args:
            need_id: NEED identifier
            proposal_id: Proposal identifier

        Returns:
            True if quorum reached, False otherwise
        """
        key = (need_id, proposal_id)
        state = self.states.get(key)
        return state.has_quorum() if state else False

    def get_attestation_count(self, need_id: str, proposal_id: str) -> int:
        """Get number of attestations for a proposal"""
        key = (need_id, proposal_id)
        state = self.states.get(key)
        return len(state.attestations) if state else 0

    def get_k_plan(
        self, active_verifiers: int, alpha: float = 0.3, k_target: int = 5
    ) -> int:
        """
        Calculate K_plan based on active verifiers.

        Formula: K = min(K_target, floor(active_verifiers × alpha))

        Args:
            active_verifiers: Number of active staked verifiers
            alpha: Fraction of active verifiers required (default: 0.3 = 30%)
            k_target: Maximum quorum size (default: 5)

        Returns:
            Required quorum size (minimum 1)

        Examples:
            - 5 active verifiers → K=1 (floor(5×0.3)=1)
            - 10 active verifiers → K=3 (floor(10×0.3)=3)
            - 20 active verifiers → K=5 (min(5, floor(20×0.3)=6) = 5)
        """
        calculated = max(1, int(active_verifiers * alpha))
        return min(k_target, calculated)

    def get_k_plan_with_bootstrap(
        self, active_verifiers: int, alpha: float = 0.3, k_target: int = 5
    ) -> int:
        """
        Calculate K_plan with bootstrap mode support.

        Uses BootstrapManager to determine if network is in bootstrap mode
        and calculates K accordingly:
        - Bootstrap mode (< 10 verifiers): K = 1
        - Post-bootstrap: Progressive K based on active verifiers

        Args:
            active_verifiers: Number of active staked verifiers
            alpha: Fraction of active verifiers required (default: 0.3 = 30%)
            k_target: Maximum quorum size (default: 5)

        Returns:
            Required quorum size (1 in bootstrap, progressive after)
        """
        bootstrap_mode = bootstrap_manager.is_bootstrap_mode(active_verifiers)
        return bootstrap_manager.calculate_k_result(active_verifiers, bootstrap_mode)


# Global quorum tracker instance
quorum_tracker = QuorumTracker()
