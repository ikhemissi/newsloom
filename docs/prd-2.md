# PRD-2: A2A research agent

Status: planned. Prerequisite: acceptance of [Phase 1](prd-1.md), including its
final tests/evals slice.

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
