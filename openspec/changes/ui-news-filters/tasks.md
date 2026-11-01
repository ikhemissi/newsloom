# Tasks

No filters implementation, full prior release acceptance or new API/cache
acceptance is claimed. The confirmed order is measured publication, filters,
cached API with detail/cursor contract, UI HTTP adapter, then evaluations.
The user approved proceeding with unavailable Azure checks explicitly open.

## 1. Current delivery closure

- [x] 1.1 Reconcile existing UI/source/deployment/manual evidence and missing automated regular-browser obligations in their own ledgers; record the concrete browser-control limitation and the user's approved publication/filter sequencing exception. Preserve unavailable parity, authorization and accessibility tasks as unchecked, without another sign-in, exported credentials or implied acceptance.
- [x] 1.2 Selectively publish the existing UI implementation and measured status with exact-source CI, safe usage/cost estimates versus unknowns and directly related runbook updates; verify unrelated baseline/prompt/skill work and historical evaluation receipts remain untouched. Archive only actually verified changes when requested.

## 2. Typed catalogue and precise filters

- [x] 2.1 Extend NewsCatalog/domain and its existing MCP adapter with validated list_sources discovery and optional-query metadata filters; verify real-SDK contract tests for exact source/category IDs, query-less no-inference requests, combined search, empty/error results, cancellation and no component SDK imports. Document the unchanged permissions and future HTTP seam.
- [x] 2.2 Implement shared calendar/filter validation for Any time, Today, 7/30 calendar days and inclusive custom dates mapped to UTC from/to; verify leap dates, DST/offset equivalence, exact lower/upper boundaries, one-day ranges and missing/invalid/reversed input without dispatch. Document local-time interpretation.
- [x] 2.3 Add labelled source/category/date draft controls, explicit Apply/Reset and visible applied state; verify component tests that edits dispatch nothing, Apply uses the submitted query, Search commits the complete draft snapshot, Reset preserves query, Clear search preserves filters and valid incompatible pairs return explicit empty news.

## 3. Research context and existing UX

- [x] 3.1 Display applied filter chips beside current-news context and pass the shared validated snapshot through ResearchRequest.filters on explicit A2A Send; verify exact wire fields, optional selected ID, frozen in-flight/answer context, no hidden search-text prompt and no automatic research or replay. Document independent questions and immutable context.
- [x] 3.2 Extend hostile-content/keyboard and headless browser/axe tests for filters, catalogue failure/retry, search/reset, date boundaries and context transitions; verify lofi, independent agent-panel scrolling, sign-out cleanup and original citation safety remain unchanged. Record authored tests separately from live evidence.

## 4. Owning delivery and publication

- [x] 4.1 Update PRD-3/capability assignments, ADRs and the UI runbook with the confirmed delivery/API/cache/UI-migration/evaluation order; verify local links/anchors, source-of-truth ownership and that no unimplemented API/detail/paging/evaluation work is claimed delivered.
- [x] 4.2 Run the primary local gate and package/frontend builds before cloud work; record exact source/npm/configuration bindings and all outcomes, preserving unrelated worktree and environment state.
- [x] 4.2a Apply the explicitly approved recursive build-context exclusions; verify the actual Azure CLI uploader includes zero generated/environment/cache files, preserve a regression guard, and rerun the source-bound local gate. Rebuild and review a fresh UI-only revision, then verify its served CSS/scripts against the pinned production build before publication.
- [x] 4.3 Review/deploy only an approved immutable UI image/revision through retained azd state; verify exact image/configuration/origin/permission and backend/schedule preservation. No new backend route, model, grant, dependency or cache resource is admitted.
- [ ] 4.4 Verify the real regular-browser source/category/date and combined-search journey, exact applied A2A constraints, no metadata-only inference, authorization errors and required deployed accessibility evidence; record safe metadata-only outcomes and usage estimates, leaving unavailable checks explicitly open.
- [x] 4.5 Selectively commit/push this explicitly approved early-access slice after passed local and owning Azure deployment/readback gates, verify exact-source implementation CI and separate measured-status CI; retain unavailable signed-in Azure acceptance in task 4.4 as open under the user's publication exception. Verify tasks/evidence match and do not archive without full acceptance and a request.

## Workflow follow-up

Local acceptance (2026-11-01): the isolated selective tree passed the complete
primary gate: 301 evaluator tests, 1,577 application tests with 67 conditional
skips, 44 frontend unit/component/SDK tests and six authored browser/axe cases.
Types, lint, runtime imports, frontend build, strict OpenSpec validation and every
Terraform stage passed; all six Python packages built. The initial fixture schema
map failed mypy and was replaced with the owning typed MCP INPUTS map, then the
full gate was rerun successfully. Browser checks also caught and corrected
ambiguous dropdown accessible names. No live inference or new sign-in was used.

UI implementation and measured status are published in `9153485` and `14e5956`,
with passing exact-source CI retained in their original ledgers. Their unavailable
Azure acceptance remains open.

Corrected build/deployment evidence (2026-11-01): the actual Azure CLI uploader
excluded every generated/environment/cache file and retained required filter
source after explicit recursive rules were added. The complete selective gate
passed again: 301 evaluator, 1,578 application (67 skipped), 44 frontend and six
authored browser/axe cases, with all checks and six package builds passing.
The first filter image's extra generated CSS was not accepted as build parity;
it was superseded by a freshly reviewed and explicitly approved UI-only revision.

Final deployed source:
`87e78e9ceb6e695e6f5c3fb305df39ad12c192afbb4ad16f24767bab258ac9da`.
Native azd changed only the existing UI image/runtime revision (zero additions/
deletions). Owning identity/image/configuration/origin readback passed. Both script
chunks and the stylesheet matched the pinned production build's filenames and
bytes exactly; public configuration retained its six fields and security headers.
All six backend/job configuration fingerprints matched their pre-rollout values.
The initial cold-start HTTP read timed out; a bounded read with the warmed app
passed. No inference, new sign-in, credential export or evaluation replay was used.
Regular-browser filter acceptance and unavailable automated signed-in Azure checks
remain open in task 4.4. Publication uses the explicit early-access exception;
no archival or full phase acceptance is claimed.

Implementation publication: `9604f3be4eaa4efdd45a0588b1296ca1007dfc53`
passed exact-source CI `41342706269`. The committed build source matches the
corrected deployed source above; all parked code/customization paths and the
historical evaluation usage receipt were hash-verified unchanged. Measured-status
publication `0869a458f7eb57826f9700a0f1c9b45fe2767996` passed separate exact-source
CI `41343382008`. Task 4.4 remains explicitly open; no archive is authorized.

- Propose the cached news API after filters: prefer the current MCP ACA app,
  delegated news.read and workload identity, with authorization before every
  cache hit and no credential/conversation caching. Define detail/cursor and
  cache freshness/invalidation/authorization-partition contracts there.
- Propose the separate UI NewsCatalog HTTP adapter swap while retaining A2A for
  agent interactions and MCP for the agent's tools.
- Resume versioned evaluations only after that migration, preserving all prior
  costs, consumed attempts and failed-run evidence.
