import base64, json, os, time, hashlib
from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError

def _get_env(name: str) -> bytes:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing env var: {name}")
    return base64.b64decode(val)

def load_signer() -> SigningKey:
    seed = _get_env("SWARM_SIGNING_SK_B64")  # 32 bytes
    return SigningKey(seed)

def load_verifier() -> VerifyKey:
    pk = _get_env("SWARM_VERIFY_PK_B64")
    return VerifyKey(pk)

def cjson(data: dict) -> bytes:
    """Canonical JSON bytes (sorted keys, no spaces)."""
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()

def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sign_record(record: dict) -> dict:
    """Return a new record with pk and sig attached."""
    sk = load_signer()
    vk = sk.verify_key
    body = cjson(record)
    sig = sk.sign(body).signature
    return {
        **record,
        "sig_pk_b64": base64.b64encode(bytes(vk)).decode(),
        "sig_b64": base64.b64encode(sig).decode(),
    }

def verify_record(signed: dict) -> bool:
    """Verify pk+sig over the canonical body (without sig fields)."""
    pk_b64 = signed.get("sig_pk_b64")
    sig_b64 = signed.get("sig_b64")
    if not pk_b64 or not sig_b64:
        return False
    body = {k: v for k, v in signed.items() if k not in ("sig_pk_b64","sig_b64")}
    try:
        VerifyKey(base64.b64decode(pk_b64)).verify(
            cjson(body),
            base64.b64decode(sig_b64),
        )
        return True
    except BadSignatureError:
        return False
