# Design

## Context

`checks.yml` already has an `evals` job (non-draft PRs and `main`) with
`id-token: write`, an `azure/login` step and `scripts/eval.sh --live`, all
gated on `vars.EVAL_CLIENT_ID`. `tests/test_briefing_live_eval.py` uses
`AzureCliCredential`, `MODEL_ENDPOINT` and `BRIEFING_DEPLOYMENT`. The
`phase1-acceptance` and `briefing-identity` layers show the existing patterns
for GitHub federation (immutable-ID subjects) and an account-scoped custom
chat role.

## Goals / Non-Goals

**Goals:** smallest identity that lets the existing job run; no workflow
redesign; reversible by unsetting one variable.

**Non-Goals:** per-deployment isolation (not supported by the data-plane roles),
agent evals, budget enforcement in CI.

## Decisions

- **Separate layer `eval-identity`** rather than adding to `briefing-identity`:
  independent enable/rollback, and the workload identity stays untouched.
  Alternative: reuse the phase-1 identity; rejected because its subject is
  `main`-only and it carries AcrPull/telemetry grants CI does not need.
- **Two federated credentials** (`…:pull_request` and `…:ref:refs/heads/main`),
  validated in Terraform against the exact immutable-ID subjects, like
  `phase1-acceptance`. GitHub does not issue OIDC tokens to fork PRs by default.
- **Custom role with only `chat/completions/action`** at the model account
  scope, mirroring `briefing-identity`. No embeddings, no management actions.
- **Configuration through repository variables** set with `gh variable set` from
  azd outputs; identifiers stay out of committed files.
- **Live failure blocks merge.** Assertions check editorial rules, not wording,
  so nondeterminism is tolerated; a transient model failure is handled by
  re-running the job.

## Risks / Trade-offs

- [Identity can call chat on every deployment in the account] → only data
  action granted; documented; no other permissions.
- [Model outage or quota exhaustion blocks merges] → re-run the job; disable by
  deleting `EVAL_CLIENT_ID` as an emergency switch.
- [Cost creep with many PRs] → golden week is small; measured per run in
  acceptance and documented.
- [Shared quota with the daily briefing] → one call per run, outside the 05:00 UTC slot most of the time.

## Migration Plan

1. Add the layer (default off), preview disabled and enabled plans.
2. Enable and apply through native azd; read back the identity, credentials and grant.
3. Set the repository variables; open a ready PR and observe live evals pass.
4. Rollback: delete `EVAL_CLIENT_ID` (CI skips live evals), then disable the
   layer to destroy the identity and grant.

## Open Questions

None blocking.
