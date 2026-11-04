# News HTTP API

Status: deployed early access in
[`cached-news-api`](../openspec/changes/archive/2026-11-04-cached-news-api/tasks.md). Local/real-database
checks, owning deployment readback, live API denials/preflight/health and existing
authenticated native MCP discovery passed. Authenticated live HTTP/cache parity
and usage acceptance remain open under an explicit user-approved publication
exception. The [UI migration](ui.md#http-catalogue-migration) now uses HTTP;
agent interactions/tools remain A2A/MCP. Its own signed-in acceptance remains open.
Original cached-API deployment source:
`a5588eaebe31132919b22e4b3f2b9d044cd85e66dbfa3b4f5d2087e5e6568ecd`.
Implementation `3c798ae8b5fac8c5323d15ea7357fff72f96c0f4` passed exact-source CI
`41449774908`. Measured-status commit `bfe5354` passed separate CI `41450605684`;
no full API acceptance, UI migration or archival is claimed.

## Contract

The API will share the existing MCP HTTPS origin and delegated `news.read`
audience/scope, not another registration or user credential.

| Route | Request | Success |
| --- | --- | --- |
| GET `/api/v1/news` | source/category, repeated tags, aware from/to, limit, cursor | items, next_cursor, meta |
| GET `/api/v1/news/{id}` | stored news UUID | item, meta |
| GET `/api/v1/sources` | no parameters | sources, categories, meta |
| POST `/api/v1/search` | JSON query and optional metadata/limit | items, next_cursor null, meta |
| GET `/api/v1/briefing` | no parameters; additional default-off briefing feature | briefing or null, refresh, meta |

Default limit is 20; integers 1-50 only. Unknown/duplicate scalar fields and blank
queries fail, never silently broaden. Tags match ALL normalized terms.
Publication `from` is inclusive and `to` exclusive; both require timezone.
Metadata-only browsing never embeds. Semantic search is bounded top-k with no
pagination or completeness claim, retaining the existing exact filtered cosine
ranking and model/vector validation.

`meta` contains UTC `read_at`, nonnegative `cache_age_seconds` and `result_scope`
(`page`, `bounded`, `item`, `catalogue`, or `briefing`). Only the public projections
are returned. Detail adds stored author/date origin/publisher categories;
valid absent UUIDs return 404, malformed UUIDs 400.

The [daily briefing](briefing.md) extension is deployed early access, with
successful artifact and authenticated read/quality acceptance still open.
Its current image source is
`a063f364dcfdbe6fb82433f3689f00834d3ecba34bfe58afae99df5239758551`.
`NEWS_BRIEFING_ENABLED` defaults to false and
requires the API flag plus its additive schema/read grants. It reads a shared
published artifact only; no generation/model write is dispatched by GET.
Null artifact/pending status, an empty-week artifact, stale last-good content
and service errors are distinct. Its cache key includes the expected 05:00 UTC
cutoff so the prior day's ready status cannot cross the daily boundary.
MCP remains read-only and existing delegated scope/consent/origins are unchanged.

Browse continuation sorts publication descending, UUID ascending. Follow the
returned opaque cursor with the same normalized filters/page size. Cursors
are validated position data, not authorization proofs or secrets. Traversal
over unchanged rows has no tie skips/duplicates; new rows ahead of the cursor
require restarting, and updates/deletions can change membership. There is no
cross-request database snapshot.

Errors contain only `{error: {code, request_id}}`: 400 invalid input, 401 invalid/
missing token, 403 insufficient scope/host/origin, 404 absent item/route, 405
method, 413 request bound, 415 content type, 429 admission, 503 dependency/result
failure or 504 deadline. Inputs and raw validation/exception details are never
echoed. All responses are `Cache-Control: no-store`; no browser/CDN caching.

## Cache and execution

Every request verifies the configured tenant/issuer/audience/signature/lifetime
and delegated scope before looking at cache contents. Caller partitions hash
verified tenant/subject/client, normalized scopes and policy version. They are
never credentials or diagnostic labels; token renewal does not invalidate an
otherwise identical caller partition. Policy changes must update the version.

The disposable in-process cache holds only complete 200 public responses:
128 entries, 8 MiB serialized payload total, 512 KiB per entry, LRU eviction.
Lifetime is 60 seconds from the backing read start, never last access. Hits
avoid repository and embedding calls; errors/404s/cancelled or expired fills
are not cached. Large otherwise valid responses bypass cache rather than truncate.
There is no stale-on-error, vector caching, single-flight/background refresh,
durable storage, cross-worker coherence or guaranteed hit across revisions.
Cache freshness is not a promise about ingestion lag or article age.

HTTP operations share MCP's four slots, one-second admission and 90-second
deadline, rather than adding another pool. Disconnect/cancellation closes work
and releases capacity. Request bodies are at most 64 KiB, raw targets 8 KiB,
cursors 2 KiB and serialized responses 1 MiB. No automatic application retry,
fallback ranking or model substitution is introduced.

## Hosting and privacy

`NEWS_API_ENABLED` accepts only `true` or `false`, defaults to false and is
owned by the existing MCP Terraform layer. Disabled instances allocate no
response cache. The existing managed identity, model, database role and exact
origin list are reused; API routes have explicit host/method/authentication/CORS
guards, independent of MCP SDK routes.

API preflight accepts only its route's GET/POST and Authorization, Accept and
Content-Type headers, with exact origin and no credentials. It does not invoke
auth/cache/data/models. Invalid/duplicate origins and hosts fail before execution;
approved-origin auth/error responses remain readable. Native `/mcp`, protected
resource metadata and current browser MCP headers retain their existing contract.

Only fixed route/outcome/cache categories, counts and timings are observed.
Request IDs are generated server-side; bodies, URLs/querystrings, cursors,
article data, claims, cache partition hashes and dependency errors are not logged.
The existing embedding counters meter actual model calls, not cache hits.
Observed cache hit rates and cost savings remain unknown until live measurement.

## Owning rollout

Run local checks and real loopback PG18/pgvector paging tests before cloud work.
Build and preview only the retained MCP image/API flag through existing azd:

```bash
bash scripts/check.sh
uv build --all-packages
uv run --locked newsloom-platform build-mcp
azd env set NEWS_API_ENABLED true
azd provision mcp --preview
# Apply only after reviewing the fresh owning plan.
azd provision mcp
uv run --locked newsloom-platform verify-mcp-layer
```

Independent image/identity/origin/model/flag readback is not signed-in API
acceptance. Record actual authorization-before-hit, HTTP/MCP parity, cursor and
miss/hit/TTL checks separately from authored fixtures and regular-browser reports.
Never export credentials or start another test-browser sign-in. If the required
workflow is unavailable, leave its acceptance task open and report the limitation.

Rollback uses a freshly reviewed retained MCP image/flag plan, not environment
recreation. Preserve identity, consent, origins, schemas and all existing jobs.
No new resource or permission is part of this slice. UI migration delivery is
tracked separately; evaluations resume only after it, with old receipts intact.
The active [UI migration](../openspec/changes/archive/2026-11-04-ui-http-news-catalog/tasks.md) owns
HTTP browser composition, shareable detail pages and a 200-item display cap.
It does not change this API's TTL, cursor, permissions or semantic-result contract.
