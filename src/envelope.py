import base64, json, os, time, uuid
from typing import Any, Dict, Optional
from hashlib import sha256

from crypto import sign_record, verify_record  # re-use your Ed25519 helpers
from lamport import Lamport

CLOCK = Lamport()

def _cjson(obj: Dict[str, Any]) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()

def _hash_payload(payload: Dict[str, Any]) -> str:
    return sha256(_cjson(payload)).hexdigest()

def make_envelope(
    *,
    kind: str,            # e.g. "NEED","PLAN","DECIDE","COMMIT","ATTEST","FINAL"
    thread_id: str,
    sender_pk_b64: str,   # who is sending (their public key)
    payload: Dict[str, Any],
    policy_engine_hash: Optional[str] = None,
    nonce: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a canonical, unsigned envelope.
    """
    # Import here to avoid circular dependency with policy.py
    from policy import current_policy_hash
    
    lamport = CLOCK.tick()
    return {
        "v": 1,
        "id": str(uuid.uuid4()),
        "thread_id": thread_id,
        "kind": kind,
        "lamport": lamport,
        "ts_ns": time.time_ns(),
        "sender_pk_b64": sender_pk_b64,
        "payload_hash": _hash_payload(payload),
        "payload": payload,
        "policy_engine_hash": policy_engine_hash or current_policy_hash(),
        "nonce": nonce or str(uuid.uuid4()),
    }

SIGN_FIELDS_EXCLUDE = {"sig_pk_b64", "sig_b64"}  # ensure sig covers everything else

def sign_envelope(env: Dict[str, Any]) -> Dict[str, Any]:
    # reuse sign_record so the same key material is used
    to_sign = {k: v for k, v in env.items() if k not in SIGN_FIELDS_EXCLUDE}
    return sign_record(to_sign)

def verify_envelope(env: Dict[str, Any]) -> bool:
    # lamport sanity: must be positive int
    if not isinstance(env.get("lamport"), int) or env["lamport"] <= 0:
        return False
    # payload hash must match
    ph = env.get("payload_hash")
    if ph != _hash_payload(env.get("payload", {})):
        return False
    return verify_record(env)

def observe_envelope(env: Dict[str, Any]) -> None:
    """
    Update our local Lamport clock when receiving an envelope.
    """
    lam = int(env.get("lamport", 0))
    if lam > 0:
        CLOCK.observe(lam)
