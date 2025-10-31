import os, json, hashlib, tempfile, shutil
from pathlib import Path
from typing import Optional, Union

# Root folder for CAS (can override with env var)
CAS_ROOT = Path(os.getenv("SWARM_CAS_DIR", ".cas"))
CAS_ALGO = "sha256"

def _algo_dir() -> Path:
    p = CAS_ROOT / CAS_ALGO
    p.mkdir(parents=True, exist_ok=True)
    return p

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _object_path(h: str) -> Path:
    # Shard into dirs to avoid huge single directories
    base = _algo_dir()
    return base / h[0:2] / h[2:4] / h

def _ensure_parents(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

def has_blob(hash_hex: str) -> bool:
    return _object_path(hash_hex).exists()

def put_bytes(data: bytes) -> str:
    h = sha256_hex(data)
    path = _object_path(h)
    if path.exists():
        return h
    _ensure_parents(path)
    # Atomic write
    with tempfile.NamedTemporaryFile(delete=False, dir=str(path.parent)) as tmp:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    shutil.move(str(tmp_path), str(path))
    return h

def get_bytes(hash_hex: str) -> bytes:
    path = _object_path(hash_hex)
    with path.open("rb") as f:
        return f.read()

def put_json(obj: Union[dict, list]) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return put_bytes(data)

def get_json(hash_hex: str) -> Union[dict, list]:
    data = get_bytes(hash_hex)
    return json.loads(data.decode("utf-8"))
