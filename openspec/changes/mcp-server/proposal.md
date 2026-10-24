# Proposal

## Why

Newsloom now stores screened, enriched news and embeddings, but clients cannot
browse or search them through a deployed service. PRD-1 Step 1.5 must make that
data accessible to an Entra-signed-in VS Code user before phase acceptance.

## What Changes

- Deliver the `mcp-server` slice of [PRD-1](../../../docs/prd-1.md), owning P1-C06
  browsing/discovery, P1-C07 filtered search, P1-C08 user access and P1-C10 service
  visibility. Prerequisites are the verified shared platform and
  [completed enrichment](../enrichment/tasks.md#acceptance-evidence), including
  its existing `news` schema. Enrichment is complete but not yet archived; this
  proposal does not archive it or change its acceptance evidence.
- Expose an authenticated Streamable HTTP MCP endpoint with four read-only tools:
  `get_recent_news`, `get_news_item`, `list_sources`, and `search_news`. Return
  typed stored-news data, never queue/quarantine bodies or database internals.
- Use single-tenant Entra delegated `news.read` access. Inventory/reuse matching
  API and public-client registrations; create only missing owning-slice
  registrations after an explicit preview. Verify PKCE browser sign-in with
  a pre-registered VS Code OAuth client, not dynamic registration or static tokens.
- Use the existing MCP managed identity for read-only news access, query
  embeddings and telemetry. User tokens never reach PostgreSQL or Foundry.
- Apply approved defaults: 10 results, maximum 50, all requested tags, inclusive
  UTC lower date bounds and exclusive upper bounds. Metadata-only results are
  newest first; semantic results rank within all filters by cosine similarity
  without a guessed relevance cutoff.
- Freeze 20 labelled query cases over an isolated authored corpus. Require mean
  recall@5 of at least 0.80 independently for filtered and unfiltered cases, zero
  filter violations, actual protocol/authentication tests and a real Azure/VS Code
  readback of stored results. Do not seed fixtures into production news.
  The user approved a short-lived isolated evaluation schema in the existing
  database, created/removed by the migration identity with temporary read-only
  MCP access; the serving endpoint cannot address that schema.
- Deploy one always-on Consumption app through the existing azd environment,
  with a digest-pinned image, health checks, bounded requests and private
  operational diagnostics.

Out of scope: write/admin MCP tools, article retrieval, enrichment or scanner
changes, quarantine/dead-letter releases, agent/OBO/browser UI work, a second
database/search service, new model deployments/capacity, multitenancy, dynamic
client registration, and full phase-wide acceptance beyond this slice.

## Capabilities

### New Capabilities

- `mcp-serving`: authenticated protocol service, stored-news browsing/discovery,
  least-privilege runtime boundaries, deployment and end-user acceptance.
- `news-search`: metadata filters, query embeddings, filtered cosine ranking and
  evidence-based retrieval quality.

### Modified Capabilities

None. The existing access, telemetry and persistent-platform contracts remain
prerequisites; the new capabilities add MCP behavior without rewriting foundation
acceptance or modifying ingestion/enrichment semantics.

## Impact

- Implement the existing [MCP package](../../../services/mcp/) with the official
  MCP Python SDK, typed tools/repository/authentication and focused tests.
  Add only owning runtime/test dependencies and lock supported stable versions.
- Add an additive migration granting the existing MCP role read access only to
  the public-news projection. Reuse the existing category catalogue and news
  indexes; the runtime does not query feed/queue/quarantine tables or run DDL.
- Extend [operator image/deployment wiring](../../../services/platform/src/newsloom_platform/control.py)
  and [azd](../../../azure.yaml) with an owning MCP app layer and explicit Entra
  registration setup. Keep actual directory/resource/client identifiers in ignored
  environment configuration, never committed examples.
- Document sign-in/consent, allowed callbacks, the endpoint and troubleshooting
  in an MCP runbook; update owning capabilities, ADRs and phase status only as
  delivery evidence becomes real.
- Preserve the existing developer environment, shared resources, runtime
  identities, news data and both schedules. One always-on replica adds metered
  compute; query embedding shares existing quota. Refresh actual compute/model
  pricing and supported SDK/Entra contracts before deployment.
- Directory permissions, consent, stable SDK/Python compatibility and actual
  VS Code sign-in are explicit implementation preflights. Missing permission,
  capacity, model availability or interoperability blocks acceptance; it does not
  authorize broader grants, client secrets, an auth proxy or a login bypass.
