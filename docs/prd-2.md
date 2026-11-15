# PRD-2: A2A research agent

Status (2026-11-15): Steps 2.1 and 2.2 are delivered and archived; Step 2.3 is
partly delivered. Prerequisite: [Phase 1](prd-1.md), complete.

| Step | Status | Evidence |
| --- | --- | --- |
| 2.1 Discoverable A2A agent, secretless on-behalf-of access | Delivered | [Archived change](../openspec/changes/archive/2026-10-27-agent-skeleton/tasks.md), [A2A serving](../openspec/specs/a2a-serving/spec.md), [delegation](../openspec/specs/delegated-mcp-access/spec.md) |
| 2.2 Cited research over stored news | Delivered | [Archived change](../openspec/changes/archive/2026-10-28-agent-research/proposal.md), [news research](../openspec/specs/news-research/spec.md), [agent runbook](agent.md#verified-research-delivery) |
| 2.3 Tests and evaluations | Partly delivered: evaluation foundation archived; live evals run in CI on every ready PR; the frozen deployed-agent baseline is pending | [Evaluation foundation](../openspec/specs/agent-evaluation/spec.md), [CI live evals](../openspec/specs/ci-live-evals/spec.md), [baseline change](../openspec/changes/agent-quality-baseline/tasks.md) |

Later agent work is owned by PRD-3 slices: research conversations and web
research through Web IQ (see [PRD-3](prd-3.md#delivery-plan)). The frozen
baseline suite predates them: web-backed answers end with a different evidence
line and `[Wn]` citations that its checks do not accept (found 2026-11-15).

This document owns phase sequencing and capability-to-slice assignments.
[Capabilities](prd-2-capabilities.md) own behavior, user stories, acceptance
criteria, and unresolved product decisions. See [the ADRs](adrs.md) for technical choices.

## Delivery plan

| Step | Slice | Capability scope |
| --- | --- | --- |
| 2.1 | `agent-skeleton` | [P2-C01](prd-2-capabilities.md#p2-c01-discoverable-streaming-a2a-access), [P2-C02](prd-2-capabilities.md#p2-c02-secretless-access-on-behalf-of-the-user) |
| 2.2 | `agent-research` | [P2-C03](prd-2-capabilities.md#p2-c03-multi-step-research-grounded-in-curated-news), [P2-C04](prd-2-capabilities.md#p2-c04-cited-answers-and-explicit-lack-of-evidence), [P2-C05](prd-2-capabilities.md#p2-c05-resistance-to-instructions-embedded-in-news) |
| 2.3 | Phase tests/evals | [P2-C06](prd-2-capabilities.md#p2-c06-repeatable-agent-quality-and-azure-acceptance) |

Use [the development guide](development.md#openspec) to execute each slice.

**Execution boundary:** pause for user review when all PRD-2 acceptance and
delivery-publication gates are verified. Do not begin PRD-3 or its browser UI
automatically; resuming beyond this phase requires explicit user approval.
Completing the synthetic evaluation foundation alone is not the end of PRD-2.

**Approved early-access exception (2026-10-31):** the user approved the minimal
[PRD-3 browser journey](prd-3.md) before Step 2.3 is complete. The
[`ui-spike-and-shell` change](../openspec/changes/archive/2026-11-04-ui-spike-and-shell/proposal.md)
owns this exception. Existing evaluation receipts, costs and unchecked acceptance
remain intact; this does not restart halted runs, complete P2-C06 or grant full
phase acceptance. Research stays visibly early access while quality acceptance
remains open.

## Deferred research TODOs

- [x] Optional web enrichment: delivered by the `web-research` change through
  Web IQ with the agent's managed identity, discovery questions only, with web
  citations kept separate from stored news (see the [agent runbook](agent.md)).
- [ ] Add persistent user preferences through a separately designed memory
  system; investigate Microsoft Work IQ as a possible source of user work
  context, not an assumed substitute for a preference/memory store. Verify its
  capabilities, licensing, consent, delegated authorization, retention and
  deletion semantics before choosing it. Step 2.2 uses only preferences supplied
  in the current request and claims no persistent memory or Microsoft 365 access.
