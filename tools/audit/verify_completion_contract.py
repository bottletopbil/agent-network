#!/usr/bin/env python3
"""
Verify completion-contract requirements for pull requests.

Fails if:
1) src/ changes happen without tests/ changes.
2) src/ changes happen without docs state updates.
3) No slice contract file is referenced in PR body.
4) AUDIT_MATRIX status transitions are invalid.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Set


VALID_STATUSES = {
    "Planned",
    "In Progress",
    "Candidate Complete",
    "Complete",
    "Regressed",
}

ALLOWED_TRANSITIONS = {
    "Planned": {"Planned", "In Progress", "Regressed"},
    "In Progress": {"In Progress", "Candidate Complete", "Regressed"},
    "Candidate Complete": {"Candidate Complete", "Complete", "In Progress", "Regressed"},
    "Complete": {"Complete", "Regressed"},
    "Regressed": {"Regressed", "In Progress"},
}

REQUIRED_DOC_UPDATES = (
    "docs/CURRENT_STATE.md",
    "ROADMAP.md",
    "REMEDIATION.md",
)

AUDIT_MATRIX_PATH = "docs/AUDIT_MATRIX.md"
CONTRACT_PATTERN = re.compile(r"\bdocs/slices/SLICE-[A-Z0-9-]+\.md\b")


def run_git(args: Sequence[str], check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def load_event_payload() -> Dict:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return {}
    path = Path(event_path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def compute_diff_range(event_name: str, payload: Dict) -> str:
    if event_name == "pull_request":
        pr = payload.get("pull_request", {})
        base_sha = pr.get("base", {}).get("sha")
        head_sha = pr.get("head", {}).get("sha")
        if base_sha and head_sha:
            return f"{base_sha}...{head_sha}"

    if event_name == "push":
        before = payload.get("before")
        after = payload.get("after")
        if before and after and set(before) != {"0"}:
            return f"{before}..{after}"

    # Local fallback.
    return "HEAD~1..HEAD"


def get_changed_files(diff_range: str) -> Set[str]:
    output = run_git(["diff", "--name-only", diff_range], check=False)
    changed = {line.strip() for line in output.splitlines() if line.strip()}
    if changed:
        return changed

    # Fallback only for local/manual mode where HEAD~1..HEAD may not be available.
    if diff_range != "HEAD~1..HEAD":
        return set()

    output = run_git(["status", "--porcelain"], check=False)
    derived = set()
    for line in output.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if path:
            derived.add(path)
    return derived


def clean_table_cell(value: str) -> str:
    cleaned = value.strip().strip("`")
    if cleaned.startswith("[") and "](" in cleaned and cleaned.endswith(")"):
        cleaned = cleaned[1 : cleaned.index("](")]
    return cleaned.strip()


def parse_audit_matrix(content: str) -> Dict[str, str]:
    lines = content.splitlines()
    header_idx = -1
    for i, line in enumerate(lines):
        if "Slice ID" in line and "Status" in line and line.strip().startswith("|"):
            header_idx = i
            break

    if header_idx < 0 or header_idx + 2 > len(lines):
        return {}

    headers = [clean_table_cell(col) for col in lines[header_idx].strip().strip("|").split("|")]
    if "Slice ID" not in headers or "Status" not in headers:
        return {}

    slice_idx = headers.index("Slice ID")
    status_idx = headers.index("Status")
    status_map: Dict[str, str] = {}

    for row in lines[header_idx + 2 :]:
        if not row.strip().startswith("|"):
            break
        cols = [clean_table_cell(col) for col in row.strip().strip("|").split("|")]
        if len(cols) != len(headers):
            continue
        slice_id = cols[slice_idx]
        status = cols[status_idx]
        if slice_id:
            status_map[slice_id] = status

    return status_map


def read_file_at_ref(ref: str, path: str) -> str:
    proc = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def validate_pr_contract_reference(event_name: str, payload: Dict) -> List[str]:
    if event_name != "pull_request":
        return []

    body = payload.get("pull_request", {}).get("body") or ""
    matches = sorted(set(CONTRACT_PATTERN.findall(body)))
    if not matches:
        return [
            "PR body must reference at least one slice contract file path like "
            "`docs/slices/SLICE-XXXX.md`."
        ]

    errors: List[str] = []
    for match in matches:
        if not Path(match).exists():
            errors.append(f"Referenced slice contract does not exist in this branch: `{match}`.")
    return errors


def validate_matrix_transitions(base_ref: str) -> List[str]:
    current_path = Path(AUDIT_MATRIX_PATH)
    if not current_path.exists():
        return [f"Missing required matrix file: `{AUDIT_MATRIX_PATH}`."]

    current_content = current_path.read_text(encoding="utf-8")
    current_status = parse_audit_matrix(current_content)
    errors: List[str] = []

    for slice_id, status in current_status.items():
        if status not in VALID_STATUSES:
            errors.append(
                f"Invalid status `{status}` for `{slice_id}` in `{AUDIT_MATRIX_PATH}`. "
                f"Allowed: {sorted(VALID_STATUSES)}."
            )

    if not base_ref:
        return errors

    previous_content = read_file_at_ref(base_ref, AUDIT_MATRIX_PATH)
    if not previous_content:
        return errors

    previous_status = parse_audit_matrix(previous_content)
    for slice_id, old_status in previous_status.items():
        if slice_id not in current_status:
            continue
        new_status = current_status[slice_id]
        if old_status == new_status:
            continue
        allowed = ALLOWED_TRANSITIONS.get(old_status, set())
        if new_status not in allowed:
            errors.append(
                f"Invalid status transition for `{slice_id}`: `{old_status}` -> `{new_status}`. "
                f"Allowed next states: {sorted(allowed)}."
            )

    return errors


def main() -> int:
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    payload = load_event_payload()
    diff_range = compute_diff_range(event_name, payload)
    changed = get_changed_files(diff_range)

    errors: List[str] = []
    src_changed = any(path.startswith("src/") for path in changed)
    tests_changed = any(path.startswith("tests/") for path in changed)

    if src_changed and not tests_changed:
        errors.append("Changes under `src/` require at least one changed file under `tests/`.")

    if src_changed:
        missing_docs = [path for path in REQUIRED_DOC_UPDATES if path not in changed]
        if missing_docs:
            errors.append(
                "Changes under `src/` require updates to all state docs. Missing: "
                + ", ".join(f"`{path}`" for path in missing_docs)
            )

    errors.extend(validate_pr_contract_reference(event_name, payload))

    base_ref = ""
    if event_name == "pull_request":
        base_ref = payload.get("pull_request", {}).get("base", {}).get("sha", "")
    elif event_name == "push":
        base_ref = payload.get("before", "")

    if AUDIT_MATRIX_PATH in changed:
        errors.extend(validate_matrix_transitions(base_ref))
    else:
        # Always validate status vocabulary, even when matrix didn't change.
        errors.extend(validate_matrix_transitions(""))

    if errors:
        print("Completion Contract Gate failed:")
        for idx, err in enumerate(errors, start=1):
            print(f"{idx}. {err}")
        return 1

    print("Completion Contract Gate passed.")
    print(f"Diff range: {diff_range}")
    print(f"Changed files detected: {len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
