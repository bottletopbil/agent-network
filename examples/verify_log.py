import json, sys, os
sys.path.append("src")  # so we can import crypto.py from src/
from crypto import verify_record

LOG_PATH = os.getenv("SWARM_LOG_PATH", "logs/swarm.jsonl")

def main():
    ok = bad = 0
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if verify_record(rec):
                    ok += 1
                else:
                    bad += 1
                    print(f"BAD SIG at line {i}")
    except FileNotFoundError:
        print(f"Log not found: {LOG_PATH}")
        return
    print(f"Verified {ok} records, {bad} bad")

if __name__ == "__main__":
    main()

