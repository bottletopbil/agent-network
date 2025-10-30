import os, json, threading
from pathlib import Path
from typing import Optional

# Persist the clock so restarts don't go backwards (cheap & cheerful)
STATE_DIR = Path(os.getenv("SWARM_STATE_DIR", ".state"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_FILE = STATE_DIR / "lamport.json"
_LOCK = threading.Lock()

def _read(path: Path) -> int:
    if not path.exists(): return 0
    try:
        return int(json.loads(path.read_text()).get("counter", 0))
    except Exception:
        return 0

def _write(path: Path, value: int) -> None:
    path.write_text(json.dumps({"counter": int(value)}))

class Lamport:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or DEFAULT_FILE
        self.counter = _read(self.path)

    def tick(self) -> int:
        with _LOCK:
            self.counter += 1
            _write(self.path, self.counter)
            return self.counter

    def observe(self, other: int) -> int:
        with _LOCK:
            self.counter = max(self.counter, other) + 1
            _write(self.path, self.counter)
            return self.counter

    def value(self) -> int:
        return self.counter
