# Proposal

## Why

The delivered research agent has focused acceptance evidence, but no reproducible
DeepEval-to-Foundry evaluation path. Before investing in a phase-wide quality
baseline, prove Python compatibility, secretless judging, honest cost accounting
and actual Foundry evaluation-report visibility.

## What Changes

- Deliver the first bounded part of [Step 2.3](../../../docs/prd-2.md#delivery-plan),
  preparing for [P2-C06](../../../docs/prd-2-capabilities.md#p2-c06-repeatable-agent-quality-and-azure-acceptance)
  without declaring that capability or Phase 2 complete.
- Add an operator-invoked evaluation pilot using two authored, precomputed
  question/evidence/answer cases: one supported answer and one deliberately
  unsupported answer. No production content or agent generation is needed.
- Prove DeepEval and the current Foundry evaluation SDK on supported Python
  3.15 in a separate, non-packaged evaluation-only uv project with its own lock
  and environment. Preserve the application lock and production dependency
  closures; keep evaluation libraries outside production installations.
- Score the cases with one explicitly configured DeepEval faithfulness metric
  using an existing Azure chat deployment and Entra authentication.
- Publish validated, explicitly labelled imported DeepEval scores through a
  Foundry custom code evaluator; verify case-level scores and lineage through
  both API readback and the actual Evaluations report. This adapter is a
  feasibility gate, not an already demonstrated integration.
- Bound all inference attempts, polling, retention and estimated spending;
  preserve missing usage, failures and ambiguous publication outcomes.
- Inspect the retained environment and provision only a separately reviewed,
  minimally scoped Foundry evaluation foundation through an owning azd layer.
  Reuse the existing model account, adding project management and its required
  account identity in place; keep production workload identities, models,
  application behavior and data unchanged.

Prerequisites are the delivered Phase 1 and Steps 2.1-2.2, followed by review and
synchronization/archival of the completed `agent-research` change before this
slice is applied. Existing verified acceptance is referenced, not rerun merely
for archival.

Out of scope: the frozen phase-wide question set, calibrated quality thresholds,
native LLM-judge comparisons, deployed-agent quality acceptance, automated paid
CI, scheduled canaries, production traffic sampling, prompt/completion capture,
automatic optimization/deployment, new model deployments/capacity, web, memory,
UI work and a move to Foundry-hosted agents. These remain subsequent slices.

## Capabilities

### New Capabilities

- `agent-evaluation`: Reproducible, bounded agent-quality evaluation execution
  and Foundry-visible results, initially limited to a synthetic interoperability
  pilot with explicit provenance and preservation guarantees.

### Modified Capabilities

None. Existing telemetry, delegated access, runtime and Phase 1 acceptance
requirements remain unchanged.

## Impact

- A separately locked evaluation-only project, authored fixtures and focused
  tests; an explicit application-workspace exclusion without application-lock
  changes; cross-environment isolation checks and existing unpaid local/CI gates.
- A new evaluation-owned Terraform/azd boundary and existing platform preparation
  helpers only where needed for reviewed project configuration and outputs.
- A future evaluation runbook plus owning PRD/ADR links and measured receipts.
  Planning creates only this change's artifacts, not implementation or delivery
  status updates.
- The last verified account had project management disabled and no Foundry
  project. The pinned provider supports projects on that account. The user
  selected reuse after being informed that disabling project management or
  removing the required account identity later would require replacement:
  those settings must remain enabled, and replacement is prohibited. Exact
  project identity/RBAC, regional operation, deployment reuse and data lifecycle
  still require the design's specific preflight. A new account/model requires
  a separate scope decision.
- Exact provisioning/grant changes and a finite pilot spending envelope require
  explicit approval before execution. Step 2.2's paid authorization is not
  inherited; no resource, role, inference, compatibility or result-visibility
  success is claimed by this proposal.
