# CAN Swarm Completion Definition (Stable PoC)

This document defines when a shippable slice is considered complete.

## Scope and Target

- Completion unit: shippable slice.
- Quality target: Stable PoC.
- Process strictness: medium strict.
- Existing five quality gates remain mandatory.

## Definition of Complete

A slice is `Complete` only if all are true:

1. A slice contract exists from template.
2. Scope and non-scope are explicit.
3. At least 1 happy-path test and 1 failure-path test were added/updated.
4. At least 1 abuse/adversarial test was added/updated.
5. Existing 5 required CI gates pass on PR.
6. `CURRENT_STATE.md`, `ROADMAP.md`, and `REMEDIATION.md` are updated for that slice.
7. No open P0/P1 issue remains for that slice.
8. Rollback note exists in the PR description.

## Standard Status Values

- `Planned`
- `In Progress`
- `Candidate Complete`
- `Complete`
- `Regressed`

## Status Transition Policy

Allowed transitions:

- `Planned` -> `In Progress`, `Regressed`, `Planned`
- `In Progress` -> `Candidate Complete`, `Regressed`, `In Progress`
- `Candidate Complete` -> `Complete`, `In Progress`, `Regressed`, `Candidate Complete`
- `Complete` -> `Regressed`, `Complete`
- `Regressed` -> `In Progress`, `Regressed`

Disallowed transitions fail the Completion Contract Gate.

## PR Workflow Requirements

Each PR must include:

1. Slice ID.
2. Contract file path (`docs/slices/SLICE-*.md`).
3. Acceptance criteria checklist.
4. Test evidence checklist.
5. Risk + rollback note.
6. Docs update checklist.

Merge policy:

1. No direct merges to `main`.
2. No bypass of required checks.
3. Branch must be up to date before merge.

## Required Test Scenarios Per Slice

Every slice must include:

1. Happy path.
2. Failure path.
3. Abuse/adversarial path.
4. Idempotency/retry path.
5. Recovery path for stateful behavior.

## Weekly Confidence Audit Cadence

Run one confidence audit each week in a dedicated PR:

1. Re-run required gate commands.
2. Run slice-specific adversarial tests.
3. Confirm all skip markers are intentional and documented.
4. Move only fully evidenced slices to `Complete`.
5. Move broken slices to `Regressed` immediately.

Update these in the same PR:

- `docs/AUDIT_MATRIX.md`
- `docs/CURRENT_STATE.md`
- `ROADMAP.md`
- `REMEDIATION.md`
