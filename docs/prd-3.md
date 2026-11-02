# PRD-3: Agent UI

Status: signed-in news/search/context UI deployed as early access; full automated
Azure and phase acceptance remain pending. Source/category/date filters are
deployed early access in their active slice, with signed-in acceptance still open.
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
| 3.3 | `ui-news-filters` | [P3-C04](prd-3-capabilities.md#p3-c04-source-category-and-date-shortcuts), filtering in [P3-C07](prd-3-capabilities.md#p3-c07-news-feed-search-and-item-context): explicit source/category/local-calendar browsing and structured A2A constraints |
| 3.4 | `cached-news-api` (deployed early access) | Same MCP app, delegated `news.read` and workload identity; authorize before every cache lookup/hit; 60-second bounded process-local cache, detail and browse-only cursor contracts; authenticated live API/cache acceptance open in the [API runbook](news-api.md) |
| 3.5 | `ui-http-news-catalog` (deployed early access) | HTTP-only NewsCatalog, shareable stored-item pages, explicit 20-item Load more capped at 200 displayed items; retain A2A interactions and MCP agent tools; signed-in acceptance remains open |
| 3.6 | Phase tests and versioned evaluations | [P3-C05](prd-3-capabilities.md#p3-c05-inert-rendering-and-accessibility-basics)/[P3-C06](prd-3-capabilities.md#p3-c06-supported-ui-integration-and-verified-azure-hosting) deployed acceptance; return to the parked [Phase 2 evaluations](prd-2.md) after the API/UI migration |

Use [the development guide](development.md#openspec) to execute each slice.

The user approved local feed implementation while the first UI's remaining
release evidence/publication stays open. The
[feed checklist](../openspec/changes/ui-news-feed/tasks.md) retains that release
prerequisite. Filters (P3-C04), item-detail routing, multi-selection and pagination
remain subsequent slices; this delivery does not claim the whole phase complete.

On 2026-11-01 the user approved selective publication followed by filters while
unavailable automated regular-browser Azure checks stay open in their original
ledgers. This is an early-access sequencing exception, not a change to full phase
acceptance. Details/pagination belong with the API contract; no API/cache/HTTP
adapter or new evaluation run is implemented by the filters slice.
