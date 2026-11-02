# Tasks

## 1. Protected persistence and contracts

- [ ] 1.1 Add strict shared briefing/run/public-response contracts and additive principal/schema migrations without changing historical checksums or the four-entry foundation manifest. Verify schema rejection, migration rerun/checksum behavior, atomic publication and actual PostgreSQL-role denial of news writes by the writer and briefing writes by MCP; document the grant inventory and persisted-content boundary.
- [ ] 1.2 Implement fixed 05:00 UTC slot selection, repeatable-read seven-day snapshot streaming and durable run/advisory-lock ownership. Verify inclusive/exclusive boundaries, future-date exclusion, delayed/bootstrap runs, concurrent ingestion, more than 200 records, duplicate/overlapping triggers and crashed-run reconciliation without regeneration; document the once-only recovery procedure.

## 2. Daily generation and accounting

- [ ] 2.1 Add the async briefing workspace package/image with typed model/provider/repository interfaces and bounded hierarchical synthesis over every eligible record. Verify real transport/schema fixtures, retained source membership, citation resolution, 900-1,100 narrative words, sparse/empty cases, hostile data, context/timeout/rate failures and no silent sampling or external tools; document model/prompt provenance and coverage limitations.
- [ ] 2.2 Derive a single TL;DR paragraph from the validated summary in the same run and atomically publish the pair. Verify no independent evidence fetch, unsupported/foreign citation rejection, summary-to-TL;DR authored claim oracles, partial-stage failure retaining the previous version and no reader-visible mixed versions.
- [ ] 2.3 Persist content-free physical-call/token/latency/uncertain-usage accounting and dated model-cost estimates without a daily spending cap. Verify transient retries, unknown usage, process loss, no-reset/no-replay behavior, deadline/shutdown handling and log/trace/job-output canaries; document model versus hosting/build cost reporting.

## 3. Read API and Agent panel

- [ ] 3.1 Add GET /api/v1/briefing using existing delegated news.read, read-only MCP identity, shared four-slot admission and bounded per-caller cache. Verify actual ASGI auth-before-hit denial, cutoff-boundary freshness, no-news/pending/running/stale/failure shapes, no inference on reads, cancellation and unchanged existing API/MCP behavior; document the endpoint and rollout flag prerequisites.
- [ ] 3.2 Extend NewsCatalog/HttpCatalog and panel presentation with a visible TL;DR and accessible full-summary collapsible, closed by default. Verify strict response parsing, independent read cancellation, periodic/resumption reads, retry/sign-out/late results, new-version collapse reset, browser-local dates, inert citations and unchanged composer/A2A snapshots; update the UI runbook.
- [ ] 3.3 Add authored desktop/mobile browser/axe journeys for panel placement, complete expanded content, keyboard operation, status transitions and continued independent panel scrolling. Verify expand/close/reopen/filter/selection interactions never generate a briefing or submit research, and document the local-versus-Azure evidence boundary.

## 4. Owning Azure resources

- [ ] 4.1 Add default-off native azd identity/model/job layers, build/preparation/readback commands and explicit additional-principal migration inputs. Verify Terraform disabled/enabled plans, exact grants, pinned images/model/version, preserved existing deployments and cron 0 5 * * * with one replica and no replica retries; document rollback, scheduling and timeout/rate requirements.
- [ ] 4.2 Read current regional model availability/quota/rate/pricing, capture preservation fingerprints and run the primary repository gate, real PostgreSQL-role checks, package builds and strict OpenSpec validation. Verify owning previews contain only declared additive resources/migrations plus matching API/UI updates; record failures honestly without capacity or authority fallback.

## 5. Deployment and acceptance

- [ ] 5.1 Apply the scoped identity/model/migration and manual-disabled job through native azd, deploy the matching API then UI and run one bootstrap daily slot. Verify ready images/configuration, actual model and DB permissions/denials, full-window provenance, summary/TL;DR citation quality, word count, exact public assets and measured model usage/cost; preserve unrelated workloads/data/evaluation ledgers.
- [ ] 5.2 Enable 05:00 UTC scheduling only after bootstrap verification and observe an actual scheduled execution separately. Verify once-only slot behavior, published fresh/stale states and safe job diagnostics; leave this task open if only a manual run has been observed.
- [ ] 5.3 Verify the real signed-in regular-browser TL;DR/collapsible/status/citation/accessibility journey and API authorization without additional test-browser sign-in or credential export. Record unavailable checks as open, not as authored-fixture or anonymous-Azure substitutes.
- [ ] 5.4 Selectively commit/publish implementation and measured status with exact-source CI for each publication, usage/cost observations and explicit open acceptance. Update owning PRD-3 capability/ADR/runbook links; verify parked work, prior source associations and failed evaluation receipts remain unchanged.

## Workflow follow-up

- Keep the change active until all required local, CI, real scheduled and Azure
  acceptance is verified; do not synchronize or archive automatically.
- Use observed production volume, quality, latency and cost to decide any future
  spending policy in a separate reviewed change.
