"""Phase 19.4 - Governance Protocol

This module implements a decentralized governance system for protocol parameter management.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from enum import Enum
import uuid
from datetime import datetime, timedelta


class VoteChoice(Enum):
    """Vote choices for proposals."""

    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"


class ProposalStatus(Enum):
    """Status of a governance proposal."""

    PENDING = "pending"  # Submitted, voting not started
    ACTIVE = "active"  # Voting in progress
    PASSED = "passed"  # Vote passed, awaiting execution
    REJECTED = "rejected"  # Vote failed
    EXECUTED = "executed"  # Proposal executed
    EXPIRED = "expired"  # Voting period expired


@dataclass
class Proposal:
    """Represents a governance proposal."""

    proposal_id: str
    title: str
    description: str
    parameter_changes: Dict[str, Any]
    proposer: str
    stake: float
    status: ProposalStatus = ProposalStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    voting_start: Optional[datetime] = None
    voting_end: Optional[datetime] = None


@dataclass
class Vote:
    """Represents a vote on a proposal."""

    voter_id: str
    choice: VoteChoice
    weight: float
    timestamp: datetime = field(default_factory=datetime.now)


class GovernanceSystem:
    """
    Manages decentralized governance of protocol parameters.

    Supports voting on proposals to change:
    - K_plan, K_result thresholds
    - Bounty caps
    - Slashing percentages
    """

    # Default governable parameters
    DEFAULT_PARAMS = {
        "k_plan": 3,
        "k_result": 5,
        "bounty_cap": 1000.0,
        "slashing_percentage": 0.1,
    }

    def __init__(
        self,
        min_stake: float = 100.0,
        voting_period_hours: int = 168,  # 1 week
        quorum_percentage: float = 0.2,  # 20% of total weight must vote
        approval_threshold: float = 0.51,  # 51% of votes must be YES
    ):
        """
        Initialize governance system.

        Args:
            min_stake: Minimum stake required to submit a proposal
            voting_period_hours: Length of voting period in hours
            quorum_percentage: Minimum % of total weight that must vote
            approval_threshold: Minimum % of YES votes needed to pass
        """
        self.proposals: Dict[str, Proposal] = {}
        self.votes: Dict[str, Dict[str, Vote]] = {}  # proposal_id -> {voter_id -> Vote}
        self.parameters: Dict[str, Any] = self.DEFAULT_PARAMS.copy()

        self.min_stake = min_stake
        self.voting_period = timedelta(hours=voting_period_hours)
        self.quorum_percentage = quorum_percentage
        self.approval_threshold = approval_threshold

        # Track total voting weight for quorum calculation
        self.total_voting_weight: float = 0.0
        self.registered_voters: Dict[str, float] = {}  # voter_id -> weight

    def register_voter(self, voter_id: str, weight: float):
        """
        Register a voter with their voting weight.

        Args:
            voter_id: ID of the voter
            weight: Voting weight (typically based on stake)
        """
        if weight <= 0:
            raise ValueError("Weight must be positive")

        old_weight = self.registered_voters.get(voter_id, 0.0)
        self.registered_voters[voter_id] = weight
        self.total_voting_weight = self.total_voting_weight - old_weight + weight

    def submit_proposal(
        self,
        proposer: str,
        title: str,
        description: str,
        parameter_changes: Dict[str, Any],
        stake: float,
    ) -> str:
        """
        Submit a new governance proposal.

        Args:
            proposer: ID of the proposer
            title: Proposal title
            description: Detailed description
            parameter_changes: Dict of parameter names to new values
            stake: Amount staked (must meet minimum)

        Returns:
            proposal_id: Unique identifier for the proposal

        Raises:
            ValueError: If stake is insufficient or parameters are invalid
        """
        if stake < self.min_stake:
            raise ValueError(f"Insufficient stake: {stake} < {self.min_stake}")

        # Validate that proposed parameters are governable
        for param in parameter_changes:
            if param not in self.DEFAULT_PARAMS:
                raise ValueError(f"Parameter '{param}' is not governable")

        # Validate parameter values
        self._validate_parameter_changes(parameter_changes)

        proposal_id = str(uuid.uuid4())
        proposal = Proposal(
            proposal_id=proposal_id,
            title=title,
            description=description,
            parameter_changes=parameter_changes,
            proposer=proposer,
            stake=stake,
            status=ProposalStatus.PENDING,
        )

        self.proposals[proposal_id] = proposal
        return proposal_id

    def start_voting(self, proposal_id: str):
        """
        Start the voting period for a proposal.

        Args:
            proposal_id: ID of the proposal

        Raises:
            ValueError: If proposal doesn't exist or is not pending
        """
        if proposal_id not in self.proposals:
            raise ValueError(f"Proposal {proposal_id} does not exist")

        proposal = self.proposals[proposal_id]

        if proposal.status != ProposalStatus.PENDING:
            raise ValueError(
                f"Proposal must be pending to start voting (status: {proposal.status})"
            )

        proposal.status = ProposalStatus.ACTIVE
        proposal.voting_start = datetime.now()
        proposal.voting_end = proposal.voting_start + self.voting_period

        # Initialize vote tracking for this proposal
        self.votes[proposal_id] = {}

    def vote(self, proposal_id: str, voter_id: str, choice: VoteChoice, weight: float):
        """
        Cast a vote on a proposal.

        Args:
            proposal_id: ID of the proposal
            voter_id: ID of the voter
            choice: YES, NO, or ABSTAIN
            weight: Voting weight

        Raises:
            ValueError: If proposal doesn't exist, voting not active, or weight invalid
        """
        if proposal_id not in self.proposals:
            raise ValueError(f"Proposal {proposal_id} does not exist")

        proposal = self.proposals[proposal_id]

        if proposal.status != ProposalStatus.ACTIVE:
            raise ValueError(
                f"Voting not active for proposal {proposal_id} (status: {proposal.status})"
            )

        # Check if voting period has expired
        if datetime.now() > proposal.voting_end:
            proposal.status = ProposalStatus.EXPIRED
            raise ValueError("Voting period has expired")

        if weight <= 0:
            raise ValueError("Weight must be positive")

        # Check if voter is registered and has sufficient weight
        if voter_id not in self.registered_voters:
            raise ValueError(f"Voter {voter_id} is not registered")

        if weight > self.registered_voters[voter_id]:
            raise ValueError(
                f"Weight {weight} exceeds voter's registered weight "
                f"{self.registered_voters[voter_id]}"
            )

        # Record or update vote
        vote = Vote(voter_id=voter_id, choice=choice, weight=weight)

        self.votes[proposal_id][voter_id] = vote

    def tally_votes(self, proposal_id: str) -> Dict[str, Any]:
        """
        Tally votes for a proposal and determine outcome.

        Args:
            proposal_id: ID of the proposal

        Returns:
            Dictionary with vote tallies and result:
            - yes_votes: Total weight of YES votes
            - no_votes: Total weight of NO votes
            - abstain_votes: Total weight of ABSTAIN votes
            - total_votes: Total weight of all votes
            - quorum_met: Whether quorum was reached
            - passed: Whether proposal passed

        Raises:
            ValueError: If proposal doesn't exist
        """
        if proposal_id not in self.proposals:
            raise ValueError(f"Proposal {proposal_id} does not exist")

        if proposal_id not in self.votes:
            # No votes yet
            return {
                "yes_votes": 0.0,
                "no_votes": 0.0,
                "abstain_votes": 0.0,
                "total_votes": 0.0,
                "quorum_met": False,
                "passed": False,
            }

        # Calculate vote tallies
        yes_votes = 0.0
        no_votes = 0.0
        abstain_votes = 0.0

        for vote in self.votes[proposal_id].values():
            if vote.choice == VoteChoice.YES:
                yes_votes += vote.weight
            elif vote.choice == VoteChoice.NO:
                no_votes += vote.weight
            else:  # ABSTAIN
                abstain_votes += vote.weight

        total_votes = yes_votes + no_votes + abstain_votes

        # Check quorum (total votes / total voting weight)
        quorum_met = (
            (total_votes / self.total_voting_weight) >= self.quorum_percentage
            if self.total_voting_weight > 0
            else False
        )

        # Check approval (yes votes / (yes + no votes))
        # Abstain votes don't count toward approval calculation
        votes_for_approval = yes_votes + no_votes
        approval_met = (
            (yes_votes / votes_for_approval) >= self.approval_threshold
            if votes_for_approval > 0
            else False
        )

        passed = quorum_met and approval_met

        return {
            "yes_votes": yes_votes,
            "no_votes": no_votes,
            "abstain_votes": abstain_votes,
            "total_votes": total_votes,
            "quorum_met": quorum_met,
            "approval_met": approval_met,
            "passed": passed,
        }

    def finalize_proposal(self, proposal_id: str):
        """
        Finalize a proposal after voting period ends.

        Updates proposal status based on vote tally.

        Args:
            proposal_id: ID of the proposal

        Raises:
            ValueError: If proposal doesn't exist or is not active
        """
        if proposal_id not in self.proposals:
            raise ValueError(f"Proposal {proposal_id} does not exist")

        proposal = self.proposals[proposal_id]

        if proposal.status != ProposalStatus.ACTIVE:
            raise ValueError(
                f"Proposal must be active to finalize (status: {proposal.status})"
            )

        # Tally votes
        result = self.tally_votes(proposal_id)

        # Update status based on result
        if result["passed"]:
            proposal.status = ProposalStatus.PASSED
        else:
            proposal.status = ProposalStatus.REJECTED

    def execute_proposal(self, proposal_id: str):
        """
        Execute a passed proposal by applying parameter changes.

        Args:
            proposal_id: ID of the proposal

        Raises:
            ValueError: If proposal doesn't exist or hasn't passed
        """
        if proposal_id not in self.proposals:
            raise ValueError(f"Proposal {proposal_id} does not exist")

        proposal = self.proposals[proposal_id]

        if proposal.status != ProposalStatus.PASSED:
            raise ValueError(
                f"Proposal must be passed to execute (status: {proposal.status})"
            )

        # Apply parameter changes
        for param, value in proposal.parameter_changes.items():
            self.parameters[param] = value

        # Mark as executed
        proposal.status = ProposalStatus.EXECUTED

    def get_parameter(self, param_name: str) -> Any:
        """Get current value of a parameter."""
        if param_name not in self.parameters:
            raise ValueError(f"Parameter '{param_name}' does not exist")
        return self.parameters[param_name]

    def get_proposal(self, proposal_id: str) -> Optional[Proposal]:
        """Get proposal by ID."""
        return self.proposals.get(proposal_id)

    def list_proposals(self, status: Optional[ProposalStatus] = None) -> list[Proposal]:
        """
        List all proposals, optionally filtered by status.

        Args:
            status: Optional status filter

        Returns:
            List of proposals
        """
        if status is None:
            return list(self.proposals.values())
        return [p for p in self.proposals.values() if p.status == status]

    def _validate_parameter_changes(self, parameter_changes: Dict[str, Any]):
        """
        Validate proposed parameter changes.

        Args:
            parameter_changes: Dict of parameter names to new values

        Raises:
            ValueError: If any parameter value is invalid
        """
        for param, value in parameter_changes.items():
            if param == "k_plan":
                if not isinstance(value, int) or value <= 0:
                    raise ValueError("k_plan must be a positive integer")

            elif param == "k_result":
                if not isinstance(value, int) or value <= 0:
                    raise ValueError("k_result must be a positive integer")

            elif param == "bounty_cap":
                if not isinstance(value, (int, float)) or value <= 0:
                    raise ValueError("bounty_cap must be a positive number")

            elif param == "slashing_percentage":
                if not isinstance(value, (int, float)) or not (0 <= value <= 1):
                    raise ValueError("slashing_percentage must be between 0 and 1")
