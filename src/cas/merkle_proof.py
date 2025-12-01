"""
Merkle Proof Generation and Verification

Provides Merkle tree construction and proof generation for verifying
envelope inclusion in threads.
"""

import hashlib
import json
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


def hash_data(data: bytes) -> str:
    """Compute SHA256 hash of data"""
    return hashlib.sha256(data).hexdigest()


def hash_envelope(envelope: Dict[str, Any]) -> str:
    """Compute hash of envelope (canonical JSON)"""
    envelope_bytes = json.dumps(envelope, sort_keys=True).encode("utf-8")
    return hash_data(envelope_bytes)


class MerkleProof:
    """
    Merkle proof generation and verification for thread envelopes.

    Constructs a Merkle tree from envelopes and generates proofs
    that an envelope is included in the tree.
    """

    @staticmethod
    def build_tree(leaves: List[str]) -> List[List[str]]:
        """
        Build Merkle tree from leaf hashes.

        Args:
            leaves: List of leaf hashes

        Returns:
            List of tree levels (bottom to top)
        """
        if not leaves:
            return [[]]

        tree = [leaves[:]]  # Copy leaves as first level

        # Build tree bottom-up
        current_level = leaves[:]

        while len(current_level) > 1:
            next_level = []

            # Process pairs
            for i in range(0, len(current_level), 2):
                left = current_level[i]

                # Handle odd number of nodes (duplicate last)
                if i + 1 < len(current_level):
                    right = current_level[i + 1]
                else:
                    right = left

                # Hash concatenation of left and right
                combined = left + right
                parent_hash = hash_data(combined.encode("utf-8"))
                next_level.append(parent_hash)

            tree.append(next_level)
            current_level = next_level

        return tree

    @staticmethod
    def get_root(tree: List[List[str]]) -> Optional[str]:
        """Get root hash from Merkle tree"""
        if not tree or not tree[-1]:
            return None
        return tree[-1][0]

    @staticmethod
    def build_proof(
        thread_envelopes: List[Dict[str, Any]], target_index: int
    ) -> Dict[str, Any]:
        """
        Build Merkle proof for envelope at target_index.

        Args:
            thread_envelopes: List of all envelopes in thread
            target_index: Index of envelope to prove

        Returns:
            Proof dictionary with path, siblings, and root
        """
        if target_index < 0 or target_index >= len(thread_envelopes):
            raise IndexError(f"Invalid target index: {target_index}")

        # Hash all envelopes
        leaves = [hash_envelope(env) for env in thread_envelopes]

        # Build Merkle tree
        tree = MerkleProof.build_tree(leaves)
        root = MerkleProof.get_root(tree)

        # Generate proof path
        proof_path = []
        siblings = []
        index = target_index

        # Walk up the tree
        for level in range(len(tree) - 1):
            level_nodes = tree[level]

            # Determine sibling
            if index % 2 == 0:
                # Target is left child
                sibling_index = index + 1
                is_left = True
            else:
                # Target is right child
                sibling_index = index - 1
                is_left = False

            # Get sibling hash (or duplicate if no sibling)
            if sibling_index < len(level_nodes):
                sibling = level_nodes[sibling_index]
            else:
                sibling = level_nodes[index]  # Duplicate

            siblings.append(sibling)
            proof_path.append("left" if is_left else "right")

            # Move to parent
            index = index // 2

        proof = {
            "target_index": target_index,
            "target_hash": leaves[target_index],
            "root": root,
            "siblings": siblings,
            "path": proof_path,
            "tree_size": len(leaves),
        }

        logger.debug(f"Built proof for index {target_index}: root={root[:16]}...")

        return proof

    @staticmethod
    def verify_proof(
        root_cid: str, envelope: Dict[str, Any], proof: Dict[str, Any]
    ) -> bool:
        """
        Verify Merkle proof for envelope.

        Args:
            root_cid: Expected root hash
            envelope: Envelope to verify
            proof: Merkle proof

        Returns:
            True if proof is valid
        """
        # Hash the envelope
        envelope_hash = hash_envelope(envelope)

        # Verify envelope hash matches proof
        if envelope_hash != proof.get("target_hash"):
            logger.warning(
                f"Envelope hash mismatch: {envelope_hash[:16]}... != "
                f"{proof.get('target_hash', '')[:16]}..."
            )
            return False

        # Reconstruct root from proof
        current_hash = envelope_hash
        siblings = proof.get("siblings", [])
        path = proof.get("path", [])

        for sibling, direction in zip(siblings, path):
            if direction == "left":
                # Current is left child
                combined = current_hash + sibling
            else:
                # Current is right child
                combined = sibling + current_hash

            current_hash = hash_data(combined.encode("utf-8"))

        # Verify computed root matches expected
        is_valid = current_hash == root_cid

        if is_valid:
            logger.debug(f"Proof verified successfully for envelope")
        else:
            logger.warning(
                f"Proof verification failed: computed root {current_hash[:16]}... "
                f"!= expected {root_cid[:16]}..."
            )

        return is_valid

    @staticmethod
    def compute_root_from_envelopes(envelopes: List[Dict[str, Any]]) -> str:
        """
        Compute Merkle root from list of envelopes.

        Args:
            envelopes: List of envelopes

        Returns:
            Merkle root hash
        """
        leaves = [hash_envelope(env) for env in envelopes]
        tree = MerkleProof.build_tree(leaves)
        root = MerkleProof.get_root(tree)
        return root or ""

    @staticmethod
    def verify_envelope_in_thread(
        envelope: Dict[str, Any],
        all_envelopes: List[Dict[str, Any]],
        expected_index: int,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Verify envelope is at expected position in thread.

        Args:
            envelope: Envelope to verify
            all_envelopes: All envelopes in thread
            expected_index: Expected position

        Returns:
            Tuple of (is_valid, proof)
        """
        try:
            # Build proof
            proof = MerkleProof.build_proof(all_envelopes, expected_index)
            root = proof["root"]

            # Verify proof
            is_valid = MerkleProof.verify_proof(root, envelope, proof)

            return is_valid, proof
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False, None
