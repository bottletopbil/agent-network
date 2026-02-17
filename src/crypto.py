"""
Cryptographic operations for agent signatures and verification.

Supports both shared keypair (backward compatible) and per-agent keypairs.
"""

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, Tuple, Optional
from nacl.signing import SigningKey, VerifyKey


# Directory for storing per-agent keys
def _get_keys_dir() -> Path:
    """Get the directory for storing agent keypairs."""
    keys_dir = Path(os.getenv("SWARM_KEYS_DIR", os.path.expanduser("~/.swarm/keys")))
    keys_dir.mkdir(parents=True, exist_ok=True)
    return keys_dir


def cjson(obj: Dict[str, Any]) -> bytes:
    """Canonical JSON encoding."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def sha256_hex(data: bytes) -> str:
    """SHA256 hash as hex string."""
    import hashlib

    return hashlib.sha256(data).hexdigest()


def generate_keypair() -> Tuple[SigningKey, VerifyKey]:
    """
    Generate a new Ed25519 keypair.

    Returns:
        Tuple of (signing_key, verify_key)
    """
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key
    return signing_key, verify_key


def save_keypair(agent_id: str, signing_key: SigningKey) -> None:
    """
    Save agent's keypair to disk.

    Args:
        agent_id: Unique identifier for the agent
        signing_key: The signing key to save
    """
    keys_dir = _get_keys_dir()
    key_file = keys_dir / f"{agent_id}.key"

    # Save the seed (32 bytes)
    seed_b64 = base64.b64encode(signing_key.encode()).decode()

    with open(key_file, "w") as f:
        f.write(seed_b64)

    # Secure the file (owner read/write only)
    os.chmod(key_file, 0o600)


def load_keypair(agent_id: str) -> Tuple[SigningKey, VerifyKey]:
    """
    Load agent's keypair from disk.

    Args:
        agent_id: Unique identifier for the agent

    Returns:
        Tuple of (signing_key, verify_key)

    Raises:
        FileNotFoundError: If keypair doesn't exist for this agent
    """
    keys_dir = _get_keys_dir()
    key_file = keys_dir / f"{agent_id}.key"

    if not key_file.exists():
        raise FileNotFoundError(f"No keypair found for agent {agent_id}")

    with open(key_file, "r") as f:
        seed_b64 = f.read().strip()

    seed = base64.b64decode(seed_b64)
    signing_key = SigningKey(seed)
    verify_key = signing_key.verify_key

    return signing_key, verify_key


def load_verifier(agent_id: Optional[str] = None) -> VerifyKey:
    """
    Load a verifier key for compatibility with agent entrypoints.

    Resolution order:
    1. Per-agent keypair (if agent_id provided)
    2. SWARM_VERIFY_PK_B64 / SWARM_PUBLIC_KEY
    3. Derived from SWARM_SIGNING_SK_B64 / SWARM_PRIVATE_KEY

    Args:
        agent_id: Optional agent ID for per-agent key loading.

    Returns:
        VerifyKey instance.

    Raises:
        ValueError: If no verifier key material is available.
    """
    if agent_id:
        _, verify_key = load_keypair(agent_id)
        return verify_key

    pk_b64 = os.getenv("SWARM_VERIFY_PK_B64") or os.getenv("SWARM_PUBLIC_KEY")
    if pk_b64:
        return VerifyKey(base64.b64decode(pk_b64))

    sk_b64 = os.getenv("SWARM_SIGNING_SK_B64") or os.getenv("SWARM_PRIVATE_KEY")
    if sk_b64:
        signing_key = SigningKey(base64.b64decode(sk_b64))
        return signing_key.verify_key

    raise ValueError(
        "No verifier key found. Set SWARM_VERIFY_PK_B64 (preferred) or "
        "SWARM_SIGNING_SK_B64 in environment."
    )


def sign_with_key(signing_key: SigningKey, message: bytes) -> bytes:
    """
    Sign a message with a signing key.

    Args:
        signing_key: The key to sign with
        message: The message to sign

    Returns:
        Signature bytes
    """
    signed = signing_key.sign(message)
    # Return just the signature (last 64 bytes)
    return signed.signature


def sign_record(record: Dict[str, Any], agent_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Sign a record dictionary.

    Args:
        record: Dictionary to sign
        agent_id: Optional agent ID for per-agent signing. If None, uses env keypair.

    Returns:
        Record with signature fields added
    """
    # Determine which key to use
    if agent_id:
        # Use per-agent keypair
        try:
            signing_key, verify_key = load_keypair(agent_id)
        except FileNotFoundError:
            # Generate new keypair for this agent
            signing_key, verify_key = generate_keypair()
            save_keypair(agent_id, signing_key)
    else:
        # Fall back to env keypair (backward compatible)
        sk_b64 = os.getenv("SWARM_SIGNING_SK_B64") or os.getenv("SWARM_PRIVATE_KEY")
        if not sk_b64:
            raise ValueError("No SWARM_SIGNING_SK_B64 or SWARM_PRIVATE_KEY in environment")

        seed = base64.b64decode(sk_b64)
        signing_key = SigningKey(seed)
        verify_key = signing_key.verify_key

    # Create canonical message
    message = cjson(record)

    # Sign it
    signature = sign_with_key(signing_key, message)

    # Add signature fields
    result = dict(record)
    result["sig_b64"] = base64.b64encode(signature).decode()
    result["sig_pk_b64"] = base64.b64encode(bytes(verify_key)).decode()

    return result


def verify_record(record: Dict[str, Any]) -> bool:
    """
    Verify a signed record.

    Args:
        record: Signed record dictionary

    Returns:
        True if signature is valid, False otherwise
    """
    sig_b64 = record.get("sig_b64")
    pk_b64 = record.get("sig_pk_b64")

    if not sig_b64 or not pk_b64:
        return False

    try:
        # Extract signature and public key
        signature = base64.b64decode(sig_b64)
        pk_bytes = base64.b64decode(pk_b64)
        verify_key = VerifyKey(pk_bytes)

        # Reconstruct the message that was signed
        to_verify = {k: v for k, v in record.items() if k not in ("sig_b64", "sig_pk_b64")}
        message = cjson(to_verify)

        # Verify
        verify_key.verify(message, signature)
        return True

    except Exception:
        return False
