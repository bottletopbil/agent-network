# CAN Swarm Audit Matrix

This is the source of truth for slice status and completion evidence.

## Required Columns

- `Slice ID`
- `Goal`
- `Files in Scope`
- `Required Tests`
- `Security/Economic Risks`
- `Status`
- `Evidence (CI run + test paths + commit)`
- `Owner`
- `Complexity (S/M/L)`
- `Blocked By`

## Slice Matrix

| Slice ID | Goal | Files in Scope | Required Tests | Security/Economic Risks | Status | Evidence (CI run + test paths + commit) | Owner | Complexity (S/M/L) | Blocked By |
|---|---|---|---|---|---|---|---|---|---|
| `SLICE-ECON-006` | Close free-rider exploit path in slashing and enforce proof-backed honest verifier payouts. | `src/economics/slashing.py`, `tests/test_slashing_payout.py`, `tests/test_remediation_honest_proof.py`, `docs/slices/SLICE-ECON-006.md` | `tests/test_slashing_payout.py::TestHonestVerifierProofEnforcement::*`, `tests/test_slashing_payout.py::TestPayoutDistribution::test_distribute_to_honest_verifiers` | Fake honest verifiers siphon rewards. | `Complete` | CI run `22126319283`; tests `tests/test_slashing_payout.py`; commit `147cd39` | `@rileyhicks` | `M` | `None` |
| `SLICE-SEC-002` | Remove policy bypass paths for externally invocable handlers. | `src/handlers/`, `src/bus.py`, `src/policy/`, `tests/test_remediation_policy_bypass.py`, `docs/slices/SLICE-SEC-002.md` | `tests/test_remediation_policy_bypass.py`, targeted handler ingress tests | Direct handler invocation can bypass policy validation. | `Regressed` | Open remediation item `SEC-002` in `REMEDIATION.md`; policy decorator coverage incomplete | `@rileyhicks` | `L` | Handler inventory and enforcement rollout not complete |
| `SLICE-PART-002` | Wire partition-heal detection to automatic `RECONCILE` emission in runtime path. | `src/monitoring/partition_detector.py`, `src/handlers/reconcile.py`, coordinator runtime wiring, `tests/test_partition_handling.py`, `docs/slices/SLICE-PART-002.md` | Partition detection tests, reconcile trigger tests, heal/recovery flow tests | Divergent state persists after partition heal. | `In Progress` | Baseline detector/hooks exist; runtime wiring still pending; see `REMEDIATION.md` `PART-002` | `@rileyhicks` | `L` | Runtime integration and end-to-end partition-heal tests |
| `SLICE-SAND-001` | Implement and validate real Firecracker execution path with fail-closed guardrails. | `src/sandbox/firecracker.py`, sandbox orchestration code, security tests, `docs/slices/SLICE-SAND-001.md` | Firecracker integration tests, fail-closed tests, isolation tests | Untrusted code may execute without true VM isolation. | `Planned` | `_real_exec` still `NotImplementedError`; tracked in `REMEDIATION.md` `SAND-001` | `@rileyhicks` | `L` | Linux/KVM environment setup and production execution path |

## Status Transition Reference

Allowed transitions:

- `Planned` -> `In Progress`, `Regressed`, `Planned`
- `In Progress` -> `Candidate Complete`, `Regressed`, `In Progress`
- `Candidate Complete` -> `Complete`, `In Progress`, `Regressed`, `Candidate Complete`
- `Complete` -> `Regressed`, `Complete`
- `Regressed` -> `In Progress`, `Regressed`
