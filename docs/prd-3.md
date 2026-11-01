# PRD-3: Agent UI

Status: early-access implementation approved; deployment and acceptance pending.
Full phase acceptance still requires [Phase 2](prd-2.md), including its final
tests/evals slice. On 2026-10-31 the user explicitly approved a narrow sequencing
exception: deliver the minimal signed-in research/citation journey using the
verified Phase 2 backend while its remaining evaluation acceptance stays open.
The [`ui-spike-and-shell` change](../openspec/changes/ui-spike-and-shell/proposal.md)
owns this first delivery, not a declaration that either phase is complete.

This document owns phase sequencing and capability-to-slice assignments.
[Capabilities](prd-3-capabilities.md) own behavior, user stories, acceptance
criteria, future-work boundaries, and unresolved product decisions.
See [the ADRs](adrs.md) for technical choices.

## Delivery plan

| Step | Slice | Capability scope |
| --- | --- | --- |
| 3.1 | `ui-spike-and-shell` | [P3-C01](prd-3-capabilities.md#p3-c01-browser-sign-in-with-organizational-identity), [P3-C06](prd-3-capabilities.md#p3-c06-supported-ui-integration-and-verified-azure-hosting), and minimal [P3-C02](prd-3-capabilities.md#p3-c02-streaming-research-chat)/[P3-C03](prd-3-capabilities.md#p3-c03-visible-navigable-article-citations)/[P3-C05](prd-3-capabilities.md#p3-c05-inert-rendering-and-accessibility-basics): sign in, ask, progress, validated answer, citations; not an empty shell |
| 3.2 | `ui-news-feed` | [P3-C07](prd-3-capabilities.md#p3-c07-news-feed-search-and-item-context): latest-news landing, top MCP search and closable right-hand A2A panel with current-news context; remaining [P3-C02](prd-3-capabilities.md#p3-c02-streaming-research-chat)/[P3-C03](prd-3-capabilities.md#p3-c03-visible-navigable-article-citations)/[P3-C05](prd-3-capabilities.md#p3-c05-inert-rendering-and-accessibility-basics) context/rendering |
| 3.3 | Phase tests | [P3-C05](prd-3-capabilities.md#p3-c05-inert-rendering-and-accessibility-basics) accessibility, [P3-C06](prd-3-capabilities.md#p3-c06-supported-ui-integration-and-verified-azure-hosting) deployed acceptance |

Use [the development guide](development.md#openspec) to execute each slice.

The user approved local feed implementation while the first UI's remaining
release evidence/publication stays open. The
[feed checklist](../openspec/changes/ui-news-feed/tasks.md) retains that release
prerequisite. Filters (P3-C04), item-detail routing, multi-selection and pagination
remain subsequent slices; this delivery does not claim the whole phase complete.
