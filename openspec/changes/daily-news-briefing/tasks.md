# Tasks

## 1. Protected persistence and contracts

- [x] 1.1 Add strict shared briefing/run/public-response contracts and additive principal/schema migrations without changing historical checksums or the four-entry foundation manifest. Verify schema rejection, migration rerun/checksum behavior, atomic publication and actual PostgreSQL-role denial of news writes by the writer and briefing writes by MCP; document the grant inventory and persisted-content boundary.
- [x] 1.2 Implement fixed 05:00 UTC slot selection, repeatable-read seven-day snapshot streaming and durable run/advisory-lock ownership. Verify inclusive/exclusive boundaries, future-date exclusion, delayed/bootstrap runs, concurrent ingestion, more than 200 records, duplicate/overlapping triggers and crashed-run reconciliation without regeneration; document the once-only recovery procedure.

## 2. Daily generation and accounting

- [x] 2.1 Add the async briefing workspace package/image with typed model/provider/repository interfaces and bounded hierarchical synthesis over every eligible record. Verify real transport/schema fixtures, retained source membership, citation resolution, 900-1,100 narrative words, sparse/empty cases, hostile data, context/timeout/rate failures and no silent sampling or external tools; document model/prompt provenance and coverage limitations.
- [x] 2.2 Derive a single TL;DR paragraph from the validated summary in the same run and atomically publish the pair. Verify no independent evidence fetch, unsupported/foreign citation rejection, summary-to-TL;DR authored claim oracles, partial-stage failure retaining the previous version and no reader-visible mixed versions.
- [x] 2.3 Persist content-free physical-call/token/latency/uncertain-usage accounting and dated model-cost estimates without a daily spending cap. Verify transient retries, unknown usage, process loss, no-reset/no-replay behavior, deadline/shutdown handling and log/trace/job-output canaries; document model versus hosting/build cost reporting.

## 3. Read API and Agent panel

- [x] 3.1 Add GET /api/v1/briefing using existing delegated news.read, read-only MCP identity, shared four-slot admission and bounded per-caller cache. Verify actual ASGI auth-before-hit denial, cutoff-boundary freshness, no-news/pending/running/stale/failure shapes, no inference on reads, cancellation and unchanged existing API/MCP behavior; document the endpoint and rollout flag prerequisites.
- [x] 3.2 Extend NewsCatalog/HttpCatalog and panel presentation with a visible TL;DR and accessible full-summary collapsible, closed by default. Verify strict response parsing, independent read cancellation, periodic/resumption reads, retry/sign-out/late results, new-version collapse reset, browser-local dates, inert citations and unchanged composer/A2A snapshots; update the UI runbook.
- [x] 3.3 Add authored desktop/mobile browser/axe journeys for panel placement, complete expanded content, keyboard operation, status transitions and continued independent panel scrolling. Verify expand/close/reopen/filter/selection interactions never generate a briefing or submit research, and document the local-versus-Azure evidence boundary.

## 4. Owning Azure resources

- [x] 4.1 Add default-off native azd identity/model/job layers, build/preparation/readback commands and explicit additional-principal migration inputs. Verify Terraform disabled/enabled plans, exact grants, pinned images/model/version, preserved existing deployments and cron 0 5 * * * with one replica and no replica retries; document rollback, scheduling and timeout/rate requirements.
- [x] 4.2 Read current regional model availability/quota/rate/pricing, capture preservation fingerprints and run the primary repository gate, real PostgreSQL-role checks, package builds and strict OpenSpec validation. Verify owning previews contain only declared additive resources/migrations plus matching API/UI updates; record failures honestly without capacity or authority fallback.

## 5. Deployment and acceptance

- [ ] 5.1 Apply the scoped identity/model/migration and manual-disabled job through native azd, deploy the matching API then UI and run one bootstrap daily slot. Verify ready images/configuration, actual model and DB permissions/denials, full-window provenance, summary/TL;DR citation quality, word count, exact public assets and measured model usage/cost; preserve unrelated workloads/data/evaluation ledgers.
- [ ] 5.2 Verify the corrected 05:00 UTC schedule and observe an actual successful scheduled execution separately, under the recorded 2026-11-03 next-slot recovery exception. Verify once-only slot behavior, published fresh/stale states and safe job diagnostics; keep this task open until that execution is observed.
- [ ] 5.3 Verify the real signed-in regular-browser TL;DR/collapsible/status/citation/accessibility journey and API authorization without additional test-browser sign-in or credential export. Record unavailable checks as open, not as authored-fixture or anonymous-Azure substitutes.
- [x] 5.4 Selectively commit/publish implementation and measured status with exact-source CI for each publication, usage/cost observations and explicit open acceptance. Update owning PRD-3 capability/ADR/runbook links; verify parked work, prior source associations and failed evaluation receipts remain unchanged.

## User-requested pause: 2026-11-02

- Paused before creating the briefing job or dispatching generation. The briefing
  schedule and API feature remain disabled; the deployed reader/API have not
  been switched to the new images.
- Native identity/model provisioning succeeded: six additions, zero updates/
  deletes. The additive migration job update and real migration execution
  succeeded. Existing foundation principals/model deployments were preserved.
- An exact staged publication tree passed the primary gate with 303 evaluator
  tests, 1,724 application tests and one live-publisher skip, 73 frontend tests,
  16 browser/axe journeys, strict types/lint/build/OpenSpec/Terraform checks.
  Follow-up snapshot cleanup and build-source binding corrections passed focused
  tests and types; final exact-source CI is not yet recorded.
- The mixed working tree's parked baseline tests still assert historical V2
  manifests. They were left untouched; the publication gate excludes those
  unrelated untracked/modified paths. An additive V3 production-input guard
  preserves V1/V2 pins and existing locked service dependency records.
- Latest worker and MCP images are built under source
  `0085f498c8522f9b7edf2d51a1a7fdd8a81f684fdc2de0c390d5a9ea8349dd08`.
  The final UI build was interrupted/uncertain and its retained environment
  binding is still older. Do not deploy the earlier job preview or stamp image
  metadata manually; finish/reconcile builds and produce a fresh owning preview.
- Retained dev state was reconciled safely from the private validation workspace
  to the original repository after an independent-change check. All 52 parked
  paths remain unchanged. The local disposable PostgreSQL container and owned
  smoke-test images were stopped/removed. Detailed resume evidence is retained
  privately in the session handoff, not committed deployment identifiers.

## Workflow follow-up

- Keep the change active until all required local, CI, real scheduled and Azure
  acceptance is verified; do not synchronize or archive automatically.
- Use observed production volume, quality, latency and cost to decide any future
  spending policy in a separate reviewed change.

## Resumed rollout: 2026-11-03

- Resumed from identical retained dev state and verified all 52 parked paths.
  The fresh manual job was created through native azd and full local gates.
- Live readback exposed Azure's region display name; normalized only case/
  spaces, with wrong-region rejection tests. A production-only startup check
  exposed missing aiohttp, now restored with an isolated async credential
  construction gate. These failures were not hidden or relabelled successful.
- The real writer access probe verified zero prior run/call/artifact rows and
  actual news-write denial. The first model generation then failed closed on a
  foreign citation. It snapshotted 89 eligible records and made one model call:
  6,577 input/940 output tokens, estimated USD 0.010079025, zero unknown usage.
  No summary/TL;DR was published and the failed slot was not retried.
- Following the user's "fix it now and deploy it now" direction, source choices
  are constrained in per-stage model-output schemas; exact schema-token admission
  and existing post-generation reference validation remain. Successful future
  generation, real scheduled execution and signed-in quality acceptance stay
  open. No failed run, usage or existing evaluation receipt is reset.
- The API image/briefing flag update is deployed; independent owning ARM
  readback, anonymous 401, exact-origin preflight 204 and readiness 200 passed.
  A separate generic replica-exec verification failed and is not substituted
  with those checks or claimed successful.
- The newly-created manual job's scheduled-trigger transition requires
  provider-driven replacement of that job only. Its identity/model/schema,
  failed-run ledger and all original workloads remain; this does not authorize
  deleting or recreating any existing foundation resources.
- The citation-fixed worker is deployed on cron `0 5 * * *`; owning scheduled
  configuration/image/identity/grant readback passed. The first successful
  generation and actual scheduled execution remain open, not inferred from
  a configured trigger or local schema tests.
- The matching panel UI image is deployed. Exact served production asset bytes,
  public config/CSP/cache headers, detail SPA fallback, independent owning
  readback and anonymous desktop/mobile shell/axe checks passed. Signed-in
  briefing behavior and semantic quality remain unverified.
- A post-transition writer probe confirmed one run/one call/no artifact and
  actual news-write denial, preserving today's failure. All four unrelated
  original app/jobs and three original models retained their fingerprints.
  Canonical dev state was safely reconciled after conflict detection.
- Combined implementation/measured-status publication `ddfd957` passed
  exact-source CI `41690057706`. Committed Git blobs reproduce the deployed
  worker/UI source exactly:
  `6ea37bee8a0564eeef5d4cd3a7c8e38f2411afc0577c8244fe71072943443c17`.
  Tasks 5.1, 5.2 and 5.3 remain open for successful generation, real scheduled
  acceptance and signed-in qualitative/browser evidence.
