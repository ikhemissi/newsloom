# Proposal

## Why

The deployed UI currently performs MCP protocol exchanges for every catalogue
load. A small authenticated HTTP news API can reduce repeated database/embedding
work and establish detail/paging contracts before a separate UI adapter migration,
without introducing another app, identity or cache service.

## What Changes

- Co-host a versioned read-only HTTP API at `/api/v1` in the existing MCP ACA
  app/process, reusing its permitted news projections and query embedding service.
  Keep `/mcp`, native discovery/authentication and agent tools compatible.
- Require the same verified single-tenant delegated `news.read` audience/scope
  on every API request, before any cache access, including hits. Define route-
  specific host/origin/method/body controls rather than inheriting SDK protection.
- Add recent/metadata browsing, source/category discovery, stored-item detail and
  explicit semantic search. Reuse existing filter/ranking semantics and expose no
  raw articles, vectors or processing data.
- Add the user-selected process-local bounded cache with an absolute 60-second
  maximum lifetime, authorization partitioning and bounded memory. No Redis,
  persistent cache, credentials, conversation or browser-cache storage.
- Add deterministic keyset cursors for newest-first browsing/metadata filters.
  Per the user's choice, semantic search remains bounded to at most 50 relevance-
  ranked items with no pagination or completeness claim.
- Define typed versioned success/error shapes, finite shared execution budgets,
  privacy-safe cache/HTTP observations and regression/acceptance evidence.
- During implementation, update owning PRD-3 assignments, capabilities, ADRs and
  runbooks. The API is delivered before the separate NewsCatalog HTTP adapter;
  A2A interaction and agent-to-MCP tools remain unchanged.

## Capabilities

### New Capabilities

- `news-http-api`: Authorized read-only HTTP news access with bounded response
  caching, browse cursors, detail/discovery and explicit semantic search.

### Modified Capabilities

None. Existing `mcp-serving` and `news-search` contracts remain intact. Shared
internal extraction must preserve those delivered contracts; the new cache and
pagination contract applies to HTTP only.

## Impact

Owns the API delivery slice in [PRD-3](../../../../docs/prd-3.md#delivery-plan),
supporting [P3-C04/P3-C07](../../../../docs/prd-3-capabilities.md). Prerequisites are
the deployed MCP/research/UI foundation and published filters. Existing signed-in
UI acceptance remains explicitly open; it is not retroactively completed here.

Affected surfaces: `services/mcp` app composition, verifier integration,
repository paging, typed API/cache boundary, telemetry and runtime configuration;
owning MCP deployment/readback and adjacent HTTP/database/privacy tests. No schema
change or migration is expected: keyset paging uses already readable publication/
ID columns. Reuse installed Starlette/Pydantic, async PostgreSQL and embedding
interfaces; no new dependency is planned.

Identity and capacity: retain existing API registration, consent, managed
identity, read-only database role, region, model deployments and ACA profile.
No new scope, role, resource or model is selected. Cache hits avoid repository/
embedding work; misses retain existing bounded embedding costs. No hit-rate,
latency saving, invoice or evaluation acceptance is claimed before measurement.
Any required profile/resource/permission increase must pause for separate review.

Out of scope: switching the deployed UI, browser detail/pagination UX, A2A or MCP
wire changes, agent-result caching, new query generation, shared distributed
caches, durable snapshots, exhaustive semantic pagination, evaluation reruns,
automatic deployment and archival of incomplete changes.
