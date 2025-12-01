"""Merkle tree implementation for checkpoint verification.

Provides cryptographic commitment to state with efficient proof generation
and verification for individual elements.
"""

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class MerkleProof:
    """Proof that a leaf is part of a Merkle tree."""

    leaf_index: int
    leaf_hash: str
    siblings: List[Tuple[str, bool]]  # (hash, is_right_sibling)
    root_hash: str


class MerkleTree:
    """
    Merkle tree for cryptographic commitment to a set of values.

    Supports efficient proof generation and verification for membership.
    """

    def __init__(self):
        """Initialize empty Merkle tree."""
        self.leaves: List[str] = []
        self.tree: List[List[str]] = []
        self.root_hash: Optional[str] = None

    def build_tree(self, leaves: List[str]) -> str:
        """
        Build Merkle tree from leaf hashes.

        Args:
            leaves: List of leaf hashes (hex strings)

        Returns:
            Root hash of the tree
        """
        if not leaves:
            # Empty tree has a special root
            self.root_hash = self._hash("")
            return self.root_hash

        self.leaves = leaves.copy()

        # Build tree bottom-up
        current_level = leaves.copy()
        self.tree = [current_level.copy()]

        while len(current_level) > 1:
            next_level = []

            # Process pairs
            for i in range(0, len(current_level), 2):
                left = current_level[i]

                if i + 1 < len(current_level):
                    # Pair exists
                    right = current_level[i + 1]
                else:
                    # Odd number, duplicate last element
                    right = left

                parent = self._hash_pair(left, right)
                next_level.append(parent)

            self.tree.append(next_level.copy())
            current_level = next_level

        self.root_hash = current_level[0]

        logger.debug(
            f"Built Merkle tree with {len(leaves)} leaves, "
            f"root: {self.root_hash[:8]}..."
        )

        return self.root_hash

    def get_proof(self, leaf_index: int) -> Optional[MerkleProof]:
        """
        Generate Merkle proof for a leaf.

        Args:
            leaf_index: Index of the leaf (0-indexed)

        Returns:
            MerkleProof if leaf exists, None otherwise
        """
        if not self.tree or leaf_index >= len(self.leaves):
            return None

        siblings = []
        current_index = leaf_index

        # Traverse from leaf to root
        for level_idx in range(len(self.tree) - 1):
            level = self.tree[level_idx]

            # Find sibling
            if current_index % 2 == 0:
                # Current is left child
                sibling_index = current_index + 1
                is_right = True
            else:
                # Current is right child
                sibling_index = current_index - 1
                is_right = False

            # Get sibling hash
            if sibling_index < len(level):
                sibling_hash = level[sibling_index]
            else:
                # No sibling (odd number at this level), use current
                sibling_hash = level[current_index]

            siblings.append((sibling_hash, is_right))

            # Move to parent
            current_index = current_index // 2

        return MerkleProof(
            leaf_index=leaf_index,
            leaf_hash=self.leaves[leaf_index],
            siblings=siblings,
            root_hash=self.root_hash,
        )

    def verify_proof(self, leaf_hash: str, proof: MerkleProof, root_hash: str) -> bool:
        """
        Verify a Merkle proof.

        Args:
            leaf_hash: Hash of the leaf to verify
            proof: Merkle proof
            root_hash: Expected root hash

        Returns:
            True if proof is valid
        """
        if leaf_hash != proof.leaf_hash:
            logger.warning("Leaf hash mismatch in proof")
            return False

        # Compute root from leaf and siblings
        current_hash = leaf_hash

        for sibling_hash, is_right in proof.siblings:
            if is_right:
                # Sibling is on the right
                current_hash = self._hash_pair(current_hash, sibling_hash)
            else:
                # Sibling is on the left
                current_hash = self._hash_pair(sibling_hash, current_hash)

        # Check if computed root matches expected
        if current_hash != root_hash:
            logger.warning(
                f"Root hash mismatch: computed {current_hash[:8]}... "
                f"vs expected {root_hash[:8]}..."
            )
            return False

        return True

    def _hash(self, data: str) -> str:
        """
        Hash a string.

        Args:
            data: String to hash

        Returns:
            Hex-encoded SHA256 hash
        """
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _hash_pair(self, left: str, right: str) -> str:
        """
        Hash a pair of hashes.

        Args:
            left: Left hash
            right: Right hash

        Returns:
            Combined hash
        """
        combined = left + right
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def get_root(self) -> Optional[str]:
        """
        Get the root hash of the tree.

        Returns:
            Root hash if tree is built, None otherwise
        """
        return self.root_hash

    def get_leaf_count(self) -> int:
        """
        Get number of leaves in the tree.

        Returns:
            Leaf count
        """
        return len(self.leaves)
