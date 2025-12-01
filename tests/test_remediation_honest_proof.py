"""
Test for honest verifier reward validation (ECON-008).

Validates that only verifiers who actually attested receive honest rewards.
"""

import sys
from pathlib import Path
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_only_actual_attestors_receive_rewards():
    """
    Test that only verifiers who submitted ATTEST messages receive rewards.
    """
    from economics.slashing import PolicyEnforcement

    enforcement = PolicyEnforcement()

    # Set up scenario with 5 verifiers
    verifiers = ["alice", "bob", "charlie", "dave", "eve"]

    # Only 3 actually attested
    attestation_log = [
        {"verifier_id": "alice", "verdict": "honest"},
        {"verifier_id": "bob", "verdict": "honest"},
        {"verifier_id": "charlie", "verdict": "honest"},
    ]

    # Try to claim all 5 are honest (including free-riders)
    claimed_honest = ["alice", "bob", "charlie", "dave", "eve"]

    result = enforcement.slash_verifiers(
        challenger_id="challenger1",
        dishonest_verifiers=["malicious"],
        honest_verifiers=claimed_honest,
        total_slashed=1000,
        attestation_log=attestation_log,
    )

    # Only actual attestors should receive rewards
    honest_rewards = result.get("honest_rewards", {})

    assert "alice" in honest_rewards, "Alice attested, should get reward"
    assert "bob" in honest_rewards, "Bob attested, should get reward"
    assert "charlie" in honest_rewards, "Charlie attested, should get reward"
    assert "dave" not in honest_rewards, "Dave didn't attest, should not get reward"
    assert "eve" not in honest_rewards, "Eve didn't attest, should not get reward"


def test_fake_honest_verifier_rejected():
    """
    Test that completely fake verifier IDs are rejected.
    """
    from economics.slashing import PolicyEnforcement

    enforcement = PolicyEnforcement()

    # Real attestors
    attestation_log = [{"verifier_id": "alice", "verdict": "honest"}]

    # Attacker tries to claim fake verifiers are honest
    claimed_honest = ["alice", "attacker_sybil", "fake_verifier"]

    result = enforcement.slash_verifiers(
        challenger_id="challenger1",
        dishonest_verifiers=["malicious"],
        honest_verifiers=claimed_honest,
        total_slashed=1000,
        attestation_log=attestation_log,
    )

    honest_rewards = result.get("honest_rewards", {})

    # Only alice should receive rewards
    assert len(honest_rewards) == 1
    assert "alice" in honest_rewards
    assert "attacker_sybil" not in honest_rewards
    assert "fake_verifier" not in honest_rewards


def test_warning_logged_for_non_attestors():
    """
    Test that warning is logged when honest_verifiers contains non-attestors.
    """
    from economics.slashing import PolicyEnforcement
    from unittest.mock import patch

    enforcement = PolicyEnforcement()

    attestation_log = [{"verifier_id": "alice", "verdict": "honest"}]

    # Include non-attestor in honest list
    claimed_honest = ["alice", "free_rider"]

    with patch("economics.slashing.logger") as mock_logger:
        enforcement.slash_verifiers(
            challenger_id="challenger1",
            dishonest_verifiers=["malicious"],
            honest_verifiers=claimed_honest,
            total_slashed=1000,
            attestation_log=attestation_log,
        )

        # Should log warning about free_rider
        assert mock_logger.warning.called


def test_empty_attestation_log():
    """
    Test behavior when no one actually attested.
    """
    from economics.slashing import PolicyEnforcement

    enforcement = PolicyEnforcement()

    # No attestations
    attestation_log = []

    # But someone claims verifiers are honest
    claimed_honest = ["alice", "bob"]

    result = enforcement.slash_verifiers(
        challenger_id="challenger1",
        dishonest_verifiers=["malicious"],
        honest_verifiers=claimed_honest,
        total_slashed=1000,
        attestation_log=attestation_log,
    )

    # No one should receive honest rewards
    honest_rewards = result.get("honest_rewards", {})
    assert len(honest_rewards) == 0


def test_all_claimed_honest_are_verified():
    """
    Test normal case where all claimed honest verifiers actually attested.
    """
    from economics.slashing import PolicyEnforcement

    enforcement = PolicyEnforcement()

    attestation_log = [
        {"verifier_id": "alice", "verdict": "honest"},
        {"verifier_id": "bob", "verdict": "honest"},
    ]

    claimed_honest = ["alice", "bob"]

    result = enforcement.slash_verifiers(
        challenger_id="challenger1",
        dishonest_verifiers=["malicious"],
        honest_verifiers=claimed_honest,
        total_slashed=1000,
        attestation_log=attestation_log,
    )

    honest_rewards = result.get("honest_rewards", {})

    # Both should receive rewards
    assert len(honest_rewards) == 2
    assert "alice" in honest_rewards
    assert "bob" in honest_rewards
