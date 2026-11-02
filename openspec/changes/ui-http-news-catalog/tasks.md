# Tasks

HTTP UI deployed early access; authenticated regular-browser acceptance remains open.
The user selected a shareable item page and explicit 20-item Load more with a
200-item displayed-list cap. Semantic search stays bounded to 20 without paging.
API/UI signed-in acceptance and versioned evaluations remain explicitly open.

## 1. HTTP domain, configuration and transport

- [x] 1.1 Extend the typed NewsCatalog boundary with page/detail/read-metadata results and migrate strict browser config/auth selection to newsApiUrl/newsScope while retaining separate A2A audiences. Wire UI_HTTP_API_ENABLED through owning preparation/Terraform/config/CSP/entrypoint/smoke-check/readback, requiring independently verified backend API readiness and retained consent without identity deployment. Test exact new/legacy config-mode shapes, invalid endpoints/audiences/flag combinations, MSAL resource selection and image/config rollback compatibility; document the migration and unchanged permission ownership.
- [x] 1.2 Implement HttpCatalog using the deployed GET news/sources/detail and POST search contracts, preserving exact filters, ordering and per-operation 90-second/1-MiB limits including authentication/body reads. Reuse shared bounded transport without altering A2A streaming. Add actual API-fixture contracts for valid pages/detail/404, cursor/ID/result-mode guards, metadata age, predicate violations, malformed/oversized responses, deadline/cancellation, news-specific input failures and 401/403/429/504 handling; prove zero MCP fallback/automatic retry or endpoint selection from returned data and document the HTTP seam.
- [x] 1.3 Switch production composition to HTTP only and remove unused browser MCP SDK/imports/fixtures through the npm workspace while preserving backend MCP/A2A tests and unrelated lock pins. Verify locked build/type/lint and network assertions that news access makes only intended HTTP calls with the news token, not MCP discovery/tools or agent calls; document removal versus retained agent-to-MCP behavior.

## 2. Bounded browsing and shareable detail interaction

- [x] 2.1 Implement immutable browse-epoch continuation with explicit Load more, 20-item requests, unique append order, no background fetch, distinct append errors/retry and a 200-item cap/restart using applied filters. Add component tests for unsent drafts, all Apply/Search/Reset/Clear/Refresh resets, stale append rejection, overlap/repeated cursors, exact final-page exhaustion, semantic no-paging, near-cap clipping at 200 and zero fetches beyond the cap. Document live/cache freshness limits and distinguish display cap from server exhaustion.
- [x] 2.2 Implement typed `/news/<uuid>` navigation with native history/popstate, stored detail metadata, not-found/error/loading states, Back to news, safe original links and browse/scroll restoration. Adjust only validated same-origin detail restoration through MSAL, keeping the auth bridge/sessionStorage and no automatic question resend. Test direct load/reload, Back/Forward, unknown/malformed routes, exact requested/returned UUIDs, absent items, detail cancellation and late results after navigation/sign-out; document intentional route history versus no persistent content/history store.
- [x] 2.3 Wire card/detail Ask about this to exact item IDs without auto-send; preserve immutable submitted item/filter context across detail/paging and all existing panel/Stop/citation/lofi behavior. Add hostile-content, keyboard/focus, narrow-layout and browser/axe tests, including connected-opener fallback, Back/scroll restoration, cap/restart, sign-out cleanup and independently scrolling long answers. Prove metadata/detail/navigation invoke zero inference/A2A, and document independent questions and stored-summary-only limitations.

## 3. Owning integration and measured publication

- [x] 3.1 Update PRD-3/capability assignments, ADRs and UI/API runbooks with the new transport, detail/page cap and historical MCP-transport supersession, preserving old receipts and unchecked acceptance. Validate links/anchors, command syntax, rollback image/config binding and that no API policy change, full phase acceptance or evaluation execution is claimed.
- [x] 3.2 Run focused HTTP/route/auth/component/static-container/browser checks, then bash scripts/check.sh and package builds on the exact selective publication tree. Record source/npm/configuration hashes and actual outcomes, verify deep-link SPA/security-header behavior and preserved backend MCP contracts, and hash-check unrelated baseline/customization files and historical evaluation receipts before cloud work; do not broaden scope to repair unrelated failures silently.
- [x] 3.3 Build the immutable UI image and preview only the retained UI layer; verify image/config/transport-mode changes with zero new resources, grants or backend/model/schedule changes, and obtain fresh owning approval before native azd apply. Verify exact deployed UI config/CSP/image/origin, retained API readiness/consent and unchanged MCP/A2A images, identities and schedules; retain matching prior image/config mode for reviewed rollback.
- [ ] 3.4 Verify actual regular-browser HTTP-only news/filter/search, Load more/exhaustion/cap/restart, direct detail/Back/Forward and explicit item A2A context, plus available authorization/cache-age/miss-hit evidence and deployed accessibility. Record safe outcomes/counts/provenance and cost estimates versus unknowns, distinguishing authored tests/manual checks/unavailable automation. If required tooling cannot operate in the regular browser, report the limitation, leave missing tasks open and seek a new explicit exception before publication; do not export credentials, request another sign-in or replay evaluations.
- [ ] 3.5 After actual gates or a newly explicit publication exception, selectively commit/push this slice and verify exact-source implementation CI, then separate measured-status CI. Confirm all UI/API ledgers match actual evidence, unavailable acceptance remains unchecked and no unrelated files were staged; do not archive without complete acceptance and an explicit request.

## Workflow follow-up

Focused local evidence (2026-11-02): 51 frontend unit/component/real HTTP API
fixture tests, 20 owning UI-control tests and seven UI Terraform cases passed.
Eight authored browser/axe journeys passed, including detail reload, Back/Forward,
200-item cap/restart, hostile content, citations and independent agent scrolling.
The cap component test also exercises overlapping pages and clipping from 195
to exactly 200 items. Existing MCP/A2A backend behavior is not replaced.

Concurrent browser-container building and unit execution caused fixture/timing
failures; the 200-card test was scoped to its continuation region to avoid
repeated whole-DOM queries, and the complete frontend suite then passed without
build contention. Stored microsecond publication order is preserved directly
rather than re-sorted through millisecond Date parsing; valid read ages above
the cache TTL are accepted for uncached slow reads. No Azure browser/model
acceptance or live inference is claimed by these authored checks.

The complete selective-tree primary gate passed: 301 evaluator tests, 1,624
application tests with 69 conditional database/live skips, 51 frontend tests,
eight authored browser/axe cases, all lint/types/runtime/OpenSpec/Terraform
checks and six Python package builds. The backend SQL code is unchanged in this
slice; its prior real-database evidence remains in the API ledger. A separate
pinned nonroot static-container smoke passed config/CSP/header/asset/log-canary
checks and direct `/news/<uuid>` SPA fallback. Retained backend API readiness was
independently verified before UI rollout preparation. Local source/npm/config
bindings and unchanged unrelated-path hashes are retained privately.

The first native UI preview correctly rejected the retained MCP-shaped
UI_CONFIG_BASE64 while HTTP mode was enabled. Explicit owning prepare-ui-layer
produced the new six-field HTTP config and independently checked backend readiness;
the fresh prepared preview then passed. No app mutation occurred on the failed
preview, and validation was not weakened. The runbook now makes preparation
explicit before previewing a configuration-shape change.

The user explicitly approved the reviewed UI-only rollout and early-access
publication with unavailable regular-browser/API-cache checks remaining open.
This exception does not complete task 3.4 or prior API/UI acceptance, and does
not permit credential export, another test-browser sign-in or archival.

Owning rollout verified (2026-11-02): the approved native UI-only plan updated
one existing app image/runtime/configuration (zero additions/deletions). News
config field names/base path changed, preserving the same news.read scope, tenant,
SPA client, agent settings and actual CSP backend origin. Final deployed source:
`076fc03305ab57f5f6ee91381bc9cc49d38a05d91bc8a9e873626c5f61f05005`.
Independent UI/API readiness, image/configuration/origin/identity/consent readback
passed. Public HTML/config headers, both script chunks and stylesheet matched the
pinned production build byte-for-byte; a direct detail URL served the same SPA
with HTTP 200. Allowed-origin unauthenticated API access returned readable 401.
All six other app/job configuration fingerprints matched their pre-rollout
values; MCP/A2A images and schedules were unchanged.

No live authenticated HTTP/cache/A2A question was dispatched for this verification,
and no credential/browser state was exported. Regular-browser interaction/cache/
deployed accessibility evidence remains open in task 3.4 under the user's explicit
publication exception. No evaluation replay or archive is claimed.

- Return to versioned evaluations after this migration's owning delivery is
  addressed, preserving failed attempts, receipts, budgets and source associations.
- Before future archival, reconcile current browser transport requirements with
  historical active UI deltas without rewriting their acceptance evidence.
- No automatic archival of API/UI changes with open acceptance.
