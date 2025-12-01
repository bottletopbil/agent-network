import os
import json
import threading
import time
from pathlib import Path
from typing import Optional

# Persist the clock so restarts don't go backwards (cheap & cheerful)
STATE_DIR = Path(os.getenv("SWARM_STATE_DIR", ".state"))
STATE_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_FILE = STATE_DIR / "lamport.json"
_LOCK = threading.Lock()

# Write batching configuration
BATCH_INTERVAL = 1.0  # Flush every 1 second
BATCH_SIZE = 100  # Or every 100 ticks


def _read(path: Path) -> int:
    if not path.exists():
        return 0
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

        # Write batching state
        self._dirty = False
        self._last_write_time = time.time()
        self._ticks_since_write = 0

    def tick(self) -> int:
        """
        Increment counter. Batches writes for performance.
        Actual persistence happens via background flush or manual flush().
        """
        with _LOCK:
            self.counter += 1
            self._dirty = True
            self._ticks_since_write += 1
            current_value = self.counter

            # Auto-flush if batch size reached
            if self._ticks_since_write >= BATCH_SIZE:
                self._flush_unsafe()
            # Auto-flush if time interval reached
            elif time.time() - self._last_write_time >= BATCH_INTERVAL:
                self._flush_unsafe()

            return current_value

    def observe(self, other: int) -> int:
        """
        Update counter based on observed value.
        ALWAYS writes immediately for correctness (not batched).
        """
        with _LOCK:
            self.counter = max(self.counter, other) + 1
            _write(self.path, self.counter)
            self._dirty = False
            self._last_write_time = time.time()
            self._ticks_since_write = 0
            return self.counter

    def flush(self) -> None:
        """
        Manually persist any pending writes.
        """
        with _LOCK:
            self._flush_unsafe()

    def _flush_unsafe(self) -> None:
        """
        Internal flush that assumes lock is already held.
        """
        if self._dirty:
            _write(self.path, self.counter)
            self._dirty = False
            self._last_write_time = time.time()
            self._ticks_since_write = 0

    def value(self) -> int:
        return self.counter
