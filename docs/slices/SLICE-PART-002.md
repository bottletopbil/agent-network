# Slice Contract: SLICE-PART-002

## Metadata

- Slice ID: `SLICE-PART-002`
- Owner: `@rileyhicks`
- Status: `In Progress`
- Target Quality: `Stable PoC`
- Last Updated: `2026-02-18`

## Goal

Wire partition-heal detection into runtime so `RECONCILE` is emitted automatically when a partition heals.

## Scope

- `src/monitoring/partition_detector.py`
- `src/handlers/reconcile.py`
- Coordinator/runtime wiring that consumes partition events
- `tests/test_partition_handling.py`

## Non-Scope

- Full multi-region deployment automation.
- Consensus protocol redesign.

## Acceptance Criteria

- [x] Contract exists and matrix row is active.
- [x] Scope/non-scope are explicit.
- [ ] Runtime wiring emits `RECONCILE` on heal events.
- [ ] Failure mode (false positive partition) is bounded and logged.
- [ ] Partition-heal integration tests pass.
- [ ] Required CI gates remain green after integration.
- [ ] Supporting docs updated.

## Required Tests

- Happy path: partition heal triggers reconcile and state convergence.
- Failure path: malformed partition signal is ignored safely.
- Abuse path: fake partition events cannot force unsafe reconcile.
- Idempotency/retry path: repeated heal events stay safe.
- Recovery path: node restart preserves partition detector behavior.

## Risks

- Security risk: forged partition events could trigger unintended flows.
- Economic risk: stale state can cause incorrect payouts/decisions.
- Reliability risk: false-positive detector signals can create churn.

## Rollback Plan

Revert runtime auto-reconcile wiring and keep manual reconcile controls while detector logic is hardened.

## Evidence

- Existing detector and callback scaffolding present.
- Runtime integration pending.

## Open Issues

- Coordinator runtime integration.
- End-to-end partition-heal verification.
