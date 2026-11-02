# Design

## Context

See [proposal](proposal.md) for motivation and [HTTP contract](specs/news-http-api/spec.md)
for requirements. Observed implementation seams:

- `newsloom_mcp.app.create_app` builds the official SDK app with custom Starlette
  health routes. Tool admission currently uses one local four-slot semaphore.
  Custom API routes cannot assume that SDK protocol authorization protects them.
- `EntraVerifier` reuses the shared trusted-key/claim verifier and maps `news.read`
  to the existing fully-qualified scope. `verify_token` intentionally returns
  no token on trusted-key failure; HTTP needs explicit key-unavailable handling
  without changing existing MCP semantics.
- `Services` owns typed repository factories, query embeddings and safe observers.
  `Repository` exposes recent/detail/sources/search and parameterized predicates,
  but has no paging method. Runtime uses read-only repeatable-read transactions,
  five-second statement timeouts and the existing managed identity.
- `McpBrowserCors` rejects browser paths other than POST `/mcp`, so simply adding
  routes would not produce a usable browser API. SDK transport-security settings
  likewise do not establish protection for arbitrary custom routes.
- The MCP ACA app is one replica, 0.25 CPU/0.5 GiB, with retained identity/model/
  read-only database access. Native azd hooks and independent `mcp_control` readback
  bind the immutable image, environment and browser origins.
- Existing HTTP, database, auth, CORS and privacy tests provide authored seams.
  The deployed browser uses a transport-neutral NewsCatalog interface, but will
  remain on its current adapter throughout this slice.

The user selected a process-local 60-second cache and browse-only pagination.
Shared cache resources and semantic result sessions were offered and not selected.

## Goals / Non-Goals

**Goals:** One small additive API using the existing app lifecycle and authority;
measurable avoided work on repeat calls; deterministic keyset traversal on stable
data; explicit failure/privacy behavior and easy image/flag rollback.

**Non-Goals:** A second web framework/service, server-to-self MCP HTTP, generic
cache framework, new DB privileges/schema, durable pagination snapshots, model
generation, UI adapter/UX implementation, or quality-evaluation restart.

## Decisions

### 1. Additive co-hosting, explicit opt-in and shared service capacity

Use the existing Starlette/SDK composition and runtime `Services`. Add API
handlers as explicit routes, with an application-owned boundary around them.
Keep one process, one credential/client lifecycle and one repository/embedding
implementation; do not make an HTTP request to the app's own MCP endpoint.

Extract only the small shared execution/admission seam needed by both surfaces.
All business operations share the existing four concurrent slots, one-second
admission timeout and 90-second total execution deadline. Preserve readiness's
existing bounded use of capacity. A cache hit is still authenticated, validated
and admitted, but performs no repository/model work. No extra four-slot API pool.
Cancellation includes disconnect detection, not merely task cancellation in tests.
No unbounded background fills, automatic retries or stale-while-revalidate.

Use a default-off `NEWS_API_ENABLED` runtime setting, owned by a matching
`news_api_enabled` MCP Terraform input and preparation/readback. Disabled means
no API data routes and no response-cache instance. The API base URL is the existing
MCP HTTPS origin plus `/api/v1`; registration/consent/resource URL stay unchanged.
Enabling requires a reviewed MCP image/flag-only plan. Avoid changing the existing
UI configuration, identity layer or app profile.

Alternatives: a separate app adds identity/ingress/cost; proxying MCP adds protocol
overhead; SDK routes without explicit guards leave an authorization gap.

### 2. Minimal versioned route/response contract

| Route | Request | Successful response |
| --- | --- | --- |
| GET `/api/v1/news` | `source?`, `category?`, repeated `tags?`, `from?`, `to?`, `limit?`, `cursor?` | `{items, next_cursor, meta}` |
| GET `/api/v1/news/{id}` | UUID path segment, no query parameters | `{item, meta}` |
| GET `/api/v1/sources` | no query parameters | `{sources, categories, meta}` |
| POST `/api/v1/search` | JSON `{query, source?, category?, tags?, from?, to?, limit?}` | `{items, next_cursor: null, meta}` |

Use existing public item/detail/source models. Browse items have the ordinary
public item projection; search items include the existing finite cosine
`similarity`. `meta` contains `read_at` (UTC-aware origin read time),
`cache_age_seconds` (nonnegative server-measured age) and
`result_scope` (`page`, `bounded`, `item` or `catalogue`). These do not echo query,
identity or filters. On a miss, age includes time since the backing read began.
On a hit, update only age, never the underlying read time or expiry.

Default limit is 20, maximum 50. POST query is required/nonblank, trimmed only
as in existing search, at most 2,048 characters. Reuse typed source/category,
normalized ALL-tags and aware-date contracts, rejecting unknown fields. GET
parsing explicitly converts only ASCII decimal integer limits; no bool/fraction/
clamping. Duplicate scalar parameters are invalid; only `tags` repeats, with
the existing maximum ten inputs and normalized deduplication. No `query` on
GET news, no `cursor` on POST search, no URL-based semantic query logging.

Return JSON errors `{error: {code, request_id}}`. Codes are an explicit fixed
allowlist; generate request IDs server-side. Do not return raw Pydantic error
objects, submitted values, SQL errors or dependency exception strings.

| Status | Meaning |
| --- | --- |
| 400 | invalid fields, cursor, dates, query, UUID or JSON |
| 401 | missing/invalid token, with fixed Bearer challenge |
| 403 | valid token without delegated scope; disallowed host/origin |
| 404 | unknown route or valid absent item |
| 405 | method unsupported for the route |
| 413 | request/URI limit exceeded |
| 415 | search body is not supported JSON |
| 429 | shared admission capacity exhausted |
| 503 | trusted keys/storage/model unavailable, invalid dependency result or oversized response |
| 504 | overall operation deadline exceeded |

No errors are cached. Responses, including errors, use `Cache-Control: no-store`;
this is an application cache, not a browser/CDN cache. No ETags or 304 path.
Cap request body at 64 KiB, raw request target at 8 KiB and encoded cursor at
2 KiB. Read bodies incrementally; cap serialized responses at 1 MiB and fail
explicitly rather than truncate. A successful response too large for cache
admission is returned uncached if within the response limit.

Alternatives: GET semantic search risks query-string retention; separate recent
and metadata routes duplicate behavior. A unified browse route covers both
without changing MCP schemas or the future NewsCatalog seam.

### 3. Authenticate first and keep authorization partitioning explicit

For each API request: bound host/origin/method/transport framing, then verify the
Bearer token and require the existing delegated `news.read`, then validate typed
input, then shared admission and cache lookup/work. Preflight is a route-specific
exception with no auth/cache work. Any early framing rejection accesses no data.

Reuse `verify_claims` and its configured trusted keys; distinguish
`TrustedKeysFailure` (503) from invalid claims (401) and missing scope (403).
Do not weaken or change `verify_token` for MCP. Require one unambiguous bounded
Authorization header; never use caller-provided identity headers.

Derive an in-memory SHA-256 authorization partition from the verified tenant,
subject, authorized client (`azp`), normalized delegated scopes and a fixed
authorization-policy version. Use length-safe canonical JSON, not concatenated
unseparated fields. Do not store/log raw claims or bearer token with the entry.
Partition hashes are internal only, not telemetry labels or public headers.

All current authorized callers read the same corpus. Still partition per caller
so future authority changes cannot silently reuse globally cached responses.
Any future row-level access policy must update both repository predicates and
policy version; a cache key is not a substitute for authorization.

Alternative: globally shared public-news caching would improve reuse, but makes
future authorization changes riskier. Token-keyed caching retains credentials
and is unnecessary for renewal by the same caller.

### 4. Small disposable success cache, strict lifetime and no hidden persistence

One cache per enabled app process; use an LRU with at most 128 entries, 8 MiB
of serialized cached payload bytes in total and 512 KiB per entry. Bound key/
entry metadata through the fixed-size key and entry count as well. Evict expired
entries first, then least-recently-used entries. A hit can update recency but not
expiry. Cache insertion/eviction is atomic and contains no awaited external I/O.

Key = digest of API/policy version, caller partition, operation, validated
normalized arguments including page size/cursor tuple, and embedding deployment/
model/version for semantic responses. Preserve trimmed query semantics; do not
casefold/rewrite questions. Hash request input instead of storing query text in
keys. Sort normalized tags for canonical ALL-tags equivalence; normalize aware
timestamps to UTC. Store immutable serialized public payload and read-time
metadata only, not mutable model objects, embeddings or request objects.

Cache only complete validated 200 responses, including successful empty
collections. Do not cache 404/error responses or partial/cancelled work.
Record monotonic read-start time at the backing repository snapshot boundary;
expiry is read-start + 60 seconds, not last access or response serialization.
If work completes after expiry, return its bounded result without caching it.
This limits reuse age, not upstream ingestion lag or time spent transmitting.
Do not claim articles are less than 60 seconds old.

No invalidation bus: new/updated/deleted data becomes visible after expiry or
eviction; no stale-on-error. The app has no news-write path. Each worker/revision
starts empty and has independent bounded freshness. No guaranteed cache hit
across replicas, and no deployment profile change to create affinity.
Concurrent identical misses may perform duplicate work, bounded by the shared
four slots; deliberately omit single-flight/task-ownership complexity initially.

Alternatives: Redis needs a new resource; sliding TTL violates the user's
freshness choice; caching query vectors or failures adds a second contract and
privacy surface without being necessary for response reuse.

### 5. Browse-only keysets, not opaque server sessions

Add a typed repository browse operation reusing existing public projections and
parameterized predicates. Query at most `limit + 1`; emit at most `limit` items
and a next cursor only if the lookahead row exists. Order:
`published_at DESC, id ASC`. After a last tuple `(p, i)`, continuation is
`published_at < p OR (published_at = p AND id > i)`, applied together with all
metadata/date predicates. Use exact stored timestamp precision and UUID ordering.

Cursor is URL-safe base64 of bounded strict JSON: schema version 1, last
publication timestamp/UUID and SHA-256 canonical filter/page-size fingerprint.
Normalize before comparison; bind to route/schema, source/category/sorted tags,
UTC bounds and limit. Reject invalid encoding, unknown fields/versions,
non-aware dates, invalid UUIDs and mismatched fingerprints before execution.
Do not put query text, credentials, caller claims, SQL fragments or vectors in it.

Cursors are opaque to clients but not secret, signed capabilities or authorization
proof. Tampering with a valid tuple only selects a different position in already
authorized public news; never trust it for identity or query authority. This avoids
introducing a signing secret/resource just for read-only position state. Cursors
can survive app/cache restarts because they carry position, not a process-local
session key.

Traversal is explicitly live, not repeatable-read across requests. Fixed data
has no tie skips/duplicates; new rows ahead of the cursor require restarting,
and corrections/deletions can alter membership. Within a request, preserve the
existing read-only snapshot. POST semantic search has no cursor/total count and
returns a bounded top-k, avoiding vector storage and multi-request ranking drift.

Alternatives: OFFSET silently drifts and degrades with depth; a timestamp-only
cursor skips ties; semantic snapshots require result/vector sessions the user
explicitly deferred.

### 6. Route-aware CORS and privacy-safe observations

Preserve existing `/mcp` exact-origin/header/method behavior. Extend the wrapper
via route-aware policy rather than permitting every method on every path:

- API GET news/detail/sources; API POST search.
- Headers limited to Authorization, Accept and Content-Type. MCP-only headers
  remain scoped to MCP; no cookies, credentials, wildcard origins or redirects.
- Validate the same configured exact hosts for API requests even without Origin.
- Preflight returns 204 with 300-second max-age and correct Vary fields;
  actual allowed-origin auth/validation/dependency errors remain readable.
- A2A runs elsewhere and is unchanged. Do not alter browser CSP/config until
  the later UI adapter slice.

Add separate fixed API route/outcome/cache hit/miss/bypass observations without
labelling API calls as MCP tools. Extend telemetry allowlists deliberately; never
use raw paths/UUIDs, query strings, filters, cursor text, partition hashes, claims,
article data, tokens, prompts/completions or exception strings as attributes.
Keep uvicorn access logging off. Privacy tests cover dependencies and every
failure path, not merely the happy-path logger.

### 7. Owning delivery, rollout and rollback

Before cloud changes run focused HTTP/auth/cache/DB/CORS/privacy checks, then
the primary gate and package builds on the exact selective publication tree.
Retain recursive `.dockerignore` protections; verify actual ACR upload inputs
when build rules change. Pin source/npm/config hashes and immutable image digest.

Review/apply only the retained MCP layer image and API enablement input; no
registration/consent/resource/profile changes. Independent readback verifies the
flag, image, existing host/origin, workload identity, registry binding, DB/model
configuration and unchanged agent/UI/job schedules. Verify real API/MCP parity,
safe cache miss/hit counts and denial before warm-cache access in Azure using
approved existing delegated workflows; never export the user's credentials or
reopen a separate test-browser sign-in.

Existing UI acceptance stays open. This API has its own acceptance ledger; known
regular-browser automation limitations must be surfaced, not silently waived by
the prior filter publication exception. Record only safe outcomes/counts/hashes,
distinguishing authored auth tests, actual workload reads and manual browser
observations. Measure live semantic miss/hit embedding counts and usage estimates
without replaying parked evaluations or charging agent-chat receipts for embeddings.
Publish selective implementation and measured-status commits with exact-source CI
only after their actual gates or a newly explicit user exception; archive only
with complete evidence and an explicit request.

Rollback disables only the API and/or restores the retained immutable MCP image
through a fresh reviewed owning plan, preserving `/mcp`, origins, identity and
all data. This slice changes no database schema or persistent cache state.

## Risks / Trade-offs

- Shared small app capacity -> share the existing execution slots; test concurrent
  API/MCP work and fail explicitly rather than increase replicas/permissions.
- Cached news is not instantly fresh -> non-sliding read-start TTL, visible age
  and no stale error fallback; document that ingestion latency is separate.
- Per-caller partitions reduce hit rate -> accept this for authority isolation;
  report actual counts instead of promising savings.
- Live paging is not snapshot export -> tie-correct keysets on stable data and
  explicit concurrent-update limitations; no exhaustive semantic pagination.
- Custom SDK routes can bypass guards -> explicit API auth/host/CORS tests plus
  regression checks for native and current browser MCP clients.
- Live delegated verification may be unavailable -> report the exact limitation
  and leave acceptance open, with no credential export or invented parity proof.
