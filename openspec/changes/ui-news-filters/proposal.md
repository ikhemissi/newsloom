# Proposal

## Why

The deployed news-first UI is useful, but readers cannot yet narrow browsing or
research by source, category and date. The user selected this bounded improvement
after current delivery closure, before a cached HTTP API and UI transport swap.

## What Changes

- Reconcile existing UI evidence and selectively publish its implementation and
  measured status with exact-source CI. The user approved proceeding with filters
  while unavailable automated Azure checks remain open in their original ledgers.
  Use the regular browser without exporting credentials or relabelling manual
  attestation as automated evidence; no full acceptance or archival is implied.
- Add source and category selectors populated from existing MCP `list_sources`.
- Add Any time, Today, Last 7 days, Last 30 days and custom calendar-date controls.
  Default remains unrestricted latest news; no hidden date cutoff.
- Apply draft filters explicitly. Metadata-only browsing uses query-less
  `search_news`; combined semantic search keeps the submitted query and filters.
  Editing controls alone dispatches no query or inference.
- Show active constraints in the agent panel and include their trusted metadata
  fields in explicit A2A research requests, alongside any selected current item.
  Freeze in-flight context and retain the existing independent scroll/lofi UX.
- Extend the typed NewsCatalog domain interface, not component-to-SDK coupling,
  so a later HTTP adapter can preserve the same filter behavior.
- During implementation, update the owning phase assignments/runbook and record
  the user-approved order: delivery closure, filters, cached API, UI API adapter,
  then evaluations. Details/pagination belong with the API contract.

## Capabilities

### New Capabilities

- `browser-news-filters`: Explicit source/category/date browsing and research
  constraints, with coherent visible state and precise calendar boundaries.

### Modified Capabilities

None. The delivered MCP metadata search, discovery and research filter contracts
already support these fields; no backend authorization or ranking change is needed.

## Impact

Owns PRD-3 P3-C04 and the filtering portion of P3-C07. Prerequisites are the
deployed UI/MCP/A2A paths and selective publication of their measured status;
unavailable Azure acceptance and PRD-2 evaluations remain pending and parked.

Affected implementation: `services/web` catalogue/domain/auth-neutral UI,
date/request validation, research request mapping and adjacent tests; owning
PRD-3/ADR/runbook documents and the existing immutable UI deployment. Reuse the
same MSAL session, MCP `news.read`, A2A `news.agent`, ACA environment and models.
No dependency, resource, role, registration, schema migration or new model is
planned. Explicit semantic queries use existing bounded embeddings; metadata-only
filtering must not incur inference.

The later API direction is confirmed but not implemented here: where practical,
co-host with MCP and reuse its delegated `news.read` authorization and workload
identity. Authenticate/authorize before every cache lookup, including hits; do
not cache credentials or conversations. Its owning slice must separately define
endpoint contracts, cache keys/freshness/invalidation and detail/cursor behavior.
The UI then swaps its NewsCatalog adapter to HTTP; agent interaction remains A2A.
Only after that migration does versioned evaluation work resume, preserving
existing receipts and costs.

Out of scope: HTTP API/cache code, new cache infrastructure, API adapter swap,
news-detail routes, pagination, multi-item selection, tag controls, saved history,
new research/generation pipeline, evaluation reruns and automatic deployment.
