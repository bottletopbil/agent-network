# Slice Contract: SLICE-ECON-006

## Metadata

- Slice ID: `SLICE-ECON-006`
- Owner: `@rileyhicks`
- Status: `Complete`
- Target Quality: `Stable PoC`
- Last Updated: `2026-02-18`

## Goal

Close the free-rider payout exploit by enforcing attestation-backed honest verifier rewards.

## Scope

- `src/economics/slashing.py`
- `tests/test_slashing_payout.py`
- `tests/test_remediation_honest_proof.py`

## Non-Scope

- Verifier stake-weight fairness model redesign (`ECON-006` selection bias item).
- New tokenomics policy.

## Acceptance Criteria

- [x] Contract exists and is referenced in matrix.
- [x] Scope/non-scope are explicit.
- [x] Happy/failure tests updated.
- [x] Abuse-path test updated.
- [x] Required quality gates pass in CI.
- [x] Supporting roadmap/remediation docs updated.
- [x] No open P0/P1 exploit remains for this specific payout proof bypass.
- [x] Rollback note documented.

## Required Tests

- Happy path: verified honest verifiers receive payout.
- Failure path: missing attestation log is rejected.
- Abuse path: forged honest verifier claims are rejected.
- Idempotency/retry path: repeated distribution with same validated inputs is stable.
- Recovery path: N/A for this deterministic payout function.

## Risks

- Security risk: false positives if attestation data source is malformed.
- Economic risk: honest verifiers could be underpaid if attestation logging fails upstream.
- Reliability risk: low; payout logic is deterministic and covered by tests.

## Rollback Plan

Revert payout enforcement changes and lock release until exploit and tests are revalidated.

## Evidence

- CI run: `22126319283`
- Commits: `a5a3f25`, `147cd39`
- Tests: `tests/test_slashing_payout.py::TestPayoutDistribution::test_distribute_to_honest_verifiers`,
  `tests/test_slashing_payout.py::TestHonestVerifierProofEnforcement::test_missing_attestation_log_rejected`,
  `tests/test_slashing_payout.py::TestHonestVerifierProofEnforcement::test_forged_honest_verifier_claim_rejected`

## Open Issues

- None for payout-proof bypass path.
