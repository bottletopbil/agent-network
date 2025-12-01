"""
Challenge Bond Calculation: Calculate required bonds for challenge submissions.

Bond amounts vary by proof type and complexity to prevent frivolous challenges
while ensuring serious challengers can participate.
"""

from enum import Enum
from challenges.proofs import ProofType


# Base bond amounts by proof type (in credits)
BASE_BOND_AMOUNTS = {
    ProofType.SCHEMA_VIOLATION: 10,
    ProofType.MISSING_CITATION: 25,
    ProofType.SEMANTIC_CONTRADICTION: 50,
    ProofType.OUTPUT_MISMATCH: 100,
    ProofType.POLICY_BREACH: 75,  # Added POLICY_BREACH
}


class ComplexityLevel(Enum):
    """Complexity multipliers for bond calculation"""

    SIMPLE = 1  # 1x multiplier
    MODERATE = 2  # 2x multiplier
    COMPLEX = 5  # 5x multiplier


class BondCalculator:
    """
    Calculate required bond amounts for challenge submissions.

    Bonds are calculated based on:
    - Proof type (different violation types have different base costs)
    - Complexity level (simple/moderate/complex with multipliers)
    """

    def __init__(self):
        self.base_amounts = BASE_BOND_AMOUNTS

    def calculate_bond(
        self,
        proof_type: ProofType,
        complexity: ComplexityLevel = ComplexityLevel.SIMPLE,
    ) -> int:
        """
        Calculate required bond for a challenge.

        Args:
            proof_type: Type of proof being submitted
            complexity: Complexity level of the challenge

        Returns:
            Required bond amount in credits

        Raises:
            ValueError: If proof_type not recognized
        """
        if proof_type not in self.base_amounts:
            raise ValueError(f"Unknown proof type: {proof_type}")

        base_amount = self.base_amounts[proof_type]
        multiplier = complexity.value

        return base_amount * multiplier

    def get_base_amount(self, proof_type: ProofType) -> int:
        """Get base bond amount for a proof type (without multiplier)"""
        if proof_type not in self.base_amounts:
            raise ValueError(f"Unknown proof type: {proof_type}")
        return self.base_amounts[proof_type]

    def get_all_base_amounts(self) -> dict:
        """Get all base bond amounts"""
        return {pt: amount for pt, amount in self.base_amounts.items()}


def calculate_bond_simple(
    proof_type: ProofType, complexity: ComplexityLevel = ComplexityLevel.SIMPLE
) -> int:
    """
    Convenience function to calculate bond without creating calculator instance.

    Args:
        proof_type: Type of proof
        complexity: Complexity level

    Returns:
        Required bond amount
    """
    calculator = BondCalculator()
    return calculator.calculate_bond(proof_type, complexity)
