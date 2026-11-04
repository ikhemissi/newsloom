# Proposal

## Why

The cached HTTP API is deployed, but the UI still performs browser MCP exchanges
and cannot use its detail/cursor contracts. Moving NewsCatalog to HTTP now
connects the delivered backend to a useful reader journey before returning to
versioned evaluations.

## What Changes

- Replace browser MCP news access with a typed HTTP NewsCatalog adapter: GET
  news/sources/detail and explicit POST semantic search, using existing delegated
  `news.read`. Agent interactions remain A2A; agent tools remain MCP.
- Preserve latest-20 defaults, explicit source/category/local-calendar filtering,
  submitted search, visible immutable research context, lofi and independent
  agent-panel scrolling. No automatic search, generation or transport fallback.
- Add user-selected explicit Load more for newest-first browsing/metadata
  filters, 20 per request, capped at 200 displayed items. At the cap, offer an
  explicit restart without pretending the server has no more records. Semantic
  search stays bounded to the current 20 results, with no Load more.
- Add user-selected shareable `/news/<id>` detail pages with Back to news,
  stored summary/metadata, safe Open original and explicit Ask about this.
  Do not fetch or interpret full publisher articles.
- Migrate runtime endpoint/scope naming and owning UI config/CSP/readback with
  an explicit app-only rollback control; preserve existing registrations/consent.
  Remove unused browser MCP SDK coupling and replace its tests with HTTP contracts.
- Update owning phase/capability assignments, ADRs and runbooks during
  implementation; preserve all historical UI/API acceptance evidence and parked
  evaluation work.

## Capabilities

### New Capabilities

- `browser-news-navigation`: Authorized HTTP-backed browsing, bounded explicit
  continuation and shareable stored-item navigation with safe agent context.

### Modified Capabilities

None in main specs. Earlier still-active `browser-news-feed` and
`browser-news-filters` deltas describe their as-delivered MCP transport. This
change deliberately supersedes that browser transport and single-page bound,
not their historical receipts or filtering/research semantics. Owning docs must
identify the transition; future archival must not publish conflicting historical
transport requirements as simultaneous current contracts.

## Impact

Owns [PRD-3 Step 3.5](../../../../docs/prd-3.md#delivery-plan), supporting
[P3-C04/P3-C07](../../../../docs/prd-3-capabilities.md). Prerequisites are the
published filters and deployed [HTTP API](../../../../docs/news-api.md). The API's
authenticated live/cache acceptance and existing UI Azure checks remain open;
this change must collect its own actual browser/API evidence, not silently
inherit a publication exception.

Affected surfaces: `services/web` domain, catalogue/config/auth composition,
navigation/list/detail state and tests; npm manifests/lock; owning UI Terraform/
platform preparation/readback, static container configuration and directly related
documentation. Prefer existing React/native History APIs with no new routing or
query-cache dependency. Remove the unused browser MCP client; backend MCP remains.

Reuse the same SPA, delegated news audience/scope, managed identities, ACA origin/
profile, API cache and model deployments. No new resource, role, consent, model,
backend route or schema migration is planned. Metadata paging/detail invokes no
inference; search and explicit A2A retain existing bounded costs. Do not promise
cache savings or full-phase acceptance without measurements.

Out of scope: API/cache-policy changes, semantic pagination, multi-selection,
full article fetching, persistent browse/chat history, unbounded list growth,
new framework/resources, evaluation reruns and automatic deployment/archival.
