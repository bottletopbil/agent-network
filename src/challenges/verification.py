"""
Challenge Verification: Core logic for verifying challenge proofs.

Implements deterministic verification rules for each proof type with gas metering
to prevent expensive verification attacks.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from challenges.proofs import ProofType, MAX_GAS_ESTIMATE


@dataclass
class VerificationResult:
    """Result of verifying a challenge proof"""

    is_valid: bool
    gas_used: int
    reason: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "gas_used": self.gas_used,
            "reason": self.reason,
            "evidence": self.evidence or {},
        }


class ChallengeVerifier:
    """
    Verify challenge proofs using deterministic rules.

    Each proof type has specific verification logic:
    - SCHEMA_VIOLATION: Check output against expected schema
    - MISSING_CITATION: Verify required citations present
    - SEMANTIC_CONTRADICTION: Detect logical contradictions
    - OUTPUT_MISMATCH: Compare output against specification
    - POLICY_BREACH: Verify policy compliance
    """

    # Gas costs for verification operations
    GAS_BASE = 1000  # Base cost per verification
    GAS_PER_FIELD = 100  # Cost per field checked
    GAS_PER_CITATION = 200  # Cost per citation verified
    GAS_CONTRADICTION_ANALYSIS = 5000  # Cost for semantic analysis

    def __init__(self):
        self.gas_limit = MAX_GAS_ESTIMATE

    def verify_proof(
        self,
        proof_type: ProofType,
        evidence_data: Dict[str, Any],
        commit_data: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """
        Verify a challenge proof.

        Args:
            proof_type: Type of proof to verify
            evidence_data: Evidence provided by challenger
            commit_data: Original commit data being challenged

        Returns:
            VerificationResult with validation outcome
        """
        if proof_type == ProofType.SCHEMA_VIOLATION:
            return self.verify_schema_violation(evidence_data, commit_data)
        elif proof_type == ProofType.MISSING_CITATION:
            return self.verify_missing_citation(evidence_data, commit_data)
        elif proof_type == ProofType.SEMANTIC_CONTRADICTION:
            return self.verify_semantic_contradiction(evidence_data, commit_data)
        elif proof_type == ProofType.OUTPUT_MISMATCH:
            return self.verify_output_mismatch(evidence_data, commit_data)
        elif proof_type == ProofType.POLICY_BREACH:
            return self.verify_policy_breach(evidence_data, commit_data)
        else:
            return VerificationResult(
                is_valid=False,
                gas_used=self.GAS_BASE,
                reason=f"Unknown proof type: {proof_type}",
            )

    def verify_schema_violation(
        self, evidence: Dict[str, Any], commit_data: Optional[Dict[str, Any]] = None
    ) -> VerificationResult:
        """
        Verify SCHEMA_VIOLATION proof.

        Checks if output violates expected schema.

        Evidence should contain:
        - expected_schema: Expected field structure
        - actual_output: Actual output from commit
        - violations: List of violated fields
        """
        gas_used = self.GAS_BASE

        expected_schema = evidence.get("expected_schema", {})
        actual_output = evidence.get("actual_output", {})
        claimed_violations = evidence.get("violations", [])

        if not expected_schema or not actual_output:
            return VerificationResult(
                is_valid=False,
                gas_used=gas_used,
                reason="Missing expected_schema or actual_output",
            )

        # Check each claimed violation
        violations_found = []
        for field in claimed_violations:
            gas_used += self.GAS_PER_FIELD

            if field not in expected_schema:
                continue

            expected_type = expected_schema[field].get("type")
            actual_value = actual_output.get(field)

            # Check type mismatch
            if actual_value is None:
                violations_found.append(f"{field}: missing")
            elif expected_type and not self._check_type(actual_value, expected_type):
                violations_found.append(
                    f"{field}: expected {expected_type}, got {type(actual_value).__name__}"
                )

        is_valid = len(violations_found) > 0

        return VerificationResult(
            is_valid=is_valid,
            gas_used=min(gas_used, self.gas_limit),
            reason=(
                f"Found {len(violations_found)} schema violations"
                if is_valid
                else "No violations found"
            ),
            evidence={"violations_found": violations_found},
        )

    def verify_missing_citation(
        self, evidence: Dict[str, Any], commit_data: Optional[Dict[str, Any]] = None
    ) -> VerificationResult:
        """
        Verify MISSING_CITATION proof.

        Checks if required citations are missing.

        Evidence should contain:
        - required_citations: List of required citation IDs
        - provided_citations: Citations actually included
        """
        gas_used = self.GAS_BASE

        required = evidence.get("required_citations", [])
        provided = evidence.get("provided_citations", [])

        # Check each required citation
        missing_citations = []
        for citation_id in required:
            gas_used += self.GAS_PER_CITATION

            if citation_id not in provided:
                missing_citations.append(citation_id)

        is_valid = len(missing_citations) > 0

        return VerificationResult(
            is_valid=is_valid,
            gas_used=min(gas_used, self.gas_limit),
            reason=(
                f"Found {len(missing_citations)} missing citations"
                if is_valid
                else "All citations present"
            ),
            evidence={"missing_citations": missing_citations},
        )

    def verify_semantic_contradiction(
        self, evidence: Dict[str, Any], commit_data: Optional[Dict[str, Any]] = None
    ) -> VerificationResult:
        """
        Verify SEMANTIC_CONTRADICTION proof.

        Detects logical contradictions in output.

        Evidence should contain:
        - statements: List of contradicting statements
        - contradiction_type: Type of contradiction (logical, temporal, factual)
        """
        gas_used = self.GAS_BASE + self.GAS_CONTRADICTION_ANALYSIS

        statements = evidence.get("statements", [])
        contradiction_type = evidence.get("contradiction_type", "unknown")

        if len(statements) < 2:
            return VerificationResult(
                is_valid=False,
                gas_used=gas_used,
                reason="Need at least 2 statements to detect contradiction",
            )

        # Basic contradiction detection (simplified for demo)
        # In production, would use NLP/logic systems
        contradictions_found = []

        for i, stmt1 in enumerate(statements):
            for stmt2 in statements[i + 1 :]:
                if self._detect_simple_contradiction(stmt1, stmt2):
                    contradictions_found.append(
                        {
                            "statement1": stmt1,
                            "statement2": stmt2,
                            "type": contradiction_type,
                        }
                    )

        is_valid = len(contradictions_found) > 0

        return VerificationResult(
            is_valid=is_valid,
            gas_used=min(gas_used, self.gas_limit),
            reason=(
                f"Found {len(contradictions_found)} contradictions"
                if is_valid
                else "No contradictions found"
            ),
            evidence={"contradictions": contradictions_found},
        )

    def verify_output_mismatch(
        self, evidence: Dict[str, Any], commit_data: Optional[Dict[str, Any]] = None
    ) -> VerificationResult:
        """
        Verify OUTPUT_MISMATCH proof.

        Compares output against specification.

        Evidence should contain:
        - specified_output: What was specified/expected
        - actual_output: What was actually produced
        - mismatch_fields: Fields that don't match
        """
        gas_used = self.GAS_BASE

        specified = evidence.get("specified_output", {})
        actual = evidence.get("actual_output", {})
        claimed_mismatches = evidence.get("mismatch_fields", [])

        mismatches_found = []
        for field in claimed_mismatches:
            gas_used += self.GAS_PER_FIELD

            specified_value = specified.get(field)
            actual_value = actual.get(field)

            if specified_value != actual_value:
                mismatches_found.append(
                    {
                        "field": field,
                        "specified": specified_value,
                        "actual": actual_value,
                    }
                )

        is_valid = len(mismatches_found) > 0

        return VerificationResult(
            is_valid=is_valid,
            gas_used=min(gas_used, self.gas_limit),
            reason=(
                f"Found {len(mismatches_found)} output mismatches"
                if is_valid
                else "Output matches specification"
            ),
            evidence={"mismatches": mismatches_found},
        )

    def verify_policy_breach(
        self, evidence: Dict[str, Any], commit_data: Optional[Dict[str, Any]] = None
    ) -> VerificationResult:
        """
        Verify POLICY_BREACH proof.

        Checks if commit violates protocol policy.

        Evidence should contain:
        - policy_rule: Which policy was breached
        - violation_details: Details of the breach
        """
        gas_used = self.GAS_BASE + (self.GAS_PER_FIELD * 3)

        policy_rule = evidence.get("policy_rule")
        violation_details = evidence.get("violation_details", {})

        if not policy_rule:
            return VerificationResult(
                is_valid=False, gas_used=gas_used, reason="No policy rule specified"
            )

        # Check specific policy breach (simplified)
        # In production, would reference actual policy engine
        is_valid = len(violation_details) > 0

        return VerificationResult(
            is_valid=is_valid,
            gas_used=min(gas_used, self.gas_limit),
            reason=(
                f"Policy breach confirmed: {policy_rule}"
                if is_valid
                else "No policy breach detected"
            ),
            evidence={"policy_rule": policy_rule, "details": violation_details},
        )

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type"""
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "object": dict,
            "array": list,
        }

        expected = type_map.get(expected_type.lower())
        if expected is None:
            return True  # Unknown type, allow it

        return isinstance(value, expected)

    def _detect_simple_contradiction(self, stmt1: str, stmt2: str) -> bool:
        """
        Simple contradiction detection (for demo).

        Checks for opposing keywords like "is/is not", "true/false", etc.
        """
        opposing_pairs = [
            (" is ", " is not "),
            (" true", " false"),
            (" yes", " no"),
            (" correct", " incorrect"),
            (" valid", " invalid"),
        ]

        stmt1_lower = stmt1.lower()
        stmt2_lower = stmt2.lower()

        for pos, neg in opposing_pairs:
            if (pos in stmt1_lower and neg in stmt2_lower) or (
                neg in stmt1_lower and pos in stmt2_lower
            ):
                # Check if they're talking about the same subject (very simplified)
                common_words = set(stmt1_lower.split()) & set(stmt2_lower.split())
                if len(common_words) >= 3:  # At least 3 common words
                    return True

        return False
