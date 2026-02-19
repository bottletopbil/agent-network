# Slice Contract: SLICE-SEC-002

## Metadata

- Slice ID: `SLICE-SEC-002`
- Owner: `@rileyhicks`
- Status: `In Progress`
- Target Quality: `Stable PoC`
- Last Updated: `2026-02-18`

## Goal

Ensure all externally invocable ingress paths enforce policy validation with no bypass route into dispatcher/handler execution.

## Scope

- `src/policy/enforcement.py`
- `src/policy/gates.py`
- `src/coordinator.py`
- `src/bus.py`
- `src/hybrid_bus.py`
- `tests/test_remediation_policy_bypass.py`

## Non-Scope

- Rewriting every handler to mandatory decorator-based enforcement.
- Policy language/runtime migration work (`SEC-004`).
- Internal handler-to-handler call path redesign.

## Acceptance Criteria

- [x] Contract exists and is referenced in matrix.
- [x] Scope/non-scope are explicit.
- [x] Externally invocable ingress entry points are enumerated and guarded.
- [x] Shared ingress validation helper enforces fail-closed behavior.
- [x] Policy gate input normalization accepts canonical envelope fields (`kind`, `sender_pk_b64`) and legacy fields (`operation`, `agent_id`).
- [ ] Bypass remediation tests run without skip and cover happy/failure/abuse/retry/recovery scenarios.
- [ ] Required quality gates pass with ingress enforcement enabled.
- [ ] Supporting docs updated with final completion evidence.

## Required Tests

- Happy path: valid ingress envelope reaches dispatch exactly once.
- Failure path: invalid signature/policy hash rejected before dispatch.
- Abuse path: crafted invalid external envelope never reaches handler logic.
- Idempotency/retry path: repeated malicious envelope remains denied and does not mutate state.
- Recovery path: gate/enforcement error denies by default and processing recovers when gate is healthy.

## Risks

- Security risk: any unguarded ingress path still permits bypass.
- Economic risk: unauthorized operations can affect stake/payout state.
- Reliability risk: fail-closed rollout could block valid traffic if normalization is incomplete.

## Rollback Plan

Revert ingress validation wiring in coordinator/bus/hybrid and keep status `Regressed` until coverage is restored.

## Evidence

- Remediation tracker item: `SEC-002` in `REMEDIATION.md`.
- Matrix state: `Regressed -> In Progress` in `docs/AUDIT_MATRIX.md`.
- Test file unskipped: `tests/test_remediation_policy_bypass.py`.

## Open Issues

- Capture full gate run evidence for completion transition.
- Validate no additional external ingress surfaces remain uncovered.
