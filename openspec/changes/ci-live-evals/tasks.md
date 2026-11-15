# Tasks

## 1. Identity layer

- [x] 1.1 Add `infra/eval-identity/` (default off): managed identity, `pull_request` and `main` federated credentials with validated immutable-ID subjects, chat-only custom role at the model account scope, outputs for client ID, model endpoint and deployment; register the layer in `azure.yaml`. Add Terraform tests for disabled (no resources) and enabled (exact resource set, no secrets) plans.
- [x] 1.2 Document the layer, cost, rollback and emergency switch in `docs/development.md`; run `bash scripts/check.sh` and `npm run spec:check`.

## 2. Deploy and accept

- [x] 2.1 Preview the layer through native azd, confirm only the declared additions, apply, and read back the identity, both subjects and the single role assignment.
  - Evidence (2026-11-15): the first apply was interrupted before anything was created (the identity did not exist). The re-run preview showed exactly 5 additions and no changes; the apply added 5 resources. Read back: `id-newsloom-dev-ci-eval` exists with federated subjects `…:pull_request` and `…:ref:refs/heads/main`, and its only role assignment is the custom chat-completions role on the model account.
- [ ] 2.2 Set `EVAL_CLIENT_ID`, `AZURE_TENANT_ID`, `EVAL_MODEL_ENDPOINT` and `EVAL_BRIEFING_DEPLOYMENT` repository variables from azd outputs; open the implementation PR as ready and verify the `evals` job runs live evals and passes on the PR and on `main`. Record measured duration and token usage/cost per run.
  - Evidence (2026-11-15): variables set from azd outputs (`AZURE_TENANT_ID` already existed). PR #11 `evals` job: Azure sign-in as the eval identity succeeded and `scripts/eval.sh --live` passed (1 live test, 186 s; job 3 min 25 s). Usage on `newsloom-briefing` in that window, which no scheduled job used: 5 requests, 4,812 prompt and 2,307 generated tokens, about $0.015 at DataZoneStandard gpt-5.4-mini list prices. Run on `main` pending until merge.
