"""
Unit tests for Challenge Verification Core.

Tests:
- Verification logic for each proof type
- Queue prioritization by bond amount
- Escalation paths for disputes
"""

import sys
import os
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from challenges.proofs import ProofType
from challenges.verification import ChallengeVerifier, VerificationResult
from challenges.queue import ChallengeQueue, QueuedChallenge
from challenges.escalation import EscalationHandler, VerifierVerdict, EscalationLevel


class TestSchemaViolationVerification:
    """Test schema violation verification"""
    
    def test_schema_violation_detected(self):
        """Test detection of schema violations"""
        verifier = ChallengeVerifier()
        
        evidence = {
            'expected_schema': {
                'name': {'type': 'string'},
                'age': {'type': 'integer'},
                'email': {'type': 'string'}
            },
            'actual_output': {
                'name': 'John',
                'age': 'thirty',  # Wrong type
                # email missing
            },
            'violations': ['age', 'email']
        }
        
        result = verifier.verify_schema_violation(evidence)
        
        assert result.is_valid  # Challenge is valid (violations found)
        assert result.gas_used > 0
        assert len(result.evidence['violations_found']) == 2
        assert result.gas_used <= verifier.gas_limit
    
    def test_no_schema_violations(self):
        """Test when output matches schema"""
        verifier = ChallengeVerifier()
        
        evidence = {
            'expected_schema': {
                'name': {'type': 'string'},
                'age': {'type': 'integer'}
            },
            'actual_output': {
                'name': 'John',
                'age': 30
            },
            'violations': []
        }
        
        result = verifier.verify_schema_violation(evidence)
        
        assert not result.is_valid  # Challenge invalid (no violations)
        assert result.gas_used > 0


class TestCitationVerification:
    """Test citation verification"""
    
    def test_missing_citations_detected(self):
        """Test detection of missing citations"""
        verifier = ChallengeVerifier()
        
        evidence = {
            'required_citations': ['source-1', 'source-2', 'source-3'],
            'provided_citations': ['source-1']  # Missing source-2 and source-3
        }
        
        result = verifier.verify_missing_citation(evidence)
        
        assert result.is_valid  # Challenge valid (missing citations)
        assert len(result.evidence['missing_citations']) == 2
        assert 'source-2' in result.evidence['missing_citations']
        assert 'source-3' in result.evidence['missing_citations']
    
    def test_all_citations_present(self):
        """Test when all citations are provided"""
        verifier = ChallengeVerifier()
        
        evidence = {
            'required_citations': ['source-1', 'source-2'],
            'provided_citations': ['source-1', 'source-2', 'source-3']  # Extra is OK
        }
        
        result = verifier.verify_missing_citation(evidence)
        
        assert not result.is_valid  # Challenge invalid (all present)
        assert len(result.evidence['missing_citations']) == 0


class TestSemanticContradiction:
    """Test semantic contradiction detection"""
    
    def test_contradiction_detected(self):
        """Test detection of contradictory statements"""
        verifier = ChallengeVerifier()
        
        evidence = {
            'statements': [
                'The result is true and valid',
                'The result is false and invalid'
            ],
            'contradiction_type': 'logical'
        }
        
        result = verifier.verify_semantic_contradiction(evidence)
        
        assert result.is_valid  # Challenge valid (contradiction found)
        assert len(result.evidence['contradictions']) > 0
    
    def test_no_contradiction(self):
        """Test when statements don't contradict"""
        verifier = ChallengeVerifier()
        
        evidence = {
            'statements': [
                'The sky is blue',
                'The grass is green'
            ],
            'contradiction_type': 'logical'
        }
        
        result = verifier.verify_semantic_contradiction(evidence)
        
        # These statements don't contradict
        assert not result.is_valid


class TestOutputMismatch:
    """Test output mismatch verification"""
    
    def test_output_mismatch_detected(self):
        """Test detection of output that doesn't match specification"""
        verifier = ChallengeVerifier()
        
        evidence = {
            'specified_output': {
                'result': 'success',
                'count': 10,
                'message': 'Completed'
            },
            'actual_output': {
                'result': 'failed',  # Mismatch
                'count': 5,  # Mismatch
                'message': 'Completed'  # Match
            },
            'mismatch_fields': ['result', 'count']
        }
        
        result = verifier.verify_output_mismatch(evidence)
        
        assert result.is_valid  # Challenge valid (mismatches found)
        assert len(result.evidence['mismatches']) == 2
    
    def test_output_matches_spec(self):
        """Test when output matches specification"""
        verifier = ChallengeVerifier()
        
        evidence = {
            'specified_output': {'result': 'success'},
            'actual_output': {'result': 'success'},
            'mismatch_fields': []
        }
        
        result = verifier.verify_output_mismatch(evidence)
        
        assert not result.is_valid  # Challenge invalid (output matches)


class TestChallengeQueue:
    """Test challenge queue management"""
    
    def test_add_challenge_to_queue(self):
        """Test adding challenges to queue"""
        db_path = Path(tempfile.mktemp())
        queue = ChallengeQueue(db_path)
        
        challenge = queue.add_challenge(
            challenge_id="challenge-1",
            task_id="task-1",
            commit_id="commit-1",
            challenger_id="alice",
            proof_data={'type': 'schema_violation'},
            bond_amount=100
        )
        
        assert challenge.challenge_id == "challenge-1"
        assert challenge.bond_amount == 100
        assert challenge.status == 'queued'
        assert queue.get_queue_size() == 1
    
    def test_queue_prioritization_by_bond(self):
        """Test higher bonds get higher priority"""
        db_path = Path(tempfile.mktemp())
        queue = ChallengeQueue(db_path)
        
        # Add challenges with different bonds
        queue.add_challenge("low", "task-1", "commit-1", "alice", {}, 50)
        queue.add_challenge("high", "task-2", "commit-2", "bob", {}, 500)
        queue.add_challenge("mid", "task-3", "commit-3", "charlie", {}, 200)
        
        # Get next should return highest bond first
        next_challenge = queue.get_next_challenge()
        assert next_challenge.challenge_id == "high"
        assert next_challenge.bond_amount == 500
    
    def test_queue_priority_ordering(self):
        """Test prioritize_by_bond returns correct order"""
        db_path = Path(tempfile.mktemp())
        queue = ChallengeQueue(db_path)
        
        queue.add_challenge("c1", "task-1", "commit-1", "alice", {}, 100)
        queue.add_challenge("c2", "task-2", "commit-2", "bob", {}, 500)
        queue.add_challenge("c3", "task-3", "commit-3", "charlie", {}, 250)
        
        ordered = queue.prioritize_by_bond()
        
        assert len(ordered) == 3
        assert ordered[0].bond_amount == 500
        assert ordered[1].bond_amount == 250
        assert ordered[2].bond_amount == 100
    
    def test_mark_verified(self):
        """Test marking challenge as verified"""
        db_path = Path(tempfile.mktemp())
        queue = ChallengeQueue(db_path)
        
        queue.add_challenge("c1", "task-1", "commit-1", "alice", {}, 100)
        
        result = {'is_valid': True, 'reason': 'Verified'}
        success = queue.mark_verified("c1", result)
        
        assert success
        assert queue.get_queue_size('verified') == 1
        assert queue.get_queue_size('queued') == 0


class TestEscalation:
    """Test escalation handling"""
    
    def test_no_escalation_with_agreement(self):
        """Test no escalation when verifiers agree"""
        handler = EscalationHandler()
        
        verdicts = [
            VerifierVerdict("v1", True, 0.9),
            VerifierVerdict("v2", True, 0.85),
            VerifierVerdict("v3", True, 0.95)
        ]
        
        needs_escalation, level, reason = handler.check_escalation_needed(
            "challenge-1", verdicts, bond_amount=100
        )
        
        assert not needs_escalation
    
    def test_escalation_on_disagreement(self):
        """Test escalation when verifiers disagree"""
        handler = EscalationHandler()
        
        verdicts = [
            VerifierVerdict("v1", True, 0.9),
            VerifierVerdict("v2", False, 0.8),  # Disagrees
            VerifierVerdict("v3", True, 0.85)
        ]
        
        needs_escalation, level, reason = handler.check_escalation_needed(
            "challenge-1", verdicts, bond_amount=100
        )
        
        assert needs_escalation
        assert level == EscalationLevel.VERIFIER_CONSENSUS
    
    def test_escalation_on_low_confidence(self):
        """Test escalation when confidence is low"""
        handler = EscalationHandler()
        
        verdicts = [
            VerifierVerdict("v1", True, 0.5),  # Low
            VerifierVerdict("v2", True, 0.6),  # Low
            VerifierVerdict("v3", True, 0.5)   # Low
        ]
        
        needs_escalation, level, reason = handler.check_escalation_needed(
            "challenge-1", verdicts, bond_amount=100
        )
        
        assert needs_escalation
        assert level == EscalationLevel.HUMAN_REVIEW
    
    def test_escalation_on_high_value_bond(self):
        """Test escalation for high-value bonds"""
        handler = EscalationHandler()
        
        verdicts = [
            VerifierVerdict("v1", True, 0.9),
            VerifierVerdict("v2", True, 0.9)
        ]
        
        needs_escalation, level, reason = handler.check_escalation_needed(
            "challenge-1", verdicts, bond_amount=1000  # High value
        )
        
        assert needs_escalation
        assert level == EscalationLevel.GOVERNANCE_VOTE
    
    def test_escalate_if_disagree(self):
        """Test escalate_if_disagree creates escalation case"""
        handler = EscalationHandler()
        
        verdicts = [
            VerifierVerdict("v1", True, 0.9),
            VerifierVerdict("v2", False, 0.8)
        ]
        
        escalation = handler.escalate_if_disagree("challenge-1", verdicts)
        
        assert escalation is not None
        assert escalation.challenge_id == "challenge-1"
        assert not escalation.resolved
        assert len(escalation.verdicts) == 2
    
    def test_get_pending_escalations(self):
        """Test retrieving pending escalations"""
        handler = EscalationHandler()
        
        verdicts = [
            VerifierVerdict("v1", True, 0.5),
            VerifierVerdict("v2", True, 0.5)
        ]
        
        handler.escalate_if_disagree("c1", verdicts)
        handler.escalate_if_disagree("c2", verdicts)
        
        pending = handler.get_pending_escalations()
        assert len(pending) == 2
        
        # Resolve one
        handler.resolve_escalation(pending[0].escalation_id, {'outcome': 'upheld'})
        
        pending = handler.get_pending_escalations()
        assert len(pending) == 1
