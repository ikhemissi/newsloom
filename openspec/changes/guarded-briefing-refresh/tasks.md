# Tasks

## 1. Immutable revision persistence

- [x] 1.1 Add the next additive migration for version-bound append-only revision audits, preserving all prior migration checksums and failed-attempt constraints. Verify migration repeatability, prior artifact/run metadata retention, request uniqueness and real writer/MCP/admin permissions; document the new database-only access in the briefing runbook.
- [x] 1.2 Implement serialized revision admission and publication guards while retaining ordinary daily and failed-retry behavior. Verify stale/missing versions, duplicate requests, concurrent owners, unknown/pending usage, current cutoff, next-cutoff overlap, known failed-revision lineage and cumulative ordinal/accounting preservation with real-role database tests.

## 2. Typed operator execution

- [x] 2.1 Add typed `revise-published` arguments and metadata-only version inspection; reuse the existing generation pipeline and job-start override. Verify required UUID/reason parsing, invalid-input diagnostics, stable request replay, existing `run`/`retry-failed` denial behavior and no sensitive output; document exact operator commands and explicit-dispatch prerequisites.
- [x] 2.2 Wire revision orchestration, base-version compare-and-publish and explicit failure handling. Verify that summary/TL;DR failure, cancellation, stale publication or unknown usage leaves the previous artifact readable with all new intents/costs retained; verify a successful architect artifact changes version atomically without moving its window. Document rollback and fully observed failed-revision recovery without automatic replay.

## 3. Contract and local integration

- [x] 3.1 Reconcile P3-C08, phase sequencing and directly related active briefing guidance with this separately authorized manual revision. Verify links/commands and preserve prior measured evidence, original successful/failed attempts, actual daily-scheduler acceptance and unavailable signed-in quality checks.
- [ ] 3.2 Run focused worker/Core/API/database regressions, strict lint/types, package builds, the exact scoped primary gate and strict OpenSpec validation. Verify old/new/no-material/empty read behavior, 60-second cache visibility, unchanged read-only browser/research semantics and untouched parked files.

## 4. Deploy and refresh the requested publication

- [ ] 4.1 Prepare fresh immutable migration/worker images from the verified tree, review owning native azd previews and deploy the additive migration before the worker in retained dev. Verify actual schema/grants/checksums and worker/model/schedule/configuration readback; compare preserved workloads, identities, models, consent and original call/history rows.
- [ ] 4.2 Inspect and persist the actual base version and one request ID, execute the user-authorized revision, and observe its terminal result without replaying uncertain generation. Verify a new architect-policy publication with both summary and TL;DR, unchanged cutoff/window, at most 1,000 combined words, safe citations and preserved prior payload/history plus incremental/cumulative usage. Confirm protected-read visibility within the existing cache bound; leave real user semantic review open if unavailable.
- [ ] 4.3 Record actual local/Azure/generation evidence and selectively commit/push the slice with exact-source passing CI, preserving parked work and real image/source associations. Verify that a manual editorial publication is not recorded as actual scheduled execution or completed signed-in qualitative acceptance.

## Workflow follow-up

- Do not dispatch generation until implementation, migration and owning worker
  readback have passed. Do not delete the successful slot, repurpose its failed
  retry or invent a new cutoff to force an immediate report.
- Keep original daily/architect acceptance ledgers open where real scheduling,
  user semantic review or permitted regular-browser checks remain unverified.
- Archive only after this change's required acceptance is genuinely verified.
