# Proposal

## Why

Small changes took hours: every azd layer re-ran the full check suite, editorial
quality was only observable after deployment, every tweak needed a full OpenSpec
package, and changes stayed active indefinitely on checks that cannot run.

## What Changes

- Two delivery tracks: OpenSpec only for new capabilities, resources, identities,
  permissions, dependencies or data contracts; a lightweight commit-plus-runbook
  track for tuning, prompts, bug fixes, documentation and operational commands.
- Deployment hooks reuse a passing check result for an identical source
  fingerprint; CI still always runs the full suite.
- Checks that cannot run (for example signed-in regular-browser acceptance) are
  recorded in a [known-gaps register](../../../docs/known-gaps.md) and no longer
  keep a change active.
- Supporting tooling: local non-publishing briefing preview with record/replay
  and a golden replay test; reruns for the flaky evaluator suite.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `repository-foundation`: delivery contract gains the lightweight track,
  single check run per source and the known-gaps register.

## Impact

Process and tooling only: `scripts/check.sh`, `azure.yaml` hooks, `.gitignore`,
development docs, agent instructions, OpenSpec archive guidance. No runtime,
resource, identity, permission or data change. Out of scope: parked
agent-quality execution and editor auto-approval settings.
