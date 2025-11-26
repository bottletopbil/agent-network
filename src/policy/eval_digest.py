"""
Policy Evaluation Digest

Provides cryptographic verification that a policy evaluation was performed correctly.
The digest is a hash of the input, decision, and policy hash.
"""

import hashlib
import json
from typing import Dict, Any


def compute_eval_digest(
    policy_input: Dict[str, Any],
    decision: Dict[str, Any],
    policy_hash: str
) -> str:
    """
    Compute a digest of a policy evaluation.
    
    The digest commits to:
    - The input that was evaluated
    - The decision that was reached
    - The version of the policy (via hash)
    
    Args:
        policy_input: The input that was evaluated
        decision: The decision that was reached
        policy_hash: Hash of the policy that was used
        
    Returns:
        Hex-encoded SHA256 digest
    """
    # Create a canonical representation
    canonical = {
        "input": _canonicalize(policy_input),
        "decision": _canonicalize(decision),
        "policy_hash": policy_hash
    }
    
    # Serialize to deterministic JSON
    serialized = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
    
    # Hash the serialized data
    digest = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
    
    return digest


def verify_eval_digest(envelope: Dict[str, Any]) -> bool:
    """
    Verify that a policy evaluation digest in an envelope is correct.
    
    Args:
        envelope: Message envelope containing policy_eval_digest
        
    Returns:
        True if the digest is valid, False otherwise
    """
    try:
        # Extract the claimed digest
        claimed_digest = envelope.get("policy_eval_digest")
        if not claimed_digest:
            return False
        
        # Extract the evaluation data
        policy_input = envelope.get("policy_input")
        decision = envelope.get("policy_decision")
        policy_hash = envelope.get("policy_hash")
        
        if not all([policy_input, decision, policy_hash]):
            return False
        
        # Recompute the digest
        actual_digest = compute_eval_digest(policy_input, decision, policy_hash)
        
        # Compare
        return actual_digest == claimed_digest
        
    except Exception:
        return False


def _canonicalize(obj: Any) -> Any:
    """
    Canonicalize an object for deterministic hashing.
    
    Handles:
    - Sorting dict keys
    - Sorting lists (if they represent sets)
    - Converting to standard types
    """
    if isinstance(obj, dict):
        return {k: _canonicalize(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, list):
        return [_canonicalize(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        # Convert unknown types to string
        return str(obj)


def create_eval_record(
    policy_input: Dict[str, Any],
    decision: Dict[str, Any],
    policy_hash: str
) -> Dict[str, Any]:
    """
    Create a complete evaluation record with digest.
    
    Args:
        policy_input: The input that was evaluated
        decision: The decision that was reached
        policy_hash: Hash of the policy that was used
        
    Returns:
        Dictionary containing input, decision, policy_hash, and digest
    """
    digest = compute_eval_digest(policy_input, decision, policy_hash)
    
    return {
        "policy_input": policy_input,
        "policy_decision": decision,
        "policy_hash": policy_hash,
        "policy_eval_digest": digest
    }
