# PRD-2: A2A research agent

Status: Step 2.1 local/Azure runtime acceptance and implementation CI verified;
final evidence/status receipt CI pending. Prerequisite:
acceptance of [Phase 1](prd-1.md), including its
final tests/evals slice.

Phase 1 is complete and its delivered contracts are archived. The
[`agent-skeleton` proposal](../openspec/changes/agent-skeleton/proposal.md)
defines Step 2.1 with actual secretless OBO as the first go/no-go gate.
Local protocol/delegation, isolated owning layers and full offline checks are
verified; see the [agent runbook](agent.md) and
[implementation checklist](../openspec/changes/agent-skeleton/tasks.md).
After separately approved owning previews, consent and cost, the non-generative
agent app is deployed with verified identity/image/configuration and public
authorization guards. Actual signed-in OBO, a user-preserving MCP read and the
required live workload denials passed. The first delegation gate is complete;
model-backed streaming and final telemetry are implemented and verified locally.
The separately approved model-stage image is deployed with independent
configuration/readiness verification and unchanged existing workloads/models.
Actual signed-in Foundry streaming, completed/cancelled task parity, authenticated
content-free telemetry ingestion and final denial/preservation checks passed.
Implementation publication and its
[exact-SHA CI](https://github.com/ikhemissi/newsloom/actions/runs/40500304977)
passed: 14/15 tasks complete. The separate final evidence/status receipt and its
CI remain pending; Step 2.1 is not yet declared delivered.

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
