# Tasks

Planning only. No API/cache runtime, cloud mutation, UI transport migration or
new acceptance evidence is claimed. The user selected a process-local 60-second
cache and browse-only cursors; semantic search is explicitly bounded, not paged.
Existing signed-in UI/filter acceptance and parked evaluation work remain open.

## 1. Typed HTTP and browsing contracts

- [ ] 1.1 Add typed versioned request/response/error/cursor models using existing public news/detail/discovery/filter contracts; implement bounded explicit GET parsing and POST JSON validation. Verify limit defaults/exact 1-50 bounds, unknown/duplicate fields, tag normalization, UTC boundary equivalence, blank/oversized queries, invalid UUIDs/JSON/content types and cursor errors without repository/model calls; document route shapes, safe status codes and bounded semantic results in the owning API runbook.
- [ ] 1.2 Add the parameterized browse repository operation with publication-descending/UUID-ascending keysets and limit-plus-one lookahead; reuse existing projections/predicates without changing MCP schemas. Run real local PostgreSQL/pgvector tests under the read-only MCP role for tie-heavy multi-page traversal, exact page multiples, all filters, absent detail, empty pages, cursor normalization/restart behavior and concurrent insert/update/delete semantics. Document live traversal limitations; do not count conditional skips as paging verification.

## 2. Authorization, cache and shared execution

- [ ] 2.1 Implement explicit HTTP authorization with the configured shared trusted-key verifier and same delegated news.read requirement; distinguish invalid tokens, missing scope and trusted-key unavailability without weakening MCP verification. Test actual ASGI requests with signed authored tokens for wrong audience/tenant/issuer/key/lifetime/algorithm, app-only/wrong-scope access, duplicate authorization and same-caller renewal; verify a spy cache is never consulted on denial and document caller partition/policy-version semantics without retaining claims or tokens.
- [ ] 2.2 Implement the bounded process-local immutable-success cache: absolute read-start TTL 60 seconds, 128 entries, 8 MiB payload total, 512 KiB per entry, LRU/expiry eviction and normalized caller/operation/model/request keys. Test exact just-before/at-expiry boundaries with a fake clock, non-sliding hits, two-caller/client/scope/policy separation, equivalent normalized inputs, byte/entry thresholds, oversized-entry bypass, successful empty results, restart isolation and no caching of errors/404/cancelled/late fills/vectors. Document freshness, upstream ingestion lag and independent-worker behavior.
- [ ] 2.3 Wire news/detail/sources/search handlers through existing typed services and one shared four-slot MCP/API admission boundary, preserving readiness limits and existing tool behavior. Verify hits perform zero repository/embedding work, semantic misses use the existing bounded vector/ranking path, metadata misses perform zero inference, mixed MCP/API concurrency cannot exceed four, admission/deadline/response-size failures are typed and disconnect/cancellation releases resources with no partial cache insert. Document request/response limits and no stale-on-error or automatic fallback/replay.

## 3. Explicit hosting and privacy boundaries

- [ ] 3.1 Make API host/origin/method policy route-aware while preserving existing MCP behavior; test API GET versus POST, unknown/disabled routes, no-Origin native requests, duplicate/unapproved origins, wrong hosts, exact preflight headers/Vary/max-age and readable allowed-origin error responses. Verify preflight consumes no auth/cache/repository/model work and that modern MCP discovery/tool/cancellation browser contracts and native clients still pass; document the shared origin without broadening credentials/methods.
- [ ] 3.2 Add fixed API route/outcome/cache observations and extend privacy allowlists without relabelling HTTP requests as MCP tools. Run hostile-canary/privacy tests through hits, misses, malformed input, auth/key errors, DB/model errors and cancellation; verify no content, query/URL/cursor, claims, partition hash, credential or raw exception reaches application/dependency telemetry, and safe counts distinguish avoided embedding/repository calls. Document measurement categories and remaining usage unknowns.
- [ ] 3.3 Add default-off NEWS_API_ENABLED through typed runtime, owning MCP Terraform input/preparation and independent readback; test disabled/no-cache behavior, strict settings, exact enabled inventory and unchanged identity/model/replica/profile/origin expectations with mocked providers. Update the owning API/MCP runbooks, PRD-3 capability/slice assignments and ADRs with the approved cache/cursor choices and separate UI migration/evaluation sequence; validate local links/anchors and ensure no UI/API/evaluation acceptance is claimed prematurely.

## 4. Owning integration and measured publication

- [ ] 4.1 Run focused tests plus bash scripts/check.sh and all package builds on the exact selective publication tree before cloud work; exercise the real local database paging tests and authored HTTP/MCP/browser regression checks, binding source/npm/configuration hashes and outcomes. Verify recursive source exclusions if build inputs changed, and hash-check preservation of unrelated baseline/customization files and historical evaluation receipts; document actual skips/failures separately.
- [ ] 4.2 Build the immutable MCP image, preview only the retained MCP layer and review exact image/API-enablement changes with zero resource additions/deletions or identity/model/profile/other-app changes; obtain fresh owning approval before native azd apply. Verify independent image/flag/identity/host/origin/DB/model readback, public health, unchanged UI/A2A apps and job schedules, and retain prior image/flag state for reviewed rollback.
- [ ] 4.3 Verify deployed authorized HTTP/MCP field/filter/ranking parity, detail/discovery, timestamp ties/cursor behavior, warm-cache auth denial, TTL freshness and measured semantic miss/hit versus metadata-only embedding counts through approved existing delegated workflows. Separately verify actual workload read-only authority and native/current-browser MCP compatibility. Record safe outcomes/counts/provenance and usage estimates only; if regular-browser tooling or authorization cannot provide a required check, report the concrete limitation and leave this task open without exporting credentials, another test-browser sign-in or evaluation replay.
- [ ] 4.4 After actual gates, selectively commit/push only this slice, verify exact-source implementation CI, then publish measured status/runbooks with separate exact-source CI. Verify API/UI/evaluation ledgers remain honest, no unrelated work was staged and unavailable acceptance is not silently waived; archive only after complete acceptance and an explicit request.

## Workflow follow-up

- Propose the separate NewsCatalog HTTP adapter migration after API delivery.
  Keep A2A agent interactions and MCP agent tools; own browser detail/pagination
  UX there rather than silently adding it to this backend slice.
- Resume versioned evaluations only after that migration, preserving all prior
  usage receipts, reservations, failed attempts and original-source associations.
- Do not archive this or prior UI changes while required acceptance remains open.
