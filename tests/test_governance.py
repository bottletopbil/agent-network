"""Tests for Phase 19.4 - Governance Protocol"""

import pytest
from datetime import datetime, timedelta
from src.marketplace.governance import (
    GovernanceSystem,
    Proposal,
    VoteChoice,
    ProposalStatus,
)


@pytest.fixture
def governance():
    """Create a fresh GovernanceSystem for each test."""
    system = GovernanceSystem(
        min_stake=100.0,
        voting_period_hours=168,  # 1 week
        quorum_percentage=0.2,
        approval_threshold=0.51,
    )

    # Register some voters
    system.register_voter("alice", 1000.0)
    system.register_voter("bob", 500.0)
    system.register_voter("charlie", 300.0)
    system.register_voter("diana", 200.0)
    # Total: 2000.0

    return system


class TestVoterRegistration:
    """Test voter registration."""

    def test_register_voter(self):
        """Test registering voters."""
        gov = GovernanceSystem()

        gov.register_voter("alice", 1000.0)
        assert gov.registered_voters["alice"] == 1000.0
        assert gov.total_voting_weight == 1000.0

        gov.register_voter("bob", 500.0)
        assert gov.registered_voters["bob"] == 500.0
        assert gov.total_voting_weight == 1500.0

    def test_update_voter_weight(self):
        """Test updating a voter's weight."""
        gov = GovernanceSystem()

        gov.register_voter("alice", 1000.0)
        assert gov.total_voting_weight == 1000.0

        # Update weight
        gov.register_voter("alice", 1500.0)
        assert gov.registered_voters["alice"] == 1500.0
        assert gov.total_voting_weight == 1500.0

    def test_register_voter_invalid_weight(self):
        """Test that invalid weights are rejected."""
        gov = GovernanceSystem()

        with pytest.raises(ValueError, match="Weight must be positive"):
            gov.register_voter("alice", 0.0)

        with pytest.raises(ValueError, match="Weight must be positive"):
            gov.register_voter("alice", -100.0)


class TestProposalSubmission:
    """Test proposal submission."""

    def test_submit_proposal(self, governance):
        """Test submitting a valid proposal."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Increase K_plan",
            description="Increase K_plan from 3 to 5 for better security",
            parameter_changes={"k_plan": 5},
            stake=150.0,
        )

        assert proposal_id is not None
        assert proposal_id in governance.proposals

        proposal = governance.get_proposal(proposal_id)
        assert proposal.title == "Increase K_plan"
        assert proposal.proposer == "alice"
        assert proposal.stake == 150.0
        assert proposal.parameter_changes == {"k_plan": 5}
        assert proposal.status == ProposalStatus.PENDING

    def test_submit_proposal_insufficient_stake(self, governance):
        """Test that insufficient stake is rejected."""
        with pytest.raises(ValueError, match="Insufficient stake"):
            governance.submit_proposal(
                proposer="alice",
                title="Test",
                description="Test",
                parameter_changes={"k_plan": 5},
                stake=50.0,  # Less than min_stake (100)
            )

    def test_submit_proposal_invalid_parameter(self, governance):
        """Test that invalid parameters are rejected."""
        with pytest.raises(ValueError, match="not governable"):
            governance.submit_proposal(
                proposer="alice",
                title="Invalid",
                description="Invalid parameter",
                parameter_changes={"invalid_param": 123},
                stake=100.0,
            )

    def test_submit_proposal_invalid_k_plan(self, governance):
        """Test that invalid k_plan values are rejected."""
        with pytest.raises(ValueError, match="k_plan must be a positive integer"):
            governance.submit_proposal(
                proposer="alice",
                title="Invalid K_plan",
                description="Negative k_plan",
                parameter_changes={"k_plan": -1},
                stake=100.0,
            )

    def test_submit_proposal_invalid_slashing(self, governance):
        """Test that invalid slashing percentages are rejected."""
        with pytest.raises(
            ValueError, match="slashing_percentage must be between 0 and 1"
        ):
            governance.submit_proposal(
                proposer="alice",
                title="Invalid Slashing",
                description="Invalid slashing percentage",
                parameter_changes={"slashing_percentage": 1.5},
                stake=100.0,
            )


class TestVoting:
    """Test voting functionality."""

    def test_start_voting(self, governance):
        """Test starting a voting period."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )

        governance.start_voting(proposal_id)

        proposal = governance.get_proposal(proposal_id)
        assert proposal.status == ProposalStatus.ACTIVE
        assert proposal.voting_start is not None
        assert proposal.voting_end is not None

    def test_vote_yes(self, governance):
        """Test casting YES vote."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )
        governance.start_voting(proposal_id)

        governance.vote(proposal_id, "bob", VoteChoice.YES, 500.0)

        assert "bob" in governance.votes[proposal_id]
        vote = governance.votes[proposal_id]["bob"]
        assert vote.choice == VoteChoice.YES
        assert vote.weight == 500.0

    def test_vote_no(self, governance):
        """Test casting NO vote."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )
        governance.start_voting(proposal_id)

        governance.vote(proposal_id, "charlie", VoteChoice.NO, 300.0)

        vote = governance.votes[proposal_id]["charlie"]
        assert vote.choice == VoteChoice.NO

    def test_vote_abstain(self, governance):
        """Test casting ABSTAIN vote."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )
        governance.start_voting(proposal_id)

        governance.vote(proposal_id, "diana", VoteChoice.ABSTAIN, 200.0)

        vote = governance.votes[proposal_id]["diana"]
        assert vote.choice == VoteChoice.ABSTAIN

    def test_vote_update(self, governance):
        """Test updating a vote."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )
        governance.start_voting(proposal_id)

        # First vote
        governance.vote(proposal_id, "bob", VoteChoice.NO, 500.0)

        # Change vote
        governance.vote(proposal_id, "bob", VoteChoice.YES, 500.0)

        vote = governance.votes[proposal_id]["bob"]
        assert vote.choice == VoteChoice.YES

    def test_vote_not_active(self, governance):
        """Test that voting on non-active proposal fails."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )

        # Don't start voting
        with pytest.raises(ValueError, match="Voting not active"):
            governance.vote(proposal_id, "bob", VoteChoice.YES, 500.0)

    def test_vote_unregistered_voter(self, governance):
        """Test that unregistered voters cannot vote."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )
        governance.start_voting(proposal_id)

        with pytest.raises(ValueError, match="not registered"):
            governance.vote(proposal_id, "eve", VoteChoice.YES, 100.0)

    def test_vote_exceeds_weight(self, governance):
        """Test that voting with excessive weight fails."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )
        governance.start_voting(proposal_id)

        with pytest.raises(ValueError, match="exceeds voter's registered weight"):
            governance.vote(
                proposal_id, "bob", VoteChoice.YES, 1000.0
            )  # Bob only has 500


class TestVoteTallying:
    """Test vote tallying and proposal outcomes."""

    def test_tally_no_votes(self, governance):
        """Test tallying with no votes."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )
        governance.start_voting(proposal_id)

        result = governance.tally_votes(proposal_id)

        assert result["yes_votes"] == 0.0
        assert result["no_votes"] == 0.0
        assert result["abstain_votes"] == 0.0
        assert result["total_votes"] == 0.0
        assert result["quorum_met"] is False
        assert result["passed"] is False

    def test_tally_quorum_not_met(self, governance):
        """Test that proposal fails when quorum not met."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )
        governance.start_voting(proposal_id)

        # Only 200 votes out of 2000 total weight (10% < 20% quorum)
        governance.vote(proposal_id, "diana", VoteChoice.YES, 200.0)

        result = governance.tally_votes(proposal_id)

        assert result["yes_votes"] == 200.0
        assert result["total_votes"] == 200.0
        assert result["quorum_met"] is False
        assert result["passed"] is False

    def test_tally_quorum_met_approval_not_met(self, governance):
        """Test that proposal fails when approval threshold not met."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )
        governance.start_voting(proposal_id)

        # Quorum: 500 out of 2000 = 25% (> 20%)
        # Approval: 200 YES / (200 + 300) = 40% (< 51%)
        governance.vote(proposal_id, "diana", VoteChoice.YES, 200.0)
        governance.vote(proposal_id, "charlie", VoteChoice.NO, 300.0)

        result = governance.tally_votes(proposal_id)

        assert result["yes_votes"] == 200.0
        assert result["no_votes"] == 300.0
        assert result["total_votes"] == 500.0
        assert result["quorum_met"] is True
        assert result["approval_met"] is False
        assert result["passed"] is False

    def test_tally_proposal_passes(self, governance):
        """Test that proposal passes with quorum and approval."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )
        governance.start_voting(proposal_id)

        # Quorum: 1500 out of 2000 = 75% (> 20%)
        # Approval: 1000 YES / (1000 + 500) = 66.7% (> 51%)
        governance.vote(proposal_id, "alice", VoteChoice.YES, 1000.0)
        governance.vote(proposal_id, "bob", VoteChoice.NO, 500.0)

        result = governance.tally_votes(proposal_id)

        assert result["yes_votes"] == 1000.0
        assert result["no_votes"] == 500.0
        assert result["total_votes"] == 1500.0
        assert result["quorum_met"] is True
        assert result["approval_met"] is True
        assert result["passed"] is True

    def test_tally_abstain_counts_for_quorum_not_approval(self, governance):
        """Test that ABSTAIN votes count for quorum but not approval."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )
        governance.start_voting(proposal_id)

        # Total votes: 1200 (60% quorum - met)
        # Approval: 600 YES / (600 + 300) = 66.7% (> 51% - met)
        # ABSTAIN doesn't count toward approval denominator
        governance.vote(proposal_id, "alice", VoteChoice.YES, 600.0)
        governance.vote(proposal_id, "bob", VoteChoice.NO, 300.0)
        governance.vote(proposal_id, "charlie", VoteChoice.ABSTAIN, 300.0)

        result = governance.tally_votes(proposal_id)

        assert result["yes_votes"] == 600.0
        assert result["no_votes"] == 300.0
        assert result["abstain_votes"] == 300.0
        assert result["total_votes"] == 1200.0
        assert result["quorum_met"] is True
        assert result["approval_met"] is True
        assert result["passed"] is True


class TestProposalFinalization:
    """Test proposal finalization."""

    def test_finalize_passed_proposal(self, governance):
        """Test finalizing a passed proposal."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )
        governance.start_voting(proposal_id)

        # Pass the proposal
        governance.vote(proposal_id, "alice", VoteChoice.YES, 1000.0)
        governance.vote(proposal_id, "bob", VoteChoice.YES, 500.0)

        governance.finalize_proposal(proposal_id)

        proposal = governance.get_proposal(proposal_id)
        assert proposal.status == ProposalStatus.PASSED

    def test_finalize_rejected_proposal(self, governance):
        """Test finalizing a rejected proposal."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )
        governance.start_voting(proposal_id)

        # Reject the proposal
        governance.vote(proposal_id, "alice", VoteChoice.NO, 1000.0)
        governance.vote(proposal_id, "bob", VoteChoice.NO, 500.0)

        governance.finalize_proposal(proposal_id)

        proposal = governance.get_proposal(proposal_id)
        assert proposal.status == ProposalStatus.REJECTED


class TestProposalExecution:
    """Test proposal execution and parameter changes."""

    def test_execute_proposal_k_plan(self, governance):
        """Test executing a proposal to change k_plan."""
        # Initial value
        assert governance.get_parameter("k_plan") == 3

        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Increase K_plan",
            description="Increase K_plan to 5",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )
        governance.start_voting(proposal_id)
        governance.vote(proposal_id, "alice", VoteChoice.YES, 1000.0)
        governance.vote(proposal_id, "bob", VoteChoice.YES, 500.0)
        governance.finalize_proposal(proposal_id)

        # Execute
        governance.execute_proposal(proposal_id)

        # Verify parameter changed
        assert governance.get_parameter("k_plan") == 5

        # Verify status
        proposal = governance.get_proposal(proposal_id)
        assert proposal.status == ProposalStatus.EXECUTED

    def test_execute_proposal_multiple_parameters(self, governance):
        """Test executing a proposal with multiple parameter changes."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Multiple Changes",
            description="Change multiple parameters",
            parameter_changes={
                "k_plan": 4,
                "k_result": 6,
                "bounty_cap": 2000.0,
                "slashing_percentage": 0.15,
            },
            stake=100.0,
        )
        governance.start_voting(proposal_id)
        governance.vote(proposal_id, "alice", VoteChoice.YES, 1000.0)
        governance.vote(proposal_id, "bob", VoteChoice.YES, 500.0)
        governance.finalize_proposal(proposal_id)
        governance.execute_proposal(proposal_id)

        # Verify all parameters changed
        assert governance.get_parameter("k_plan") == 4
        assert governance.get_parameter("k_result") == 6
        assert governance.get_parameter("bounty_cap") == 2000.0
        assert governance.get_parameter("slashing_percentage") == 0.15

    def test_execute_not_passed_proposal(self, governance):
        """Test that rejected proposals cannot be executed."""
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Test",
            description="Test",
            parameter_changes={"k_plan": 5},
            stake=100.0,
        )
        governance.start_voting(proposal_id)
        governance.vote(proposal_id, "alice", VoteChoice.NO, 1000.0)
        governance.finalize_proposal(proposal_id)

        with pytest.raises(ValueError, match="must be passed to execute"):
            governance.execute_proposal(proposal_id)

        # Parameter should not have changed
        assert governance.get_parameter("k_plan") == 3


class TestEndToEnd:
    """End-to-end governance scenarios."""

    def test_complete_governance_cycle(self, governance):
        """Test complete governance cycle from submission to execution."""
        # 1. Submit proposal
        proposal_id = governance.submit_proposal(
            proposer="alice",
            title="Update Bounty Cap",
            description="Increase bounty cap to 5000",
            parameter_changes={"bounty_cap": 5000.0},
            stake=150.0,
        )

        proposal = governance.get_proposal(proposal_id)
        assert proposal.status == ProposalStatus.PENDING
        assert governance.get_parameter("bounty_cap") == 1000.0

        # 2. Start voting
        governance.start_voting(proposal_id)
        assert proposal.status == ProposalStatus.ACTIVE

        # 3. Cast votes
        governance.vote(proposal_id, "alice", VoteChoice.YES, 1000.0)
        governance.vote(proposal_id, "bob", VoteChoice.YES, 500.0)
        governance.vote(proposal_id, "charlie", VoteChoice.NO, 300.0)

        # 4. Tally votes
        result = governance.tally_votes(proposal_id)
        assert result["passed"] is True

        # 5. Finalize
        governance.finalize_proposal(proposal_id)
        assert proposal.status == ProposalStatus.PASSED

        # 6. Execute
        governance.execute_proposal(proposal_id)
        assert proposal.status == ProposalStatus.EXECUTED
        assert governance.get_parameter("bounty_cap") == 5000.0

    def test_multiple_proposals(self, governance):
        """Test managing multiple proposals simultaneously."""
        # Submit multiple proposals
        p1 = governance.submit_proposal(
            proposer="alice",
            title="Proposal 1",
            description="Change k_plan",
            parameter_changes={"k_plan": 4},
            stake=100.0,
        )

        p2 = governance.submit_proposal(
            proposer="bob",
            title="Proposal 2",
            description="Change slashing",
            parameter_changes={"slashing_percentage": 0.2},
            stake=100.0,
        )

        # Start voting on both
        governance.start_voting(p1)
        governance.start_voting(p2)

        # Vote differently on each
        governance.vote(p1, "alice", VoteChoice.YES, 1000.0)
        governance.vote(p1, "bob", VoteChoice.YES, 500.0)

        governance.vote(p2, "alice", VoteChoice.NO, 1000.0)
        governance.vote(p2, "bob", VoteChoice.NO, 500.0)

        # Finalize both
        governance.finalize_proposal(p1)
        governance.finalize_proposal(p2)

        # p1 should pass, p2 should be rejected
        assert governance.get_proposal(p1).status == ProposalStatus.PASSED
        assert governance.get_proposal(p2).status == ProposalStatus.REJECTED

        # Execute p1
        governance.execute_proposal(p1)
        assert governance.get_parameter("k_plan") == 4

        # Original slashing percentage should remain
        assert governance.get_parameter("slashing_percentage") == 0.1

    def test_list_proposals(self, governance):
        """Test listing proposals by status."""
        p1 = governance.submit_proposal("alice", "P1", "Desc", {"k_plan": 4}, 100.0)
        p2 = governance.submit_proposal("bob", "P2", "Desc", {"k_plan": 5}, 100.0)
        p3 = governance.submit_proposal("charlie", "P3", "Desc", {"k_plan": 6}, 100.0)

        governance.start_voting(p1)
        governance.start_voting(p2)

        pending = governance.list_proposals(ProposalStatus.PENDING)
        active = governance.list_proposals(ProposalStatus.ACTIVE)

        assert len(pending) == 1
        assert len(active) == 2

        all_proposals = governance.list_proposals()
        assert len(all_proposals) == 3
