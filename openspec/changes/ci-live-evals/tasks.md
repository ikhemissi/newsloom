# Tasks

## 1. Identity layer

- [ ] 1.1 Add `infra/eval-identity/` (default off): managed identity, `pull_request` and `main` federated credentials with validated immutable-ID subjects, chat-only custom role at the model account scope, outputs for client ID, model endpoint and deployment; register the layer in `azure.yaml`. Add Terraform tests for disabled (no resources) and enabled (exact resource set, no secrets) plans.
- [ ] 1.2 Document the layer, cost, rollback and emergency switch in `docs/development.md`; run `bash scripts/check.sh` and `npm run spec:check`.

## 2. Deploy and accept

- [ ] 2.1 Preview the layer through native azd, confirm only the declared additions, apply, and read back the identity, both subjects and the single role assignment.
- [ ] 2.2 Set `EVAL_CLIENT_ID`, `AZURE_TENANT_ID`, `EVAL_MODEL_ENDPOINT` and `EVAL_BRIEFING_DEPLOYMENT` repository variables from azd outputs; open the implementation PR as ready and verify the `evals` job runs live evals and passes on the PR and on `main`. Record measured duration and token usage/cost per run.
