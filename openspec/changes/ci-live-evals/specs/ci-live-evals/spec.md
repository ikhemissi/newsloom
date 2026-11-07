# Spec Delta

## Purpose

Run live model evals in CI with a dedicated, secretless and least-privilege identity.

## ADDED Requirements

### Requirement: Dedicated secretless CI eval identity

The platform SHALL provide a default-off `eval-identity` layer that creates one
user-assigned managed identity federated only with this repository's
`pull_request` events and exact `main` ref, using immutable owner/repository ID
subjects. It SHALL grant only the chat-completions data action on the existing
model account and SHALL NOT create client secrets, keys or other role grants.

#### Scenario: Layer disabled

- **WHEN** the layer is provisioned with `enabled = false`
- **THEN** the plan creates no resources

#### Scenario: Layer enabled

- **WHEN** the layer is provisioned with `enabled = true`
- **THEN** the plan adds exactly one identity, two federated credentials, one
  custom role definition and one role assignment, and changes nothing else

#### Scenario: Other subjects are rejected

- **WHEN** a token from another repository, a fork, or a branch push other than
  `main` requests access
- **THEN** Entra token exchange fails because no federated credential matches

### Requirement: Live evals gate ready PRs and main

When the eval identity is configured, the CI `evals` job SHALL run replay and
live evals on every non-draft PR and every push to `main`, and a live eval
failure SHALL fail the required `evals` check. When it is not configured, CI
SHALL skip live evals with a visible notice.

#### Scenario: Ready PR

- **WHEN** a non-draft PR runs CI with the identity configured
- **THEN** the `evals` job signs in through OIDC, runs `scripts/eval.sh --live`
  and passes only if the live eval passes

#### Scenario: Draft PR

- **WHEN** a draft PR runs CI
- **THEN** no evals run and no model is called

#### Scenario: Model call denied or failing

- **WHEN** the live eval cannot call the model or its editorial assertions fail
- **THEN** the `evals` check fails and logs contain no prompts, completions,
  article text or tokens
