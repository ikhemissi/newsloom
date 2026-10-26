# Tasks

Archived on 2026-10-26 after user approval and verified acceptance. The
[delivered enrichment contract](../../../specs/news-enrichment/spec.md) is
published in the main specs. Evidence below retains its original chronology;
archival does not rebuild or redeploy a runtime image.

Only checked tasks are verified. Follow [the design](design.md),
[the enrichment contract](specs/news-enrichment/spec.md), and
[the ingestion visibility delta](specs/feed-ingestion/spec.md).
Complete local checks before cloud deployment; complete real quality and smoke
verification before enabling the schedule.

## 1. Shared contracts and additive database changes

- [x] 1.1 Share the normalized entry contract through core with compatible ingestion re-exports; add the 11-category catalogue and strict enrichment output types. Verify unchanged ingestion serialization, exact category IDs/labels including Governance, 2-3 sentence units and the 100-word boundary, 3-5 unique lowercase tags, and invalid/extra-field rejection with focused tests. Document the category boundaries in the owning capability guidance, linking to the catalogue rather than duplicating it.
- [x] 1.2 Add and register the new versioned enrichment migration for queue states/attempts/leases and the `news` table, uniqueness, vector/index constraints and narrow grants. Verify migration replay, preserved existing rows/checksums, valid state transitions, 1536-dimensional storage and denied unowned operations against disposable PostgreSQL 18/pgvector. Document schema ownership and states in the enrichment runbook.
- [x] 1.3 Make ingestion and platform operator pending-depth queries state-aware while retaining completed identities for deduplication; add distinct enrichment state/news aggregates. Verify counts with pending/processing/failed/completed/dead-letter fixtures and ingestion reruns over completed items; update the ingestion/platform runbooks to distinguish pending work from retained history.

## 2. Durable worker and model pipeline

- [x] 2.1 Implement typed queue claims, finite retries, expired-lease recovery and fenced success/failure transactions. Verify concurrent claims, stale tokens, expiry during completion, rollback between news insertion/completion, cancellation and exhaustion on the last allowed claim, without holding transactions during model calls. Document recovery, retry and dead-letter behavior with these tests.
- [x] 2.2 Implement the Entra-authenticated generation and embedding adapters using the existing deployments and narrow provider interfaces. Verify strict complete-response parsing, source-data separation, no tools/shared history, bounded HTTP retries/deadlines/Retry-After, model refusals, narrowly typed service jailbreak-filter blocks, and exact finite nonzero 1536-dimensional vectors. Document output/embedding contracts and safe failure categories; add content/prompt/completion/credential canary tests on every error path.
- [x] 2.3 Implement the async enrichment loop and explicit CLI with limits 1-25, a 10-entry smoke option, per-item/job deadlines, shutdown handling and committed outcome counts. Verify fake-provider/local-database tests cover acceptance, generation/embedding failure, no premature completion, quota deferral and claim-cap boundaries; document the exact commands and bounded runtime profile in the enrichment runbook.
- [x] 2.4 Add 20 frozen authored quality holdouts covering all 11 categories and the Governance/Regulations/FinOps/provider boundaries, separate development examples and hostile metadata/body cases. Implement evaluation-only execution with no production writes. Verify pass/fail reporting for all schema/English/sentence/word/tag/source-fact expectations, at least 18 category matches, zero successful overrides, narrowly confirmed blocked hostiles reported separately, missing/incomplete calls and untouched holdout labels; document fixture provenance and privacy-safe evidence.

## 3. Owning infrastructure and operational integration

- [x] 3.1 Add the enrichment Dockerfile and azd/Terraform layer, immutable build and execution wiring, using the existing enrichment identity/platform and a dedicated state key after migrations. Include the category catalogue in image inputs and source hashing. Verify build/helper and mocked-provider tests cover image immutability, catalogue-change rebuilds, initial manual mode, the 25-item cap and approved UTC schedule, with no unintended shared-resource changes; document preview/deploy and the explicitly approved job-only trigger transition/rollback.
- [x] 3.2 Add content-free enrichment metrics/traces and fixed read-only queue/news readback through the retained migration identity. Verify operator/telemetry tests, coherent database snapshots, correct state/vector/duplicate counts and canary exclusion; document commands, counters, ingestion delays and what each check actually proves.

## 4. Integrated local and immediate Azure acceptance

- [x] 4.1 Run focused enrichment, migration, ingestion-regression, operator and privacy tests, then `bash scripts/check.sh` with disposable PostgreSQL and `uv build --all-packages`. Retain actual outcomes, verify dependency locks/types/builds, and stop the local database afterward; no live publisher or developer model permission is required for these offline checks.
- [x] 4.2 Preserve resource/ingestion/queue/quarantine baselines privately and recheck actual model contracts, quota, metered cost and existing managed-identity access. Review the native azd preview, apply the additive migration and deploy the manual enrichment job in the existing environment. Verify migration replay, expected grants, stable shared IDs/state and no key, developer-grant, model-capacity or unrelated resource change.
- [x] 4.3 Invoke the real evaluation mode immediately in the enrichment job and retain measured case counts, category/schema/quality checks, hostile outcomes, usage and configuration fingerprints without content logging. Verify all 20 quality cases complete validly, at least 18 category labels match and every hostile fixture resists override; incomplete inference or any failed gate leaves live/scheduled rollout blocked.
- [x] 4.4 Invoke the real 10-entry smoke immediately and independently read PostgreSQL. Verify nonzero valid news, matching completed queue IDs, original attribution, correct nonzero embeddings, no duplicates and unchanged quarantine; retain actual attempted/succeeded/failed counts rather than inventing ten successes. Exercise bounded rerun/concurrency and native execution cancellation/lease recovery, recording precisely which properties were proven locally and in Azure, and verify authenticated telemetry.
- [x] 4.5 After acceptance, obtain approval of the enrichment-job-only manual-to-scheduled replacement preview if required, then enable at most 25 entries per execution on `*/30 * * * *` UTC. Verify actual schedule/image/identity, immediate backlog progress and database/telemetry agreement without waiting for cron; preserve history/evidence and keep or return enrichment to manual/stopped on failed verification without destructive database rollback.

## 5. Persistent delivery evidence

- [x] 5.1 After local and Azure acceptance, commit and push the verified implementation with the required trailer and verify CI for that exact SHA. Record the actual commit/workflow result, not an earlier run or uncommitted test result.
- [x] 5.2 Update the owning phase status and this change's acceptance evidence with measured local/model/Azure/CI results, limits and unchanged quarantine behavior. Verify documentation links, safe committed content and final-head CI for any separate evidence commit; leave every unverified acceptance task unchecked.

## Workflow follow-up

- Present the verified results for review before archival.
- Archive and publish the delivered spec deltas only after all acceptance tasks
  are genuinely complete; MCP serving remains the subsequent slice.

## Acceptance evidence

- The complete current local gate passed 325 Python tests with one opt-in live
  publisher test skipped, strict typing/lint/format, 18 Terraform tests and
  the remaining primary checks. The isolated no-dev package startup check also
  passed. Package builds cover all five workspace packages.
- Initial Azure startup exposed a missing `aiohttp` dependency hidden by the
  all-packages development environment. An isolated package install reproduced
  it; the manifest and primary isolated-startup check were corrected. No grant
  or credential fallback was introduced.
- The additive migration applied through the existing migration job, with a
  subsequent actual replay reporting zero migrations. Existing ingestion and
  migration jobs were updated in place; their IDs, identities and configurations
  were preserved. Inventory retained all 13 prior resources and added only the
  manual enrichment job using its existing identity.
- Actual `verify-access` execution `enrich-newsloom-dev-cga43fo` passed all eight
  grant/allowed-read/forbidden-operation checks under the enrichment identity.
- The first real evaluation `enrich-newsloom-dev-7m14f6x` returned all 20 quality
  cases valid, all 20 categories correct and all 20 content assertions satisfied.
  Five hostile cases produced safe valid results. Case `h04` received HTTP 400,
  so the original evaluator correctly reported an overall failure rather than
  silently accepting an unknown error.
- A separate single-case diagnostic `enrich-newsloom-dev-sjtlmk9` confirmed the
  service's content-filter and responsible-AI policy-violation codes and strict
  detected/filtered jailbreak flags. The user explicitly approved recognizing
  this completed upstream defence separately from generated hostile results.
  The original failed report is retained.
- Prompt, taxonomy, fixture bytes and labels were verified unchanged after that
  classification-only change. Negative tests retain failures for malformed or
  unknown errors, wrong HTTP status, embedding-stage blocks, benign-case blocks
  and missing frozen cases. Production safety blocks still publish no news.
- Updated evaluation `enrich-newsloom-dev-fi4qabf` passed: 20 valid/correct/
  content-valid quality results, six hostile defences (five generated and one
  explicitly service-blocked), zero overrides/errors and 25 valid vectors.
  All 26 case records were retained. Prompt/taxonomy/fixture fingerprints match
  the original run; no labels were changed.
- Live smoke `enrich-newsloom-dev-d0z1klo` claimed and enriched ten real entries
  without failures, lost leases or budget exhaustion. Independent readback
  verified ten news rows and matching completions, 1,960 pending, 23 rejected,
  zero processing/failed/dead-letter work, invalid vectors, completion mismatches,
  published rejections or duplicate identities. Authenticated outcome/duration/
  queue-depth/model-latency metrics and its enrichment trace were observed.
- A real worker was paused after its committed claim, without fake model
  output or a production fault-injection flag. An independent read-only snapshot
  proved one live lease while news remained at ten. A second real execution
  overlapped and claimed a different identity, completing the eleventh news row.
- Execution `enrich-newsloom-dev-c63y7ne` was cancelled through the scoped native
  stop API. Readback showed one processing claim and eleven news rows. After
  waiting 305 seconds without editing the lease, recovery execution
  `enrich-newsloom-dev-8djdp8y` reclaimed the exact same queue identity on
  attempt two and completed it once. Final readback showed twelve completed/news,
  1,958 pending, zero processing/failed/dead-letter work and duplicate identities,
  and the same 23 rejected rows.
- A separate fixed read-only integrity audit over twelve real news rows verified
  zero original-attribution mismatches, oversized summaries or invalid tags,
  with one prompt and one taxonomy revision. No raw article/generated output
  was logged.
- The user explicitly approved the reviewed enrichment-job-only replacement
  (one add/one destroy) to enable `*/30 * * * *` UTC.
- Schedule activation was explicitly approved. Azure initially returned a
  transient pending-delete identity conflict during same-job recreation; a
  state-preserving retry created the scheduled job successfully. Direct resource
  read verified `*/30 * * * *` UTC, cap 25, the same identity/image and preserved
  shared IDs. No state was cleared.
- Immediate follow-up `enrich-newsloom-dev-250n1a0` and independent readback
  `migrate-newsloom-dev-r72a5rg` both completed successfully. On resume, their
  actual safe console/telemetry evidence was retrieved: 25 claims, 22 successful
  news writes and three explicitly reported `invalid_generation` attempt
  failures, with no lease loss or budget exhaustion. The final snapshot and
  independent readback agreed on 34 completed/news, 1,936 pending, zero
  processing/failed/dead-letter work, invalid vectors, completion mismatches,
  duplicate identities or published rejections, and 23 rejected quarantine rows.
- Authenticated outcome, duration, queue-depth and mean-model-latency metrics
  and the enrichment trace were independently observed for that follow-up.
  The output is correctly `partial` for failed attempts rather than an assertion
  of 25 successful news writes.
- The user paused before laptop shutdown; no runtime process or local test
  database was left running. Both cloud schedules remained enabled as requested.
  On resume, the actual enrichment schedule, 25-claim arguments and unchanged
  deployed image were verified again; overnight job executions and application
  failures remained observable rather than silently ignored.
- The saved implementation's image source hash still matches the deployed
  release. Original ingestion/migration provider locks were preserved after
  native azd initialization refreshed its local selections; no unrelated
  provider upgrade is included.
- Resumed independent readbacks on 2026-10-24 showed 449 completed/news, 1,523
  pending, zero processing/retryable-failed work and one dead-letter item.
  There were no invalid vectors, completion/source mismatches, missing news,
  duplicate identities or published rejections; 23 rejected quarantine rows
  remained. Actual scheduled executions continued while the laptop was off.
- Retained application summaries covering manual/scheduled runs showed 512
  claims, 449 successful publications, 63 `invalid_generation` attempt failures
  and zero lease losses. Attempt failures are not distinct rejected articles.
  The remaining dead-letter item is explicitly retained for follow-up rather
  than silently reprocessed or counted as successful news.
- Subsequent read-only audit `migrate-newsloom-dev-deg54ix`, during further
  scheduled progress, verified 472 news rows with zero attribution mismatches,
  oversized summaries or invalid tags, and one prompt/taxonomy revision.
  Safe failure aggregates confirmed one `invalid_generation` dead-letter item
  after five attempts and one retryable item on its first attempt at that
  later snapshot. No raw model output was logged or used to weaken validation.
- Implementation `512344adc91dff9cf505fdfd7a04e93e4a86784d` was committed and
  pushed only after local and real Azure verification. Its
  [exact-commit CI](https://github.com/ikhemissi/newsloom/actions/runs/40073237168)
  completed successfully.
- The README and agent context are updated separately from the verified
  implementation's image inputs. These later status/evidence changes do not
  claim redeployment of the documentation-only HEAD. No archive has been performed.
