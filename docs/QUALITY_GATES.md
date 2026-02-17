# Quality Gates (Must-Pass)

This is the minimum release safety system for this repository.

Rule: no merge if any gate below fails.

## Gate Matrix

| Gate | Purpose | Command |
|---|---|---|
| Core Flow | Protect core execution path/import drift | `python -m pytest -q tests/test_core.py tests/test_challenge_verifier_agent.py tests/test_hybrid_bus.py -p no:warnings` |
| Economics | Protect payout/slashing correctness and free-rider prevention | `python -m pytest -q tests/test_slashing_payout.py::TestPayoutDistribution::test_distribute_to_honest_verifiers tests/test_slashing_payout.py::TestHonestVerifierProofEnforcement::test_missing_attestation_log_rejected tests/test_slashing_payout.py::TestHonestVerifierProofEnforcement::test_forged_honest_verifier_claim_rejected -p no:warnings` |
| Security Abuse | Protect known exploit remediations | `python -m pytest -q tests/test_remediation_claim_extended_consensus.py tests/test_remediation_mint_authorization.py -p no:warnings` |
| Epoch/Partition | Protect epoch fencing baseline | `python -m pytest -q tests/test_epoch_fencing.py -p no:warnings` |
| Consensus (Raft) | Protect DECIDE atomicity/hardening | `python -m pytest -q tests/test_raft_consensus.py -p no:warnings` |

## CI Workflow

CI file: `.github/workflows/quality-gates.yml`

It runs on:
- pull requests
- pushes to `main`

Consensus gate uses `docker compose up -d etcd` and runs the raft test suite against live etcd.

## Local Run Checklist

1. Create/activate environment and install deps:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
   - `pip install -r requirements.txt`
2. Run all non-etcd gates:
   - core flow command
   - economics command
   - security abuse command
   - epoch/partition command
3. Start etcd and run consensus gate:
   - `docker compose up -d etcd`
   - raft command
   - `docker compose down`

## Operating Policy

- Do not add new feature work until all quality gates are green.
- Any new critical bug fix must include:
  - a failing test first (or explicit reproduction),
  - code fix,
  - gate green before merge.
- Keep this gate list small and stable. Add tests only when they are reliable.
