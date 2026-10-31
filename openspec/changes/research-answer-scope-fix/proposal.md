# Proposal

## Why

The PRD-2 baseline's discovery request fails `research_coverage_invalid`.
Planning constrains trusted state in its schema, but synthesis leaves
application-owned coverage and missing IDs to unconstrained model copying.

## What Changes

- Bind final coverage and missing selected IDs from a typed trusted synthesis
  scope, following the existing planning-scope pattern.
- Preserve validated client receipts/usage and content-free failed-task
  categories so this invariant can be diagnosed without exposing output.
- Keep independent controller/render validation, evidence/citation guards,
  existing budgets and explicit failure; never repair a returned answer.
- Validate selected/discovery/no-match/missing-item behavior locally, then
  deploy only the existing agent image and verify one discovery case.
- Preserve the failed baseline and all diagnostic usage. This is a narrow
  correctness prerequisite to its continuation, not candidate optimization.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `news-research`: Extend evidence-bounded synthesis to bind application-owned
  coverage metadata independently of untrusted content.

## Impact

Owns a PRD-2 research correctness slice toward
[P2-C03/P2-C04](../../../docs/prd-2-capabilities.md).
Prerequisites are the delivered research runtime and the retained failed
[baseline](../agent-quality-baseline/tasks.md). Affects research contracts,
generator/controller interfaces and directly related tests/runbook.
No dependency, resource, model, capacity, grant, database write, web or PRD-3
change. Existing same-user access, region/model availability and USD 100
allowance remain in force; no new identity/cost decision is introduced.
The user approved agent-only deployment. Measured acceptance and exact-source
publication/CI remain separate from planning or local tests.
