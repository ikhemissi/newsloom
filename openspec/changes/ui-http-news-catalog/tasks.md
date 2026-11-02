# Tasks

Planning only; no HTTP UI, detail/paging rollout or new live acceptance is claimed.
The user selected a shareable item page and explicit 20-item Load more with a
200-item displayed-list cap. Semantic search stays bounded to 20 without paging.
API/UI signed-in acceptance and versioned evaluations remain explicitly open.

## 1. HTTP domain, configuration and transport

- [ ] 1.1 Extend the typed NewsCatalog boundary with page/detail/read-metadata results and migrate strict browser config/auth selection to newsApiUrl/newsScope while retaining separate A2A audiences. Wire UI_HTTP_API_ENABLED through owning preparation/Terraform/config/CSP/entrypoint/smoke-check/readback, requiring independently verified backend API readiness and retained consent without identity deployment. Test exact new/legacy config-mode shapes, invalid endpoints/audiences/flag combinations, MSAL resource selection and image/config rollback compatibility; document the migration and unchanged permission ownership.
- [ ] 1.2 Implement HttpCatalog using the deployed GET news/sources/detail and POST search contracts, preserving exact filters, ordering and per-operation 90-second/1-MiB limits including authentication/body reads. Reuse shared bounded transport without altering A2A streaming. Add actual API-fixture contracts for valid pages/detail/404, cursor/ID/result-mode guards, metadata age, predicate violations, malformed/oversized responses, deadline/cancellation, news-specific input failures and 401/403/429/504 handling; prove zero MCP fallback/automatic retry or endpoint selection from returned data and document the HTTP seam.
- [ ] 1.3 Switch production composition to HTTP only and remove unused browser MCP SDK/imports/fixtures through the npm workspace while preserving backend MCP/A2A tests and unrelated lock pins. Verify locked build/type/lint and network assertions that news access makes only intended HTTP calls with the news token, not MCP discovery/tools or agent calls; document removal versus retained agent-to-MCP behavior.

## 2. Bounded browsing and shareable detail interaction

- [ ] 2.1 Implement immutable browse-epoch continuation with explicit Load more, 20-item requests, unique append order, no background fetch, distinct append errors/retry and a 200-item cap/restart using applied filters. Add component tests for unsent drafts, all Apply/Search/Reset/Clear/Refresh resets, stale append rejection, overlap/repeated cursors, exact final-page exhaustion, semantic no-paging, near-cap clipping at 200 and zero fetches beyond the cap. Document live/cache freshness limits and distinguish display cap from server exhaustion.
- [ ] 2.2 Implement typed `/news/<uuid>` navigation with native history/popstate, stored detail metadata, not-found/error/loading states, Back to news, safe original links and browse/scroll restoration. Adjust only validated same-origin detail restoration through MSAL, keeping the auth bridge/sessionStorage and no automatic question resend. Test direct load/reload, Back/Forward, unknown/malformed routes, exact requested/returned UUIDs, absent items, detail cancellation and late results after navigation/sign-out; document intentional route history versus no persistent content/history store.
- [ ] 2.3 Wire card/detail Ask about this to exact item IDs without auto-send; preserve immutable submitted item/filter context across detail/paging and all existing panel/Stop/citation/lofi behavior. Add hostile-content, keyboard/focus, narrow-layout and browser/axe tests, including connected-opener fallback, Back/scroll restoration, cap/restart, sign-out cleanup and independently scrolling long answers. Prove metadata/detail/navigation invoke zero inference/A2A, and document independent questions and stored-summary-only limitations.

## 3. Owning integration and measured publication

- [ ] 3.1 Update PRD-3/capability assignments, ADRs and UI/API runbooks with the new transport, detail/page cap and historical MCP-transport supersession, preserving old receipts and unchecked acceptance. Validate links/anchors, command syntax, rollback image/config binding and that no API policy change, full phase acceptance or evaluation execution is claimed.
- [ ] 3.2 Run focused HTTP/route/auth/component/static-container/browser checks, then bash scripts/check.sh and package builds on the exact selective publication tree. Record source/npm/configuration hashes and actual outcomes, verify deep-link SPA/security-header behavior and preserved backend MCP contracts, and hash-check unrelated baseline/customization files and historical evaluation receipts before cloud work; do not broaden scope to repair unrelated failures silently.
- [ ] 3.3 Build the immutable UI image and preview only the retained UI layer; verify image/config/transport-mode changes with zero new resources, grants or backend/model/schedule changes, and obtain fresh owning approval before native azd apply. Verify exact deployed UI config/CSP/image/origin, retained API readiness/consent and unchanged MCP/A2A images, identities and schedules; retain matching prior image/config mode for reviewed rollback.
- [ ] 3.4 Verify actual regular-browser HTTP-only news/filter/search, Load more/exhaustion/cap/restart, direct detail/Back/Forward and explicit item A2A context, plus available authorization/cache-age/miss-hit evidence and deployed accessibility. Record safe outcomes/counts/provenance and cost estimates versus unknowns, distinguishing authored tests/manual checks/unavailable automation. If required tooling cannot operate in the regular browser, report the limitation, leave missing tasks open and seek a new explicit exception before publication; do not export credentials, request another sign-in or replay evaluations.
- [ ] 3.5 After actual gates or a newly explicit publication exception, selectively commit/push this slice and verify exact-source implementation CI, then separate measured-status CI. Confirm all UI/API ledgers match actual evidence, unavailable acceptance remains unchecked and no unrelated files were staged; do not archive without complete acceptance and an explicit request.

## Workflow follow-up

- Return to versioned evaluations after this migration's owning delivery is
  addressed, preserving failed attempts, receipts, budgets and source associations.
- Before future archival, reconcile current browser transport requirements with
  historical active UI deltas without rewriting their acceptance evidence.
- No automatic archival of API/UI changes with open acceptance.
