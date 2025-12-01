"""
Feature Extraction for Contextual Bandits

Extracts numeric feature vectors from task NEEDs for context-aware routing.
"""

from typing import Dict, Any, List
import logging
import hashlib

logger = logging.getLogger(__name__)


class FeatureExtractor:
    """
    Extracts contextual features from task NEEDs.

    Features include:
    - Domain (hashed categorical)
    - Complexity estimate
    - Deadline urgency
    - Budget constraints
    """

    def __init__(self, feature_dim: int = 10):
        """
        Initialize feature extractor.

        Args:
            feature_dim: Dimension of feature vector
        """
        self.feature_dim = feature_dim

    def extract_context(self, need: Dict[str, Any]) -> List[float]:
        """
        Extract feature vector from NEED.

        Args:
            need: Task NEED payload

        Returns:
            Feature vector (list of floats)
        """
        features = []

        # Feature 1-3: Domain features (one-hot-like encoding)
        domain_features = self._extract_domain_features(need)
        features.extend(domain_features)

        # Feature 4: Complexity (0.0 - 1.0)
        complexity = self._estimate_complexity(need)
        features.append(complexity)

        # Feature 5: Deadline urgency (0.0 - 1.0)
        urgency = self._extract_urgency(need)
        features.append(urgency)

        # Feature 6: Budget constraint (0.0 - 1.0)
        budget_normalized = self._extract_budget(need)
        features.append(budget_normalized)

        # Feature 7: Input size estimate (0.0 - 1.0)
        input_size = self._estimate_input_size(need)
        features.append(input_size)

        # Feature 8: Required capabilities count (normalized)
        capability_count = (
            len(need.get("capabilities", [])) / 10.0
        )  # Normalize by max ~10
        features.append(min(capability_count, 1.0))

        # Feature 9-10: Reserved for future extensions
        features.extend([0.0, 0.0])

        # Ensure fixed dimension
        while len(features) < self.feature_dim:
            features.append(0.0)

        return features[: self.feature_dim]

    def _extract_domain_features(self, need: Dict[str, Any]) -> List[float]:
        """
        Extract domain features (3 dimensions).

        Uses hash of primary tag to create pseudo one-hot encoding.

        Args:
            need: Task NEED

        Returns:
            3-dimensional domain feature vector
        """
        tags = need.get("tags", [])

        if not tags:
            return [0.33, 0.33, 0.33]  # Neutral

        # Use primary tag (first tag)
        primary_tag = tags[0]

        # Hash to 3 buckets
        hash_val = int(hashlib.md5(primary_tag.encode()).hexdigest(), 16)
        bucket = hash_val % 3

        # Create one-hot-like encoding
        features = [0.1, 0.1, 0.1]  # Small baseline
        features[bucket] = 0.9

        return features

    def _estimate_complexity(self, need: Dict[str, Any]) -> float:
        """
        Estimate task complexity (0.0 - 1.0).

        Based on:
        - Number of required capabilities
        - Description length
        - Constraint complexity

        Args:
            need: Task NEED

        Returns:
            Complexity score from 0.0 (simple) to 1.0 (complex)
        """
        complexity_score = 0.0

        # Number of capabilities (more = more complex)
        num_capabilities = len(need.get("capabilities", []))
        complexity_score += min(num_capabilities / 5.0, 0.3)

        # Description length (longer = more complex)
        description = need.get("description", "")
        desc_complexity = min(len(description) / 500.0, 0.3)
        complexity_score += desc_complexity

        # Number of constraints
        num_constraints = len(need.get("constraints", {}))
        complexity_score += min(num_constraints / 10.0, 0.2)

        # Has examples (simpler if examples provided)
        if need.get("examples"):
            complexity_score -= 0.1

        # Clamp to [0, 1]
        return max(0.0, min(1.0, complexity_score))

    def _extract_urgency(self, need: Dict[str, Any]) -> float:
        """
        Extract deadline urgency (0.0 - 1.0).

        Args:
            need: Task NEED

        Returns:
            Urgency from 0.0 (relaxed) to 1.0 (urgent)
        """
        # Check for explicit deadline
        deadline_ms = need.get("deadline_ms")

        if deadline_ms is None:
            return 0.5  # Neutral urgency

        # Map deadline to urgency (shorter deadline = higher urgency)
        # < 1 second = very urgent (1.0)
        # > 1 minute = relaxed (0.0)
        if deadline_ms < 1000:
            return 1.0
        elif deadline_ms > 60000:
            return 0.0
        else:
            # Linear interpolation
            return 1.0 - (deadline_ms - 1000) / (60000 - 1000)

    def _extract_budget(self, need: Dict[str, Any]) -> float:
        """
        Extract budget constraint (0.0 - 1.0).

        Args:
            need: Task NEED

        Returns:
            Budget from 0.0 (tight budget) to 1.0 (generous budget)
        """
        max_price = need.get("max_price")

        if max_price is None:
            return 1.0  # No budget constraint = generous

        # Normalize to [0, 1] based on typical price range
        # Assume typical range: 0-100 credits
        typical_max = 100.0
        normalized = min(max_price / typical_max, 1.0)

        return normalized

    def _estimate_input_size(self, need: Dict[str, Any]) -> float:
        """
        Estimate input data size (0.0 - 1.0).

        Args:
            need: Task NEED

        Returns:
            Size estimate from 0.0 (small) to 1.0 (large)
        """
        # Check input schema for array/list indicators
        input_schema = need.get("input_schema", {})

        if not input_schema:
            return 0.3  # Assume small by default

        # Look for array types
        properties = input_schema.get("properties", {})
        has_arrays = any(
            prop.get("type") == "array"
            for prop in properties.values()
            if isinstance(prop, dict)
        )

        if has_arrays:
            return 0.7  # Likely larger input

        # Count number of input fields
        num_fields = len(properties)
        return min(num_fields / 10.0, 0.5)


# Global extractor instance
_global_extractor: FeatureExtractor = None


def get_feature_extractor(feature_dim: int = 10) -> FeatureExtractor:
    """Get or create global feature extractor"""
    global _global_extractor
    if _global_extractor is None:
        _global_extractor = FeatureExtractor(feature_dim=feature_dim)
    return _global_extractor


def reset_feature_extractor() -> None:
    """Reset global extractor (for testing)"""
    global _global_extractor
    _global_extractor = None
