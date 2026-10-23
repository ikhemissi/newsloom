# Tasks

## 1. Fetch and normalize

- [x] 1.1 Implement protected async feed/robots retrieval using the approved budgets; verify public-only pinned connections, redirect/robots policy, TLS, decompression bounds, timeouts, retries, and exact limit boundaries with deterministic tests, and document the settings alongside the implementation.
- [x] 1.2 Implement RSS/Atom normalization, source selection, publisher-category matching, and `--force` inputs using the existing catalogue types; preserve query strings and fragments in entry URLs/deduplication keys while retaining source/GUID deduplication; verify namespaced/relative/anchored links, distinct releases sharing a page, dates, HTML/plain text, invalid XML/DTD/entities, and a synthetic full-text feed of at least 4 MB, and document the one-RSS/one-Atom local smoke command.

## 2. Durable ingestion storage

- [x] 2.1 Add additive versioned migrations for `feed_sources`, `ingestion_queue`, and `quarantine` with narrowly scoped ingestion grants; verify replay, rollback, constraints, and runtime-role restrictions on disposable PostgreSQL 18/pgvector, preserve applied checksums, and update the database/runbook description.
- [x] 2.2 Implement the typed repository, source validator rules, cross-disposition deduplication, run serialization, and deferred-screening retries; verify real SQL handles repeat/forced/concurrent/interrupted runs, zero parsed entries, 304 responses, atomic deferred-to-accepted transitions, and retained rejection history without content leakage.

## 3. Real content screening

- [x] 3.1 Implement the scanner interface and real managed-identity Decision adapter with validated `noul` responses, bounded rate-limited retries, and distinct accepted/rejected/deferred outcomes; verify clean/hostile/malformed/error/deadline paths with unit tests and keep fake scanners exclusively in tests.
- [x] 3.2 Add labelled calibration and separate validation fixtures plus a bounded real-model evaluation command; verify deterministic scoring/threshold-selection tests and document expected fixture outcomes, model metadata, and safe result reporting without guessing a live threshold.

## 4. Runnable job and deployment

- [x] 4.1 Wire the real ingestion CLI/pipeline, pending/quarantine persistence, and correlated allowlisted structured/OpenTelemetry diagnostics; verify end-to-end fixture persistence, explicit failures, counters, and content/credential canary exclusion, and update the ingestion operations guidance.
- [x] 4.2 Add the real image and minimal azd ingestion layer after migrations, reusing existing build/start/poll helpers and identity; verify focused job/configuration tests, immutable digest and catalogue-sensitive hashing, build-context exclusions, schedule-disabled initial deployment, manual arguments, and propagation of build/migration/execution failures.
- [x] 4.3 Update existing platform probes/tests for this slice's real tables and grants rather than the old zero-table assumption; add fixed read-only ingestion aggregate verification through the retained migration job, verify these queries against actual SQL, and reconcile PRD-1/ADR/capability/runbook references with the approved combined slice and absence of a runtime no-op.

## 5. Local verification at the requested scale

- [x] 5.1 Run focused tests and `bash scripts/check.sh` with the disposable database; retrieve exactly one configured RSS source and one configured Atom source locally and verify normalized entries and repository writes, including independent persistence of distinct anchored Atom releases and duplicate-free replay, clearly distinguishing test scanner decisions from real Azure model acceptance. Do not live-scan the full catalogue locally or in CI; clean up the disposable helper and record actual local outcomes.

## 6. Immediate Azure verification

- [x] 6.1 Refresh actual Decision availability, quota, rate/lifecycle metadata, existing environment/identity references, and incremental cost inputs; review azd previews for additive schema/job changes with no shared replacement, and stop rather than change model, region, SKU, or privileges silently.
- [x] 6.2 Deploy the additive migration and real ingestion job through azd with scheduling disabled; verify real migration replay and existing resource preservation, execute bounded labelled calibration/validation under the ingestion identity, and record the observed threshold/results before enabling live admission.
- [x] 6.3 Start the real ingestion job immediately against the full configured catalogue, without waiting 30 minutes; verify terminal execution status and independently query PostgreSQL through the retained migration job for actual source outcomes, nonzero fetched entries and model-accepted pending rows, quarantine/deferred counts, and screening provenance. Do not substitute synthetic inserts or log-only claims.
- [x] 6.4 Immediately repeat the full-catalogue run with `--force`; read back duplicate/identity aggregates to prove unchanged entries are not duplicated, distinguish newly published entries, verify deferred work remains retriable, and confirm real content-free telemetry with explicit publisher failure outcomes.
- [x] 6.5 Enable the approved `*/30 * * * *` UTC schedule through azd only after manual acceptance; run `azd up` and repeat relevant previews, verify stable shared IDs/retained rows and no unintended changes, and record safe execution/database evidence while keeping enrichment/MCP pending.

## 7. Commit and exact-commit CI

- [x] 7.1 Commit verified implementation only after local and actual Azure checks pass, push, and verify CI on that exact full SHA; record the commit/run, preserve failed or unverified gates as unchecked, and persist acceptance evidence separately without amending a CI-verified commit.

## Workflow follow-up

- Review and archive only after the tracked local, Azure, and exact-commit CI
  gates pass; synchronize the delivered capability specs.
- Continue with enrichment. This slice does not produce summaries, final news
  categories, embeddings, stored `news`, or an MCP endpoint.

## Acceptance evidence

Local, Azure, and exact-implementation-commit CI acceptance passed as of 2026-10-23.
The observations below distinguish local fixtures from actual cloud evidence;
completion evidence is persisted separately without amending the verified implementation.

- `bash scripts/check.sh` passed with disposable PostgreSQL 18/pgvector:
  152 Python tests passed, the opt-in publisher smoke was skipped as intended,
  strict mypy/lint/format/catalogue/identifier/spec checks passed, and all 13
  Terraform tests passed, including the four new ingestion-job contracts.
- The explicit two-source live test retrieved only `microsoft-foundry-devblog`
  (RSS: 10 entries) and `vertex-ai-release-notes` (Atom: 30 entries). Actual
  disposable PostgreSQL writes were verified using fixture scanner verdicts;
  these are not evidence of real-model admission.
- The live test exposed a correctness blocker: the 30 Atom entries have 30
  distinct GUIDs and 30 distinct fragment-anchored links, but stripping URL
  fragments collapses them to one deduplication key. Only one Atom row was stored;
  the other 29 were treated as duplicates. The current test's nonzero-row
  assertion is insufficient to accept this behavior.
- The user approved preserving URL fragments in entry URLs and deduplication keys,
  with source/GUID deduplication unchanged. The design and contract now reflect
  this decision. The fix and regression/live verification passed: the two selected
  feeds stored all 40 distinct entries (10 RSS, 30 Atom); an immediate forced repeat
  found 40 duplicates, staged/accepted zero new entries, and retained 40 pending
  rows. Only fixture scanner decisions were used in this disposable database.
- The final pre-deployment full gate passed with 162 Python tests, one intentionally
  skipped opt-in live test, strict lint/format/mypy/spec checks, and 13 Terraform
  tests. The explicit live test passed separately. The exact task-owned PostgreSQL
  helper was stopped and verified removed.
- Actual Decision metadata was refreshed without modifying resources:
  `Microsoft-Decision-1` version `1`, Preview, `DataZoneStandard`, capacity 60,
  60 requests/minute; regional quota is 60/60 and advertised inference retirement
  remains 2027-02-04. No model/region/SKU/capacity change was made.
- Both immutable images built successfully in the existing ACR. Reviewed azd
  previews show no application/shared changes, an in-place migration image-only
  update, and one new manual ingestion job using the existing ingestion identity.
  Initial scheduling is disabled and the admission threshold is empty.
- Actual OpenTelemetry SDK testing additionally verified correlated spans,
  counters, the duration histogram, queue depth, managed-identity exporter
  configuration, and disabled offline storage. Console canary tests passed.
- Public France Central Consumption rates were refreshed from the Azure Retail
  Prices API: USD 0.000024/vCPU-second and 0.000003/GiB-second active usage.
  The configured 0.25 vCPU/0.5 GiB running for all 900 seconds is about USD 0.00675
  per execution before free grants, startup overhead, model, build, and telemetry
  usage. No new fixed-cost service or model capacity increase is proposed.
- Azure migration deployment updated only the retained migration image. Its first
  execution failed without retrievable container diagnostics; no root cause is
  asserted. One bounded retry succeeded and reported one applied migration.
  A subsequent azd replay succeeded with no infrastructure changes. Independent
  read-only execution verified the three real ingestion tables were initially
  empty. All 12 prior application resource IDs remain; only the ingestion job was
  added. No platform resource was recreated.
- Real calibration execution `ingest-newsloom-dev-w1yms35` succeeded under the
  ingestion identity: eight calibration and eight separate validation cases,
  eight clean/eight hostile overall, zero validation mistakes. The observed
  threshold is `0.4996947340549454` for `Microsoft-Decision-1` version `1`,
  deployment `newsloom-screening`. The threshold-only azd update was reviewed and
  applied while scheduling remained disabled.
- The full-catalogue job was started immediately. A provisional independent
  PostgreSQL read-back while it was still running found all 42 sources, 1,964
  parsed entries, 73 model-screened pending rows, one rejected entry, 1,608 deferred
  entries, and zero duplicate URL/GUID keys. These are progress counts, not the
  terminal acceptance result. Four explicit source outcomes were
  `langchain-blog` / `metr-blog`: `missing_entry_title`;
  `openai-news`: `entry_limit`; `solo-io-blog`: `feed_http_404`.
- The first immediate execution, `ingest-newsloom-dev-i2pobk3`, reached
  `Succeeded` with correlation `152a6bfbd94c46a3baf0d68a4b0e3c75`.
  Its terminal counters report 38 fetched/four failed sources, 1,964 parsed,
  272 category-filtered, ten duplicate, and 1,682 durably staged entries;
  818 were accepted, one rejected, and 863 remain deferred. The runtime reports
  `partial`, not universal publisher success. Actual authenticated AppMetrics
  counters/queue depth and an AppDependencies span agree with these counts;
  the duration metric is 850.016 seconds. The forced full-catalogue execution
  `ingest-newsloom-dev-q426pje` was started immediately after independent SQL
  readback and its `Running` status was verified through ARM.
- Terminal independent readback `migrate-newsloom-dev-3ueos59` returned all 42
  per-source records plus aggregate SQL results: 818 pending, all 818 with the
  configured model/version and scores at or below their threshold, one rejected,
  863 deferred, 818 resolved history rows, and zero duplicate URL/GUID groups.
  Its 38 fetched/four failed source outcomes and 1,964 found entries agree with
  the terminal run. Active identities total 1,682; resolved history is excluded
  from that baseline. No new writer privilege or synthetic cloud row was used.
- The final local gate with disposable PostgreSQL 18.6/pgvector passed:
  163 Python tests, one intentionally skipped opt-in live test, strict lint,
  format, mypy, catalogue/identifier/spec validation, and all 13 Terraform tests.
- Forced execution `ingest-newsloom-dev-q426pje` succeeded with correlation
  `4a6ef2fe2a604f909569213867ab21b1`. It again found 1,964 entries, filtered 272,
  recognized 1,692 duplicate occurrences, and staged zero new entries. There
  were no newly published identities to distinguish in this repeat.
  Readback `migrate-newsloom-dev-jejcnqg` independently confirmed 1,637 screened
  pending, eight rejected, 37 deferred, 1,637 resolved history rows, and zero
  duplicate URL/GUID groups. The 1,682 active identities are unchanged:
  819 former deferrals became accepted and seven became rejected, proving
  backlog retry rather than new duplicate admission. The same four publisher
  failures remain explicit in all 42 per-source SQL records.
- Both runs' actual console output has 44 allowlisted JSON records with no
  unknown fields, raw URLs, or content/credential canaries. First-run
  authenticated Azure metrics and the correlated span were independently queried.
  All five packages also rebuilt successfully. The final disposable PostgreSQL
  helper was stopped and its removal verified.
- Forced-run authenticated AppMetrics independently match its terminal counters,
  including zero staged entries and queue depth 1,637; duration was 849.695 seconds.
  Final bootstrap/application previews are no-ops; migration and ingestion image
  updates are in-place. However, the schedule preview requires replacing only
  `azurerm_container_app_job.ingestion`: AzureRM marks both removal of
  `manual_trigger_config` and addition of `schedule_trigger_config` as
  `forces replacement` (one add/one destroy). No replacement was applied.
  `INGESTION_SCHEDULE_ENABLED` was restored to `false`, and ARM confirmed the real
  job remains `Manual`. Task 6.5 was paused for an explicit decision rather than silently
  replacing the job or introducing another infrastructure provider.
- The user explicitly approved the ingestion-job-only recreation as the leanest
  scheduling path. All 12 original resource IDs and the 13-resource current
  inventory were checked before applying. A fresh preview confirmed only that
  approved replacement; `azd up` was then started in the existing environment.
- `azd up` succeeded in 5 minutes 39 seconds: bootstrap/application had zero
  changes, migrations had one image-only update, and ingestion had only the
  explicitly approved job replacement. ARM confirmed `Schedule`,
  `*/30 * * * *` UTC, the final immutable image, original ingestion identity,
  observed threshold, and 900-second deadline. All 13 resource IDs match the
  pre-operation inventory (the ingestion job reused its name); all 12 original
  shared resources were preserved. Final application/migrations/ingestion
  previews each report no changes.
- The actual next cron execution, `ingest-newsloom-dev-29879130`, succeeded
  with correlation `75c8f5a098454105a4a345a91ed20216`. It fetched 14 sources,
  received 24 not-modified responses, retained the same four explicit failures,
  and accepted all 37 remaining deferred entries without staging new identities.
  Independent readback `migrate-newsloom-dev-jicd0wk` confirmed 1,674 screened
  pending rows, eight rejected, zero deferred, 1,674 resolved history rows,
  and zero duplicate URL/GUID groups. Active identities remain 1,682.
  Actual authenticated metrics agree, including queue depth 1,674 and a
  55.028-second duration; all 44 structured console records remain allowlisted
  and content/credential-free. These are pending enrichment entries, not
  generated summaries, embeddings, published news, or an MCP service.
- Verified implementation commit:
  `eed2169431bf20ee14b261c92ee2effdfae8d41b`, committed/pushed only after local
  and real Azure acceptance. Its exact-SHA
  [CI run](https://github.com/ikhemissi/newsloom/actions/runs/39932983680)
  completed successfully: 163 Python tests passed with only the opt-in live test
  skipped, strict lint/format/mypy/catalogue/identifier/spec checks passed, and
  all 13 Terraform tests passed. The committed image inputs still match the
  source hash used for the deployed immutable images. This evidence and phase
  status update are a separate documentation commit; the verified implementation
  is not amended. The change remains available for review/archive, and enrichment
  is the next delivery slice.

Confirmed scope: ingestion and real content screening together; local live smoke
test limited to one RSS and one Atom source; immediate manual full-catalogue Azure
run followed by independent database read-back and an immediate forced rerun.
