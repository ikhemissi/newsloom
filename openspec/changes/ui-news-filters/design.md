# Design

## Context

See [proposal](proposal.md) for motivation and confirmed sequence.
The current deployed UI has latest news, submitted MCP search, selected-item
A2A research, independently scrollable agent interactions and default lofi.
Its remaining release evidence and selective CI/publication obligations are open.

Observed integration surfaces:

- `NewsCatalog` currently exposes recent and semantic search, hiding SDK types
  from components. `McpCatalog` pins modern MCP and has a bounded per-load client.
- `list_sources` returns represented source IDs with category IDs, plus category
  IDs/labels. Source display names are not a returned field.
- MCP `search_news` supports optional query plus exact source/category and
  timezone-aware from/to constraints. Query-less requests rank by publication
  without inference; semantic requests rank only eligible rows without a cutoff.
- Agent ResearchRequest already accepts the same filter fields separately from
  its question and item IDs. No server contract extension is required.

## Goals / Non-Goals

**Goals:** Reuse existing contracts for explicit filtering and consistent visible
research context; keep a transport-neutral interface for the later API adapter.

**Non-Goals:** No caching implementation, HTTP endpoints, new model/permission,
tag controls, details/cursors, account/history store or replacement research path.

## Decisions

### 1. Explicit draft and applied state

Use a compact labelled filter bar below the top search form: source, category,
date preset, optional custom dates, Apply and Reset.
Keep draft controls separate from a validated applied snapshot. Editing dispatches
nothing. Apply uses draft filters with the last submitted query, not unsent search
text. Search commits its draft text and draft filters together. Reset clears
metadata restrictions while preserving the submitted query; Clear search removes
the query while preserving applied metadata filters.

Empty query with no filters keeps the latest-news path. Any metadata filter uses
query-less `search_news({source?,category?,from?,to?,limit:20})`. A submitted
semantic query uses the same fields plus query. Preserve backend ordering and
the existing stale-response, cancellation, empty/error and no-replay behavior.
Labels/chips describe only the applied snapshot, not draft changes.

### 2. Catalogue via the existing domain seam

Extend the typed domain with `NewsFilters` and source/category catalogue results.
Extend NewsCatalog with catalogue discovery and a query accepting an optional
semantic query plus filters. Only its MCP adapter imports SDK types.

Call `list_sources` once for the signed-in view, validate its structured result
with Zod, and cancel/discard it on sign-out or view replacement. Display actual
source IDs and provided category labels; do not invent publisher display names
or import the full feed configuration into the browser for this slice.
Keep category choices from the returned catalogue. Valid source/category pairs
with no matches remain explicit empty results, not automatic filter broadening.

Catalogue failure disables unavailable choices with visible retry. It does not
silently reset already applied constraints or claim fabricated options.
Do not add a general cache, polling or new query library.

### 3. Calendar dates and exact wire mapping

Default is Any time, omitting both bounds. Today begins at local midnight;
Last 7 days begins six calendar days before today, and Last 30 begins 29 days
before today. Each ends at tomorrow's local midnight. Use calendar constructors,
not multiples of 24 hours, and serialize the resulting UTC-aware timestamps.

Custom inputs represent inclusive local start/end dates. Require both valid dates
and start no later than end; convert the end to the next local midnight for the
server's exclusive `to`. One-day ranges are valid. Test leap dates, DST transitions,
UTC offsets, exact boundary inclusion/exclusion and missing/reversed input.
Show the reader's local date interpretation and active period.

Share normalized filter construction and validation between catalogue requests
and research mapping. Stable IDs, UTC timestamps and ordering come from typed
application state, never publisher strings or model instructions.

### 4. Research uses the visible applied snapshot

Show applied source/category/date chips in the agent panel alongside current-item
context. Send passes those fields as ResearchRequest.filters; item selection still
passes its stored ID. Do not append search text as hidden prompt instructions.

Freeze request context at Send and retain it with the resulting answer. Later draft
or applied browsing changes affect the next question, not the previous result.
Removing/replacing current item and reset behavior must not mislabel a completed
answer under new constraints. Preserve independent scrolling, lofi and explicit
Stop; neither filter changes nor panel opening invoke generation.

### 5. Measured publication with explicit open acceptance

Reconcile current UI evidence and publish first in its own ledgers and commits.
Use the regular browser only; never export credentials or invent automated proof
from manual user observations. If required automation cannot operate through that
workflow, surface the concrete capability limitation before changing its criteria.
Preserve evaluation worktree changes, receipts and cumulative accounting.

On 2026-11-01 the user approved selective publication and proceeding with filters
while unavailable Azure checks remain open. Available automation controls only
VS Code's integrated browser, not the existing regular-browser session. Do not
request another sign-in or add a verifier silently. Keep original automated
acceptance tasks unchecked; this exception permits progress, not phase acceptance.

For filters, run local type/lint/unit/contract/headless browser and accessibility
checks, then the primary gate. Deploy only a reviewed immutable UI image/revision
in the retained ACA layer; no backend or grant change is planned. Verify config/
image readback, regular-browser filter/context behavior and required Azure evidence,
then selectively commit with exact-source implementation and measured-status CI.
Archive only when all actual obligations pass.

### 6. Confirmed follow-on API direction, not implementation

After filters, the next owning slice designs a cached HTTP news API. Co-hosting
in the current MCP ACA app is the confirmed preferred direction where compatible:
reuse its read-only repository/embedding services, workload identity and delegated
news.read audience/scope. Authenticate and authorize before cache lookup/hits.
Keep credentials and conversations out of the cache.

The API slice separately defines its routes, response/error shapes, detail/cursor
contract, cache keys, freshness/invalidation, per-user authorization partitioning
and multi-replica implications. A shared host must not assume new routes inherit
MCP authentication or CORS automatically. No Redis/resource is selected now.
The subsequent UI slice swaps NewsCatalog to HTTP and removes browser MCP coupling
where unused; agent interaction and agent-to-MCP tools remain A2A/MCP respectively.
Only afterwards resume versioned evaluations, preserving prior costs and failed
attempts. Do not implement those future slices as part of filters.

## Risks / Trade-offs

- Implicit filter application can incur repeated embeddings -> Explicit Apply/
  Search and a separate applied query snapshot.
- Calendar dates differ from fixed-hour ranges -> State local calendar semantics
  and test DST, leap dates and exact UTC wire boundaries.
- Catalogue choices are dynamic -> Validate response/IDs and retain explicit
  absence/error states without silent substitution.
- Browsing can outpace a running question -> Immutable displayed request context;
  never relabel its result or replay generation.
- Release closure can get stuck on unavailable tooling -> Honest open evidence,
  a concrete capability report and regular-browser workflow, not new sign-in loops.

## Migration Plan

1. Reconcile current UI release evidence/publication and document safe usage
   estimates versus unknowns without restarting evaluations; preserve explicitly
   unavailable Azure checks as open under the approved sequencing exception.
2. Implement filters/catalogue/date validation and A2A context with adjacent tests
   and owning documentation; preserve existing UX.
3. Run local checks, review the UI-only native plan, deploy and verify exact image/
   configuration plus filter/context/browser evidence in the retained environment.
4. Publish selective implementation/status commits and exact-source CI; keep all
   unrelated phase/evaluation tasks open.

Rollback uses the prior immutable UI image and unchanged runtime configuration.
No identity, cache, schema or backend rollback is involved.
