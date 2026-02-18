# Slice Contract: SLICE-SEC-002

## Metadata

- Slice ID: `SLICE-SEC-002`
- Owner: `@rileyhicks`
- Status: `Regressed`
- Target Quality: `Stable PoC`
- Last Updated: `2026-02-18`

## Goal

Ensure all externally invocable handler paths enforce policy validation with no bypass route.

## Scope

- `src/handlers/`
- `src/bus.py`
- `src/policy/`
- `tests/test_remediation_policy_bypass.py`

## Non-Scope

- New policy language or policy engine migration.
- Economic and consensus logic changes outside ingress enforcement.

## Acceptance Criteria

- [x] Contract exists and is referenced in matrix.
- [x] Scope/non-scope are explicit.
- [ ] Handler inventory is complete and externally invocable entry points are enumerated.
- [ ] Policy enforcement decorator/guard is applied consistently.
- [ ] Bypass tests prove direct invocation cannot skip policy.
- [ ] Required gates pass with this enforcement enabled.
- [ ] Supporting docs updated with final result.

## Required Tests

- Happy path: valid envelopes pass policy checks.
- Failure path: invalid envelopes are rejected with explicit reason.
- Abuse path: direct handler invocation without policy context is blocked.
- Idempotency/retry path: repeated validation produces same decision.
- Recovery path: policy service fallback still enforces deny-by-default.

## Risks

- Security risk: bypass enables unauthorized state transitions.
- Economic risk: policy gaps can allow fraudulent operations.
- Reliability risk: broad handler refactor can introduce regressions.

## Rollback Plan

If enforcement rollout causes broad breakage, revert to last known safe commit and keep status `Regressed` until full handler coverage is restored.

## Evidence

- Remediation tracker item: `SEC-002` in `REMEDIATION.md`.
- Current finding: policy decorator coverage is partial.

## Open Issues

- Full externally invocable handler inventory.
- Uniform policy guard coverage.
- End-to-end policy bypass attack tests in required checks.
