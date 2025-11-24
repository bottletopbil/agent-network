import base64, json
from typing import Dict, Any
from hashlib import sha256

from envelope import verify_envelope
from cas import has_blob

# ---- Policy config (v0) ----
ALLOWED_KINDS = {"NEED", "PLAN", "COMMIT", "ATTEST", "FINAL", "FINALIZE", "DECIDE", "PROPOSE", "CLAIM", "YIELD", "RELEASE"}
MAX_PAYLOAD_BYTES = 64 * 1024  # 64 KB

# This dict defines the current rulebook. Hash it to pin the version.
_POLICY_SPEC = {
    "allowed_kinds": sorted(list(ALLOWED_KINDS)),
    "max_payload_bytes": MAX_PAYLOAD_BYTES,
    "require_artifact_for_commit": True,
    "hash_algo": "sha256",
    "version": 1,
}

def _cjson(obj: Dict[str, Any]) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()

def current_policy_hash() -> str:
    return sha256(_cjson(_POLICY_SPEC)).hexdigest()

def _payload_size(env: Dict[str, Any]) -> int:
    return len(_cjson(env.get("payload", {})))

class PolicyError(ValueError):
    pass

def validate_envelope(env: Dict[str, Any]) -> None:
    """Raise PolicyError if the envelope violates the rule book."""
    # 1) Signature & integrity
    if not verify_envelope(env):
        raise PolicyError("signature or payload_hash invalid, or lamport ≤ 0")

    # 2) Policy pin match
    if env.get("policy_engine_hash") != current_policy_hash():
        raise PolicyError("policy_engine_hash mismatch")

    # 3) Kind allowlist
    kind = env.get("kind")
    if kind not in ALLOWED_KINDS:
        raise PolicyError(f"kind not allowed: {kind}")

    # 4) Size limit
    if _payload_size(env) > MAX_PAYLOAD_BYTES:
        raise PolicyError(f"payload too large (> {MAX_PAYLOAD_BYTES} bytes)")

    # 5) Artifact rules
    p = env.get("payload", {})
    a_hash = p.get("artifact_hash")
    if kind == "COMMIT":
        if not a_hash:
            raise PolicyError("COMMIT requires payload.artifact_hash")
    if a_hash is not None and not has_blob(a_hash):
        raise PolicyError("artifact_hash not found in CAS")
