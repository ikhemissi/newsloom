# Tasks

Artifact validation is not runtime acceptance. Follow the [design](design.md) and
[ingestion requirements](specs/feed-ingestion/spec.md).

## 1. Baseline and item isolation

- [x] 1.1 Sync the already-verified `feed-ingestion` baseline specs through the
  normal workflow without archiving it or rewriting its evidence; verify its
  delivered capabilities are available as main specs before delta reconciliation.
- [x] 1.2 Flush the HTML parser at EOF and isolate expected item normalization
  failures; verify ampersands in titles/bodies, valid siblings around malformed
  RSS/Atom items, dates/URLs, existing fragment identities and unchanged document
  protections in `tests/test_ingestion_feeds.py`.

## 2. Protected article recovery

- [x] 2.1 Implement feed-field preservation, JSON-LD/OpenGraph extraction and
  bounded visible article-text fallback from one protected direct response; add
  offline fixtures proving each path, mixed-field precedence, one GET, no redirect
  following or remote/asset navigation, robots/DNS enforcement and exact limits.
- [x] 2.2 Wire the same recovery into the job and two-source `fetch` command,
  skipping filtered/durable duplicates and preserving valid title-only behavior;
  test transient versus permanent failures and content-free output. Update
  P1-C02 guidance and the ingestion runbook. Adapt the opt-in live test to one
  LangChain RSS source and one Atom source, with accounting that distinguishes
  malformed/retryable work rather than assuming every raw node was accepted.

## 3. Durable counters and retry semantics

- [x] 3.1 Extend `feed_sources.counts` with the documented latest-run outcome,
  acquisition and recovery counters; update decision counts transactionally and
  preserve validators for unfinished recovery. Database tests must cover mixed
  malformed items, all-malformed bodies, replay, 304/backlog screening, rollback,
  correct per-source attribution and duplicates excluded from new-work counts.
- [x] 3.2 Extend allowlisted diagnostics and existing read-only Azure readback
  with per-feed counters; verify CLI/telemetry/readback tests and content canaries.
  Document latest-run versus lifetime semantics and backlog versus acquisition
  counts in the ingestion runbook; no new table or inference grant is introduced.

## 4. Catalogue retirement

- [x] 4.1 Remove only `solo-io-blog`, retain `agentgateway-blog` once and preserve
  all other definitions/allowlists; update catalogue tests and current source-count
  documentation. Verify `uv run --locked newsloom-validate-feeds config/feeds.json`
  reports 41 unique active sources and tests prove no historical database deletes.

## 5. Integrated local and immediate Azure acceptance

- [x] 5.1 Run focused ingestion/catalogue regressions, the complete
  `bash scripts/check.sh` gate and `uv build --all-packages`. Run the explicit
  one-RSS/one-Atom live database test with fixture verdicts; independently verify
  persistence and forced-replay deduplication, and record counts without claiming
  fixture verdicts establish real-model acceptance. Do not fetch all feeds locally.
- [x] 5.2 Preview and deploy the rebuilt immutable image through the existing azd
  environment after local checks; verify no shared-resource replacement, schedule
  switch, identity/model permission change or state recreation. Record the actual
  image/deployment result and stop for approval if preview introduces such changes.
- [x] 5.3 Start the real full-catalogue Azure job immediately and independently
  read PostgreSQL. Verify actual per-source outcomes/counters, recovery of the
  LangChain item if still published, the METR normalizer regression, screened queue
  writes and 41 active catalogue sources. Record actual publisher unavailability,
  including the unchanged OpenAI item-cap failure, rather than inventing success.
- [x] 5.4 Immediately force a repeat and read PostgreSQL again: verify no duplicate
  identities, no new-work counts for unchanged durable entries, retained source
  history and the original eight quarantined rows unchanged. Check authenticated
  telemetry and resource/schedule preservation; record only content-free evidence.

## 6. Persistent delivery evidence

- [ ] 6.1 After local and Azure acceptance, commit and push the verified changes,
  verify CI for the exact implementation SHA and persist observed acceptance
  evidence without amending that verified commit. Verify the final pushed HEAD's
  CI too; leave any unverified acceptance task unchecked.

## Workflow follow-up

- Present the completed evidence for review. Archive this follow-up only after
  its local, Azure and CI acceptance requirements are actually satisfied.

## Acceptance evidence

- Baseline ingestion and screening contracts were synced without archival or
  changes to their original acceptance evidence; strict main-spec validation passed.
- The final primary local gate passed 199 Python tests with the opt-in live test skipped,
  strict mypy, Ruff, catalogue/identifier/spec checks and all 13 Terraform tests.
  All five workspace packages built successfully.
- Explicit local live acceptance used only LangChain RSS and Vertex Atom:
  100 and 30 items persisted with fixture scanner verdicts. LangChain used 99
  feed-item paths and one article-body recovery from one direct response.
  Immediate forced replay counted 130 duplicates, zero new staging and zero
  article recovery attempts. Fixture verdicts are not real-model acceptance.
- Image-only migration/ingestion previews each reported zero additions, one
  in-place update and zero deletions; application preview was unchanged. Both
  immutable job images were verified against source hash
  `c8bae6e4904187eee7af9d5fb5a273780bd712d3929ca431a4a196fca175b344`.
  No migration schema or inference permission changed.
- The first `azd up` applied the image updates, then caught a test-file formatting
  failure in predeploy. After fixing formatting, the full local gate passed.
  A no-change retry stalled in Terraform apply on the migrations layer and was
  stopped; final migration/ingestion previews both reported no changes.
  `azd deploy --no-prompt` then passed its full predeploy gate and completed.
  No state or resource was recreated.
- Immediate real-model execution `ingest-newsloom-dev-9qikr3m`, correlation
  `72d87e7e247e4c97ad8582a30137b312`, succeeded in 259 seconds: 40 sources OK and
  one explicit OpenAI `entry_limit` failure; 759 found, 272 filtered, 287
  duplicates and 200 staged. Actual outcomes were 185 accepted, 15 security
  rejections and zero deferrals or malformed drops.
- LangChain stored/screened 100 items, using 99 feed-item paths and one
  article-body recovery; all were accepted. METR stored/screened 100, using 96
  feed-item, three metadata and one article-body path; 85 accepted and 15
  quarantined by the unchanged scanner. No summary generation was introduced.
- Independent read-only snapshot `migrate-newsloom-dev-b4rjurs` and standard
  readback `migrate-newsloom-dev-lsjdcr2` observed 1,964 screened pending, 23
  rejected, zero deferred and zero duplicate URL/GUID groups. The original eight
  quarantine rows had the same complete-row fingerprint as before rollout.
  The standard readback followed the successful preserved 14:30 UTC scheduled
  run, so its latest-run counters correctly reflected that later correlation
  rather than retaining the earlier manual run's acquisition counts.
- Authenticated telemetry for the first manual correlation included actual
  outcome/duration/queue metrics and one ingestion span. Console queries found
  all 41 feed summaries and zero content/credential canary leaks. All 13 resource
  IDs and the complete ingestion job configuration/identity were unchanged;
  `*/30 * * * *` UTC remained enabled.
- Immediate forced execution `ingest-newsloom-dev-9oobt6p`, correlation
  `e496de33a1e847c8908e2561b12e95c3`, succeeded in 57 seconds: 2,165 found, 272
  filtered, 1,893 duplicates, zero staged, zero screening decisions and zero
  recovery attempts. The sole active-source failure remained OpenAI's item cap.
- Forced read-only snapshot `migrate-newsloom-dev-znphg8w` and standard readback
  `migrate-newsloom-dev-s28kuoz` confirmed unchanged 1,964 screened pending,
  23 rejected and zero deferred/duplicate URL/duplicate GUID groups. All 41 active
  rows carried the forced correlation and zero new-work decision/path counts.
  The original eight complete quarantine rows and retired Solo.io history were
  unchanged. The 42nd database source row is history, not an active feed.
- Forced-run metrics and its ingestion span were present. After normal log
  ingestion delay, Log Analytics contained all 41 forced feed summaries and zero
  content/credential canary leaks.
