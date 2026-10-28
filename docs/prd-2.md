# PRD-2: A2A research agent

Status: Step 2.1 complete and verified, including local/Azure acceptance and
exact-SHA implementation/status CI. Step 2.2 runtime and implementation CI are
verified; its separate evidence/status CI remains open. Step 2.3 remains pending. Prerequisite:
acceptance of [Phase 1](prd-1.md), including its
final tests/evals slice.

Phase 1 is complete and its delivered contracts are archived. The
[`agent-skeleton` proposal](../openspec/changes/archive/2026-10-27-agent-skeleton/proposal.md)
defines Step 2.1 with actual secretless OBO as the first go/no-go gate.
Local protocol/delegation, isolated owning layers and full offline checks are
verified; see the [agent runbook](agent.md) and
[archived implementation checklist](../openspec/changes/archive/2026-10-27-agent-skeleton/tasks.md).
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
passed, followed by the separate
[evidence/status receipt CI](https://github.com/ikhemissi/newsloom/actions/runs/40501029431).
All 15 tasks are verified; only Step 2.1 is delivered. The change is archived,
with [A2A serving](../openspec/specs/a2a-serving/spec.md) and
[delegation](../openspec/specs/delegated-mcp-access/spec.md) published as delivered
contracts. Multi-step research, frozen phase-wide evaluations and
the Phase 3 browser UI remain future work.

Step 2.2 is being
[implemented separately](../openspec/changes/agent-research/proposal.md): deepen or
compare one or multiple stored MCP items and tailor the response to preferences
provided in the current request. Local implementation, the source-bound
agent-only deployment and all six focused signed-in cases are verified, including
semantic/citation checks, private telemetry, cancellation and preservation.
Implementation [exact-SHA CI](agent.md#verified-research-implementation-publication)
passed; the separate evidence/status receipt still needs its own CI before delivery
is checked. The [runbook](agent.md#state-constrained-planning-follow-up) retains
the failed planning attempts and the state-constrained follow-up.
Progress precedes a validated final answer; external web enrichment and
persistent personalization are explicitly deferred below.

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

## Deferred research TODOs

- [ ] Revisit optional web enrichment for user-requested deeper research on MCP
  news, starting with Foundry Toolbox/Web Search or a reviewed read-only provider.
  The 2026-10-27 read-only check found no usable project/toolbox in the retained
  environment: the AIServices account has project management disabled and zero
  Foundry projects; no project/toolbox endpoint is configured. The user chose to
  proceed without it for Step 2.2. The feature is
  [documented](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox),
  not disproven: a later owning change must review account/project prerequisites,
  secretless consumer identity/RBAC, region/client compatibility, costs, query
  privacy and web-search data/display terms before provisioning or inference.
  Distinguish external evidence/citations from stored MCP evidence. Do not send
  credentials, private preferences or full news bodies to external search.
- [ ] Add persistent user preferences through a separately designed memory
  system; investigate Microsoft Work IQ as a possible source of user work
  context, not an assumed substitute for a preference/memory store. Verify its
  capabilities, licensing, consent, delegated authorization, retention and
  deletion semantics before choosing it. Step 2.2 uses only preferences supplied
  in the current request and claims no persistent memory or Microsoft 365 access.
