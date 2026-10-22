# PRD-3: Agent UI

Status: planned. Prerequisite: acceptance of [Phase 2](prd-2.md), including its
final tests/evals slice.

This document owns phase sequencing and capability-to-slice assignments.
[Capabilities](prd-3-capabilities.md) own behavior, user stories, acceptance
criteria, future-work boundaries, and unresolved product decisions.
See [the ADRs](adrs.md) for technical choices.

## Delivery plan

| Step | Slice | Capability scope |
| --- | --- | --- |
| 3.1 | `ui-spike-and-shell` | [P3-C01](prd-3-capabilities.md#p3-c01-browser-sign-in-with-organizational-identity), [P3-C06](prd-3-capabilities.md#p3-c06-supported-ui-integration-and-verified-azure-hosting) integration decision and shell |
| 3.2 | `ui-chat` | [P3-C02](prd-3-capabilities.md#p3-c02-streaming-research-chat), [P3-C03](prd-3-capabilities.md#p3-c03-visible-navigable-article-citations), [P3-C04](prd-3-capabilities.md#p3-c04-source-category-and-date-shortcuts), [P3-C05](prd-3-capabilities.md#p3-c05-inert-rendering-and-accessibility-basics) rendering |
| 3.3 | Phase tests | [P3-C05](prd-3-capabilities.md#p3-c05-inert-rendering-and-accessibility-basics) accessibility, [P3-C06](prd-3-capabilities.md#p3-c06-supported-ui-integration-and-verified-azure-hosting) deployed acceptance |

Use [the development guide](development.md#openspec) to execute each slice.
