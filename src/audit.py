import os, json, time
from pathlib import Path
from typing import Optional
from crypto import sign_record, sha256_hex

LOG_DIR = Path(os.getenv("SWARM_LOG_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)


def now_ns() -> int:
    return time.time_ns()


def write_jsonl(line: dict, logfile: Optional[str] = None) -> str:
    """Append a signed JSON object as one line."""
    if logfile is None:
        logfile = "swarm.jsonl"
    path = LOG_DIR / logfile
    signed = sign_record(line)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(signed, separators=(",", ":")) + "\n")
    return str(path)


def log_event(
    *,
    thread_id: str,
    subject: str,
    kind: str,
    payload: dict,
    logfile: Optional[str] = None
):
    """
    kind: e.g. 'BUS.PUBLISH', 'BUS.DELIVER'
    payload: arbitrary JSON-friendly dict (we also store its hash).
    """
    payload_hash = sha256_hex(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    )
    record = {
        "ts_ns": now_ns(),
        "thread_id": thread_id,
        "subject": subject,
        "kind": kind,
        "payload_hash": payload_hash,
        "payload": payload,  # small messages OK; for big blobs, store only hash
        "version": 1,
    }
    return write_jsonl(record, logfile=logfile)
