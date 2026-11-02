# Tasks

API deployed as early access; no UI transport migration or full acceptance is claimed.
The user selected a process-local 60-second cache and browse-only cursors;
semantic search is explicitly bounded, not paged.
Existing signed-in UI/filter acceptance and parked evaluation work remain open.

## 1. Typed HTTP and browsing contracts

- [x] 1.1 Add typed versioned request/response/error/cursor models using existing public news/detail/discovery/filter contracts; implement bounded explicit GET parsing and POST JSON validation. Verify limit defaults/exact 1-50 bounds, unknown/duplicate fields, tag normalization, UTC boundary equivalence, blank/oversized queries, invalid UUIDs/JSON/content types and cursor errors without repository/model calls; document route shapes, safe status codes and bounded semantic results in the owning API runbook.
- [x] 1.2 Add the parameterized browse repository operation with publication-descending/UUID-ascending keysets and limit-plus-one lookahead; reuse existing projections/predicates without changing MCP schemas. Run real local PostgreSQL/pgvector tests under the read-only MCP role for tie-heavy multi-page traversal, exact page multiples, all filters, absent detail, empty pages, cursor normalization/restart behavior and concurrent insert/update/delete semantics. Document live traversal limitations; do not count conditional skips as paging verification.

## 2. Authorization, cache and shared execution

- [x] 2.1 Implement explicit HTTP authorization with the configured shared trusted-key verifier and same delegated news.read requirement; distinguish invalid tokens, missing scope and trusted-key unavailability without weakening MCP verification. Test actual ASGI requests with signed authored tokens for wrong audience/tenant/issuer/key/lifetime/algorithm, app-only/wrong-scope access, duplicate authorization and same-caller renewal; verify a spy cache is never consulted on denial and document caller partition/policy-version semantics without retaining claims or tokens.
- [x] 2.2 Implement the bounded process-local immutable-success cache: absolute read-start TTL 60 seconds, 128 entries, 8 MiB payload total, 512 KiB per entry, LRU/expiry eviction and normalized caller/operation/model/request keys. Test exact just-before/at-expiry boundaries with a fake clock, non-sliding hits, two-caller/client/scope/policy separation, equivalent normalized inputs, byte/entry thresholds, oversized-entry bypass, successful empty results, restart isolation and no caching of errors/404/cancelled/late fills/vectors. Document freshness, upstream ingestion lag and independent-worker behavior.
- [x] 2.3 Wire news/detail/sources/search handlers through existing typed services and one shared four-slot MCP/API admission boundary, preserving readiness limits and existing tool behavior. Verify hits perform zero repository/embedding work, semantic misses use the existing bounded vector/ranking path, metadata misses perform zero inference, mixed MCP/API concurrency cannot exceed four, admission/deadline/response-size failures are typed and disconnect/cancellation releases resources with no partial cache insert. Document request/response limits and no stale-on-error or automatic fallback/replay.

## 3. Explicit hosting and privacy boundaries

- [x] 3.1 Make API host/origin/method policy route-aware while preserving existing MCP behavior; test API GET versus POST, unknown/disabled routes, no-Origin native requests, duplicate/unapproved origins, wrong hosts, exact preflight headers/Vary/max-age and readable allowed-origin error responses. Verify preflight consumes no auth/cache/repository/model work and that modern MCP discovery/tool/cancellation browser contracts and native clients still pass; document the shared origin without broadening credentials/methods.
- [x] 3.2 Add fixed API route/outcome/cache observations and extend privacy allowlists without relabelling HTTP requests as MCP tools. Run hostile-canary/privacy tests through hits, misses, malformed input, auth/key errors, DB/model errors and cancellation; verify no content, query/URL/cursor, claims, partition hash, credential or raw exception reaches application/dependency telemetry, and safe counts distinguish avoided embedding/repository calls. Document measurement categories and remaining usage unknowns.
- [x] 3.3 Add default-off NEWS_API_ENABLED through typed runtime, owning MCP Terraform input/preparation and independent readback; test disabled/no-cache behavior, strict settings, exact enabled inventory and unchanged identity/model/replica/profile/origin expectations with mocked providers. Update the owning API/MCP runbooks, PRD-3 capability/slice assignments and ADRs with the approved cache/cursor choices and separate UI migration/evaluation sequence; validate local links/anchors and ensure no UI/API/evaluation acceptance is claimed prematurely.

## 4. Owning integration and measured publication

- [x] 4.1 Run focused tests plus bash scripts/check.sh and all package builds on the exact selective publication tree before cloud work; exercise the real local database paging tests and authored HTTP/MCP/browser regression checks, binding source/npm/configuration hashes and outcomes. Verify recursive source exclusions if build inputs changed, and hash-check preservation of unrelated baseline/customization files and historical evaluation receipts; document actual skips/failures separately.
- [x] 4.2 Build the immutable MCP image, preview only the retained MCP layer and review exact image/API-enablement changes with zero resource additions/deletions or identity/model/profile/other-app changes; obtain fresh owning approval before native azd apply. Verify independent image/flag/identity/host/origin/DB/model readback, public health, unchanged UI/A2A apps and job schedules, and retain prior image/flag state for reviewed rollback.
- [ ] 4.3 Verify deployed authorized HTTP/MCP field/filter/ranking parity, detail/discovery, timestamp ties/cursor behavior, warm-cache auth denial, TTL freshness and measured semantic miss/hit versus metadata-only embedding counts through approved existing delegated workflows. Separately verify actual workload read-only authority and native/current-browser MCP compatibility. Record safe outcomes/counts/provenance and usage estimates only; if regular-browser tooling or authorization cannot provide a required check, report the concrete limitation and leave this task open without exporting credentials, another test-browser sign-in or evaluation replay.
- [x] 4.4 After passed local and owning Azure rollout/readback gates, selectively commit/push only this slice, verify exact-source implementation CI, then publish measured status/runbooks with separate exact-source CI. Use the user's explicit 2026-11-02 early-access publication exception while authenticated live API/cache checks remain open in 4.3; verify API/UI/evaluation ledgers stay honest and unrelated work is unstaged. Do not archive without complete acceptance and an explicit request.

## Workflow follow-up

Local focused evidence (2026-11-02): 83 contract/cache/actual-ASGI/auth/privacy/
control and existing MCP regression tests passed, with strict mypy and lint.
Seven real local PG18/pgvector tests passed under the read-only MCP role, including
tie-heavy keysets, exact page multiples, combined filters and concurrent
publication updates/deletion/reinsertion. All seven mocked MCP Terraform cases
passed, including default-off/opt-in API enablement and preserved authority/profile.
These are authored/local checks, not Azure sign-in, model-cost or live cache proof.

The user explicitly approved early-access rollout/publication after a reviewed
MCP-only preview while unavailable authenticated live checks remain open. No
regular-browser credential export or separate sign-in is authorized. The first
full gate passed 301 evaluator tests and 1,689 application tests (one live-
publisher skip), then hit an existing frontend option-discovery timing failure.
Its five-test component file passed immediately in isolation without changes.
Final API amendments also passed 27 HTTP cases, including extreme timestamp
overflow rejection; the complete selective gate will be rerun before cloud work.

Final selective-tree gate passed: 301 evaluator tests, 1,690 application tests
with real local PG18/pgvector enabled (one intentionally excluded live-publisher
test), 44 frontend tests, six authored browser/axe cases, all runtime/type/lint/
OpenSpec/Terraform checks and six package builds. The earlier frontend timing
failure did not recur; no unrelated frontend code or thresholds were changed.
Source/configuration/npm bindings and preserved unrelated-path hashes are retained
in private metadata receipts. No live model or evaluation run was invoked.

Owning Azure rollout (2026-11-02): the explicitly approved native MCP-only plan
changed the immutable image and added NEWS_API_ENABLED=true, with zero additions/
deletions or identity/model/origin/profile changes. Final deployed source:
`a5588eaebe31132919b22e4b3f2b9d044cd85e66dbfa3b4f5d2087e5e6568ecd`.
The first immediate independent readback reported a mismatch; follow-up read-only
ARM comparisons found matching predicates and a repeated owning readback passed.
No deployment mutation was replayed; the initial mismatching predicate was not
captured, so its cause is not asserted.

Live API anonymous/invalid-token rejection returned 401, approved-origin search
preflight 204, unapproved-origin rejection 403, unsupported method 405 and
unknown route 404, with live/readiness health 200. Exact owning image/flag/
identity/model/origin/configuration readback passed. Six other app/job
configuration fingerprints matched their pre-rollout values, preserving UI and
agent images and schedules. The existing authenticated native MCP connection
successfully returned discovery (40 represented sources, 11 categories) without
new sign-in or inference. These checks do not prove authenticated HTTP/cache
parity, warm-cache authorization or live semantic miss/hit usage; task 4.3 remains
open under the explicit publication exception. No API verification embedding/
generation request, browser credential export or evaluation replay was dispatched.
Build/hosting costs remain separate and unmeasured.

Implementation publication: commit `3c798ae8b5fac8c5323d15ea7357fff72f96c0f4`
passed exact-source CI `41449774908`. Its build source matches the deployed MCP
revision. All 52 parked baseline/customization paths and the historical evaluation
usage receipt were hash-verified unchanged. The disposable local database/check
tree were removed. Measured-status commit
`bfe535483d9a985429f6b8e2c7a8f4ffd1e05cbb` passed separate exact-source CI
`41450605684`. Task 4.3 remains open; no archive or full acceptance is claimed.

- Propose the separate NewsCatalog HTTP adapter migration after API delivery.
  Keep A2A agent interactions and MCP agent tools; own browser detail/pagination
  UX there rather than silently adding it to this backend slice.
- Resume versioned evaluations only after that migration, preserving all prior
  usage receipts, reservations, failed attempts and original-source associations.
- Do not archive this or prior UI changes while required acceptance remains open.
