# Proposal

## Why

Live briefing evals (`scripts/eval.sh --live`) only run when someone remembers to
run them locally with their own Azure sign-in. CI already has a guarded live-eval
step on ready PRs and `main`, but it is skipped because no CI identity exists. A
prompt or model regression can therefore merge with only replay evals passing.

## What Changes

- Add a default-off native azd layer `eval-identity`: one user-assigned managed
  identity, GitHub OIDC federated credentials for this repository's
  `pull_request` events and the exact `main` ref (immutable owner/repository ID
  subjects), and a custom role limited to the chat-completions data action on
  the existing model account.
- Set the GitHub repository variables the existing workflow reads
  (`EVAL_CLIENT_ID`, `AZURE_TENANT_ID`, `EVAL_MODEL_ENDPOINT`,
  `EVAL_BRIEFING_DEPLOYMENT`) from azd outputs; nothing is committed.
- The `evals` job then runs live evals on every ready PR and every push to
  `main`. A live failure fails the required `evals` check.
- Document cost, rollback and how to disable live evals.

Owning slice: repository delivery workflow (follow-up to the archived
lean delivery workflow). Prerequisites: existing model account and
`newsloom-briefing` deployment (delivered by `briefing-identity`).

Out of scope: agent/A2A live evals in CI, Foundry publication from CI, new model
deployments or capacity, secrets or client credentials, fork PRs.

Decisions surfaced:
- **Identity:** a new dedicated identity rather than reusing the phase-1
  acceptance identity, whose purpose and `main`-only subject differ.
- **Scope limit:** Azure OpenAI data-plane roles cannot be scoped to one
  deployment, so the identity can call chat on any deployment in the account.
- **Cost:** each run is one briefing generation on the small synthetic golden
  week, estimated at a few cents; with about two runs per PR (ready + `main`),
  expected under USD 1/month at the current PR rate. Measured in acceptance.
- **Capacity/region:** uses the existing France Central deployment and its quota;
  no new capacity.

## Capabilities

### New Capabilities

- `ci-live-evals`: CI runs live model evals on ready PRs and `main` using a
  dedicated, least-privilege, secretless GitHub OIDC identity.

### Modified Capabilities

None.

## Impact

- New `infra/eval-identity/` Terraform layer and its `azure.yaml` entry.
- GitHub repository variables (configuration, not code).
- `.github/workflows/checks.yml` unchanged except for any fix found in acceptance.
- `docs/development.md` (checks/evals) and the evals runbook section.
