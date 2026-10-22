# Proposal

## Why

Newsloom needs a reproducible repository foundation before the first deployable
platform slice. Extract its planning input into focused documents rather than
retaining duplicate full specifications.

## What Changes

- Preserve phase PRDs, capabilities/user stories, ADRs, platform notes, and the
  ordered delivery workflow in focused documents.
- Add a Python 3.15 uv workspace, shared typed feed configuration, service package
  boundaries, and the complete initial 42-feed catalogue.
- Configure Ruff, strict mypy, pytest, pre-commit, pinned OpenSpec/Copilot integration,
  an identifier guard, and cloud-credential-free CI.
- Add native azd Terraform layers for the persistent RBAC-only state bootstrap
  and the subsequent application infrastructure, using one developer environment.

## Capabilities

### New Capabilities

- `repository-foundation`: reproducible tooling, typed catalogue, package boundaries,
  permanent requirements, offline checks, and secretless state-bootstrap configuration.

### Modified Capabilities

None. This is a repository with no prior commits or application code.

## Impact

Step 0 only. No live feed fetching, queue, scanner, model calls, database schema,
MCP runtime, agent, UI, application infrastructure, deployment, or commit is implied.
CI and Azure state verification are explicit remaining acceptance gates.
