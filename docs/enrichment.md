# Enrichment operations

Status: implemented and verified locally and in Azure; delivery CI is pending. The owning
[change](../openspec/changes/enrichment/tasks.md) retains actual acceptance evidence.
See [PRD-1](prd-1.md) for sequencing and
[the capability contract](../openspec/changes/enrichment/specs/news-enrichment/spec.md)
for behavior; MCP serving remains a later slice.

## Contracts and taxonomy

The [category catalogue](../config/categories.json) owns labels and stable IDs.
Governance covers AI-agent governance and AI gateways, not Regulations.
Each generation returns 2-3 summary sentence units (joined into stored plain text),
at most 100 whitespace-separated words, one category ID and 3-5 unique lowercase
tags. Whitespace/case normalization does not supply missing fields or facts.
The generated result must pass its closed schema before embedding.

## Database ownership and states

The migration job applies the additive enrichment migration. Previously applied
migrations are immutable; runtime startup does not run DDL or seed rows.
Existing accepted rows remain pending. Processing adds an expiring ownership
token, attempts and safe errors; successful publication moves to completed,
retryable work to failed, and exhausted work to dead letter.

`news` references its queue identity and contains source attribution, generated
summary/category/tags, a nonzero `vector(1536)` and model/revision metadata.
The article body is not copied into news. Completed queue rows remain retained
for ingestion deduplication. Enrichment cannot read or modify quarantine.
Ingestion's pending-depth count excludes completed history.

All runtime access uses the existing enrichment managed identity and narrow
database privileges. No developer database grant, firewall exception, password
or model key is part of this slice.

## Ownership and recovery

The initial worker profile uses 300-second leases and 240-second item deadlines.
Claims use `FOR UPDATE SKIP LOCKED`; model requests run outside transactions.
Completion and failure updates require both the current token and an unexpired
lease. News insertion and final queue completion commit together or roll back.
Completed rows cannot be reclaimed or republished.

Expired claims become retryable failures or dead letter after five processing
attempts. Retry eligibility grows from 30 seconds to at most 30 minutes, or later
when the provider supplies a longer Retry-After. A stale worker cannot update its
success or failure after another worker takes ownership. Cancellation leaves an
expiring claim, not a false completion. Model requests may be repeated after a
crash; database effects are fenced, not model billing.

## Model requests and failures

Generation uses the existing deployment's strict JSON Chat Completions contract,
with trusted instructions and a separate serialized untrusted entry. Each article
has an independent request, no prior article history and no tools. Refusal, incomplete
termination, invalid JSON, unknown categories and invalid fields fail explicitly;
there is no model-based repair or category fallback.

Only a validated result reaches the embedding adapter. Its input contains title,
summary and bounded metadata, not raw article text. The vector must have exactly
1536 finite non-boolean numeric components and a nonzero norm.

Requests use verified HTTPS, Entra, a 30-second timeout, at most three transport
attempts and a 256-KiB response ceiling. HTTP 401/403 and nonretryable errors do not
silently switch identities or models. Retry-After is parsed with the shared feed
helper and preserved when work must defer. Extremely large/invalid headers are
explicit errors, never unbounded sleeps. Diagnostics expose safe categories such
as `generation_http_429`, `invalid_generation`, `invalid_embedding` and lease loss,
not upstream response bodies.

Outcome, input/output token and request counters are content-free. Token usage
means numeric usage totals, never credential tokens; embedding has no generation
output tokens. Model latency metrics are explicitly per-run means.

## Worker and local checks

```bash
uv run --locked pytest tests/test_enrichment_contracts.py tests/test_enrichment_providers.py
NEWSLOOM_TEST_POSTGRES_DSN="host=127.0.0.1 port=15432 user=postgres dbname=postgres" \
  uv run --locked pytest tests/test_enrichment_database.py tests/test_enrichment_job.py
```

Database tests require the explicitly started disposable PostgreSQL 18/pgvector
instance described in the [platform runbook](azure-platform.md#local-database-tests).
Offline tests use fake providers only; no accepting/generating fallback is
available in a deployed job.

The runtime CLI exposes `newsloom-enrichment run --limit 10` for the initial smoke
and `newsloom-enrichment run --limit 25` for normal bounded work. `--limit` must be
1-25 and counts claims, including failed attempts, not just successful writes.
The job budget is 900 seconds with 20 reserved for shutdown; another claim starts
only when a complete item/commit budget fits. Budget exhaustion is a visible
partial outcome. Pending/processing/retryable-failed/completed/dead-letter counts
are distinct from the execution's claimed/enriched/failed/lease-lost counters.

## Quality evaluation

`newsloom-enrichment evaluate` is an explicit evaluation-only command dispatched
before database or production telemetry initialization. It uses the existing
managed identity and the same real generation/embedding adapters; it never
publishes fixtures or requests a developer role.

The packaged authored data contains two development examples, 20 separate frozen
quality holdouts covering all 11 categories, and six hostile title/body/author/
category cases. Labels are fixed before real inference. Quality assertions check
the strict result, sentence/word/tag limits, expected English source-fact wording,
primary categories and valid embeddings. These finite content assertions are not
an independent language detector, model judge or proof of arbitrary factual
accuracy. No raw prompts or completions appear in evidence.

Acceptance requires all 20 quality outputs valid and satisfying their content
assertions, at least 18 correct categories, all six hostile cases passing, zero
successful override markers, valid vectors for generated results and no
incomplete/error calls. With explicit user approval, a hostile request blocked
by a narrowly confirmed service jailbreak filter is a completed safety defence:
report it separately from generated/embedded hostile results. Recognition requires
HTTP 400, `content_filter`, `ResponsibleAIPolicyViolation`, and strict true
detected/filtered jailbreak flags. Unknown/malformed HTTP 400 responses remain
errors. A blocked benign quality case still fails its required valid-output gate.
No summary, category or vector is invented for a blocked hostile case.
Missing fixtures and operational failures cannot count as safe classifications.
After seeing a holdout, changing the prompt requires a fresh holdout, not revised
labels. Reports retain only opaque case IDs, category IDs, pass/fail assertions,
counts, configuration/fixture fingerprints and token/timing totals.
In normal processing, a recognized block is still an explicit failed attempt
(`generation_jailbreak_filtered`) and never publishes news or alters quarantine.

## Deployment and immediate verification

The enrichment azd layer depends on migrations and the compatible ingestion image.
The category catalogue participates in the image source hash; changing it cannot
reuse a stale enrichment image. Images are registry-built and digest-pinned.

After local acceptance, preserve the existing environment and readback baseline.
Start with `ENRICHMENT_SCHEDULE_ENABLED=false` in the existing ignored azd
environment, apply the additive migration, update ingestion's state-aware image
in place, then preview and provision only the owning enrichment layer.
No shared service, identity, region or model capacity needs replacement.

```bash
uv run --locked newsloom-platform build-enrichment
azd provision enrichment --preview
azd provision enrichment
uv run --locked newsloom-platform verify-enrichment
uv run --locked newsloom-platform evaluate-enrichment
uv run --locked newsloom-platform execute-enrichment --limit 10
uv run --locked newsloom-platform read-enrichment
```

`verify-enrichment` invokes actual allowed queue/news reads, inspects the column
grants, and proves denial of quarantine access, queue insertion/content mutation,
news deletion and schema creation. Denied operations run in transactions and no
probe object is committed even if permissions are accidentally broader.

The real quality/hostile evaluation must pass before a live smoke or scheduling.
Readback uses the retained migration identity and fixed read-only aggregate SQL;
it reports state/news counts, vector validity, completion/source mismatches,
published rejections and duplicate identities, never summaries or model output.
Authenticated metrics/traces and console logs can arrive after execution finishes;
wait for the actual evidence rather than infer persisted writes from job status.

After verified smoke/recovery and explicit approval of the job-only replacement
preview, set `ENRICHMENT_SCHEDULE_ENABLED=true` and provision enrichment through
azd to use `*/30 * * * *` UTC. This changes only the newly introduced enrichment
job's trigger; shared resources and PostgreSQL rows remain. Runtime stays capped
at 25 claims per execution. On failed verification stop enrichment and disable
scheduling via a reviewed job-only transition; keep the additive schema and all
queue/news data. Do not roll back the queue to its old pending-only constraint.

Azure may briefly return `409 FailedIdentityOperation` when recreating the same
job after trigger replacement, reporting that deletion is still pending. Preserve
the existing azd state, let deletion settle, review the retry preview (creation of
that same job only), and retry. Do not delete the identity, change the job name,
clear state, or recreate the shared platform to bypass this transient conflict.

## Quota and compute cost observations

The verified existing generation deployment advertised 10 requests/minute and
10,000 tokens/minute; embeddings advertised 10 requests/10 seconds and 10,000
tokens/minute. These are observations for the selected deployments/capacities,
not universal capacity-unit conversions. Retry-After delays are included in the
job budget; request-time totals exclude those backoff sleeps. No quota/capacity
increase is introduced automatically.

The public France Central active consumption rates checked for this delivery were
USD 0.000024 per vCPU-second and USD 0.000003 per GiB-second. At 0.25 vCPU and
0.5 GiB, a full 900-second execution costs about USD 0.00675 in worker compute
before free grants. Forty-eight full-duration scheduled runs/day for 30 days
would be about USD 9.72 in compute, not a total invoice or a hard spending cap.
Actual runs are shorter; model tokens, builds, telemetry, storage, manual/evaluation
runs and taxes are additional. Existing shared services and model capacity remain
unchanged; actual token totals are retained with the evaluation/run evidence.

## Verified delivery observations

The local gate passed 325 Python tests with one opt-in publisher test skipped,
18 Terraform tests, strict typing/lint/format/spec checks, the isolated no-dev
runtime startup check, and builds of all five workspace packages.

The frozen quality set produced 20 valid outputs, 20 matching primary categories
and 20 passing source-content assertions. All six hostile cases were defended:
five produced safe valid results and one was explicitly blocked by the service
jailbreak filter. There were zero successful overrides or operational evaluation
errors and 25 valid vectors; no vector was invented for the blocked case.
These finite authored tests do not establish production-wide accuracy.

The immediate smoke processed and published ten real entries. Independent
database readback and authenticated telemetry verified their completion. A
real overlapping worker claimed a distinct item, and a deliberately cancelled
execution left one expiring claim. After natural lease expiry, a fresh worker
reclaimed that exact identity on attempt two and completed it once. At that
point there were twelve valid news rows, no duplicates or integrity mismatches,
and the existing 23 rejected entries remained quarantined.

After the explicitly approved trigger replacement, the scheduled job retained
the verified image and existing identity, with `*/30 * * * *` UTC and a 25-claim
cap. Its immediate follow-up made **25 claims and 22 successful publications**,
with three explicit `invalid_generation` attempt outcomes, not 25 invented
successes. The same run's final snapshot and independent readback showed
34 completed/news rows and zero processing, retryable-failed or dead-letter
work, invalid vectors, completion mismatches, duplicate identities or published
rejections. A failed attempt can retry within a later claim; attempt-failure
totals are not a count of permanently lost articles.

The worker deliberately fails closed on invalid generated output. A `partial`
summary means some attempts failed even if the Container Apps execution exits
successfully and subsequent retries complete. Inspect the application outcome,
failed/dead-letter counts and readback rather than treating job status alone as
proof of error-free processing. `invalid_generation` does not identify a proven
injection, and telemetry intentionally does not contain raw completions or a
claim about which particular validation rule failed.

The resumed independent readbacks on 2026-10-24 showed **449 completed/news rows**,
1,523 pending, zero processing/retryable-failed work and one dead-letter item.
All vector/completion/duplicate/published-rejection checks were zero, and the
same 23 rejected quarantine rows remained. These are dated snapshots, not a
permanent backlog size: ingestion and enrichment continue on their Azure schedules
when the developer laptop is off.

The retained application summaries at that observation covered 512 claims and
449 successful publications, including manual smoke/recovery and scheduled runs.
They recorded 63 `invalid_generation` attempt failures and zero lease losses;
those attempts are not 63 distinct rejected articles. The one dead-letter item
is an explicit unresolved output-validation follow-up, not automatically
released, reset or hidden as a successful publication.

See the owning change's
[acceptance evidence](../openspec/changes/enrichment/tasks.md#acceptance-evidence)
for execution references, retained limitations and delivery/CI state.
