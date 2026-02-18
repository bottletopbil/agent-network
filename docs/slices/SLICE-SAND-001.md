# Slice Contract: SLICE-SAND-001

## Metadata

- Slice ID: `SLICE-SAND-001`
- Owner: `@rileyhicks`
- Status: `Planned`
- Target Quality: `Stable PoC`
- Last Updated: `2026-02-18`

## Goal

Deliver a real Firecracker execution path with fail-closed behavior for untrusted workloads.

## Scope

- `src/sandbox/firecracker.py`
- Sandbox execution orchestration
- Isolation and fail-closed tests

## Non-Scope

- Full production autoscaling of microVM fleet.
- Long-term sandbox backend alternatives.

## Acceptance Criteria

- [x] Contract exists and matrix row is active.
- [x] Scope/non-scope are explicit.
- [ ] `_real_exec` implemented for Linux/KVM environment.
- [ ] Fail-closed behavior validated for unsupported environments.
- [ ] Isolation tests verify untrusted code does not execute in host process.
- [ ] Required CI gates remain green.
- [ ] Supporting docs updated.

## Required Tests

- Happy path: valid sandboxed task executes in microVM.
- Failure path: sandbox launch failure returns safe error.
- Abuse path: escape attempt is blocked.
- Idempotency/retry path: retried task does not leak resources.
- Recovery path: host restart recovers sandbox state safely.

## Risks

- Security risk: incomplete VM isolation can expose host.
- Economic risk: sandbox instability can fail paid tasks.
- Reliability risk: environment-specific dependencies (KVM, kernel config).

## Rollback Plan

Keep fail-closed behavior and disable real execution path if isolation guarantees regress.

## Evidence

- Current state: `_real_exec` is not implemented.
- Remediation tracking item: `SAND-001`.

## Open Issues

- Linux/KVM integration and test environment setup.
