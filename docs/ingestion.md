# Ingestion operations

The ingestion change implements
[PRD-1 source retrieval](prd-1-capabilities.md#p1-c02-safe-feed-retrieval-and-normalization)
and [screening/quarantine](prd-1-capabilities.md#p1-c03-content-screening-and-quarantine).
Reuse the [platform](azure-platform.md) and its persistent `dev` environment.
Do not consider the job delivered until its actual Azure acceptance is recorded.

## Retrieval settings

The initial approved profile is four concurrent feeds, an 8 MiB feed body,
256 KiB robots.txt, 5-second connection and 30-second request timeouts,
60 seconds per feed retrieval/parse, three redirects, and two retries.
The complete job has 900 seconds including screening/shutdown. At most 1,000
entries are parsed per feed; normalized text is bounded to 32 KiB UTF-8.
Compressed responses are bounded while decoding, not after unlimited expansion.
HTTPS, public pinned addresses, robots policy, and safe XML parsing remain
mandatory; an unavailable publisher is a reported outcome, not a policy bypass.

## Item recovery and per-feed counts

Only an individually malformed item is dropped; valid siblings continue. Unsafe
XML/DTD/entities and document size/item limits still fail the document. Closing
the HTML normalizer preserves ordinary final text such as ampersand-containing
titles.

### Article acquisition

Every new eligible item (not a known duplicate, not category-filtered) gets one
article GET, defined by the
[`full-article-acquisition` change](../openspec/changes/archive/2026-11-08-full-article-acquisition/proposal.md).
Feed identity fields (title, URL, GUID, dates) stay authoritative. Missing
title/text is still filled from JSON-LD/OpenGraph, then visible article text.
The stored text becomes the visible article body when it has at least 150 words
and at least twice the words of the feed/metadata text; otherwise the feed text
is kept. The replaced feed text is stored in `feed_text` and the outcome in
`acquisition` (queue and quarantine columns, migration 010), not inside the
entry, because enrichment sends the whole entry to the model.

Article GETs never follow redirects, execute JavaScript, fetch assets, resolve
remote JSON-LD contexts, rewrite hosts or bypass sign-in. The existing
HTTPS/public pinned DNS, robots, byte and time limits apply. A failed, denied,
redirected or script-only article leaves a complete item with its feed text;
an incomplete item keeps the previous recovery rules. Acquired text is screened
as untrusted publisher data and is model input only: it is never returned by
the UI, HTTP or MCP APIs, logs or telemetry.

**Publisher rules.** robots.txt is read once per origin per run (transient
failures are retried on the next use, not cached). The robots token is
`Newsloom`; the user agent is
`Newsloom/0.2 (+https://github.com/ikhemissi/newsloom)` and never imitates a
browser. A `Content-Signal` line in the group that applies to `Newsloom` (else
`*`) with `ai-input=no` blocks article requests for that host; the item keeps its
feed text. Articles are requested one at a time per host; a 429/503 is retried
once when `Retry-After` is at most 60 s and fits the deadline, otherwise the item
is deferred to a later run (`article_throttled`).

Audit on 2026-11-07 against each source's article host: 40 of 41 sources allow
`Newsloom`. Comet's feed links to a staging host that disallows all crawlers, so
it keeps feed text (no host rewriting). Six sites publish `Content-Signal`; all
allow `ai-input`, and Giskard disallows `ai-train` (Newsloom never trains on content).

**Retention and backfill.** Each run restores the feed text and clears
`feed_text` for completed items whose article was acquired more than 90 days
ago (at most 500 rows per run, count `article_text_retired`). To acquire
articles for items stored before this change, run once:

```bash
uv run --locked newsloom-platform backfill-articles
```

It runs inside the ingestion job under its identity, processes completed items
published in the last 14 days whose `acquisition` is still empty, screens any
richer text with the production scanner, records an outcome for every attempted
item and is safe to repeat. Published news rows and summaries are unchanged.

Measured on 2026-11-07: of 190 items from the previous 14 days, 48 (25%) were
feed teasers and now store the article body (about 1,800 words on average); 128
already had complete feed text; 14 kept feed text after 9 article redirects and
5 robots denials. Screening rejected none.

`feed_sources.counts` holds **latest-run activity**, tied to `last_run`, not lifetime
totals. Existing found/filtered/duplicate/staged counters are joined by:

| Keys | Meaning |
| --- | --- |
| `accepted`, `security_rejected`, `deferred` | Committed screening decisions in this run; deferred is not current backlog depth. |
| `malformed_rejected` | Individual parsing/normalization drops, not model rejection. |
| `feed_item`, `article_metadata`, `article_body` | New staged items, once each by the deepest tier needed; mixed metadata/body uses article-body. |
| `recovery_attempted`, `recovery_failed`, `recovery_deferred` | Recovery attempts (including authorization), failures, and necessary recovery awaiting retry. |
| `article_attempted`, `article_body_selected`, `feed_text_kept` | Article GETs for items whose feed fields were complete, and whether the article body replaced the feed text. |

New acquisition counts exclude duplicates, filtering and malformed drops.
Screening an older deferred item can increment a decision counter even after 304
or a fetch failure, with zero new acquisition. Decisions and corresponding
per-feed counters commit atomically. A temporary failure recovering a required
field keeps previous validators so the next run can retry; stored siblings
deduplicate. Empty/all-malformed bodies and incomplete work cannot hide behind
new validators. Document failures remain explicit, including OpenAI feeds above
the unchanged 1,000-item cap.

There are 41 active catalogue sources after retiring `solo-io-blog`; the existing
`agentgateway-blog` is retained once. Historical database rows are not deleted,
so `read-ingestion` can still show the retired Solo.io row and its older run.
Compare each source's `source_run` with the current execution correlation before
interpreting aggregate latest-source statistics as one run.

## Local tests

Unit tests use fixtures and database tests use an explicitly local disposable
PostgreSQL 18/pgvector instance. CI never fetches publishers or calls models.
The opt-in live smoke test fetches just one RSS and one Atom source, not the
full catalogue. Its fixture scanner decisions prove persistence, not real-model
screening; the real managed-identity scanner is verified in Azure.

```bash
uv run pytest tests/test_ingestion_feeds.py
uv run --locked newsloom-ingestion fetch \
  --source langchain-blog \
  --source vertex-ai-release-notes
```

The optional database-backed live test is
`NEWSLOOM_LIVE_INGESTION=1 uv run --locked pytest -s tests/test_ingestion_live.py`
with the disposable database DSN configured as in the
[platform test guidance](azure-platform.md). It uses fixture verdicts only.

## Database ownership

Versioned platform migrations own `feed_sources`, `ingestion_queue`, and
`quarantine`. The catalogue file remains authoritative. Runtime ingestion has
no schema/admin or quarantine-delete grant. Accepted entries are pending queue
work; rejected entries are retained. Deferred screening is recorded separately
from rejection and retried without relying on the source returning its body again.
Enrichment and the `news` table remain later work.
Entry URLs retain query strings and fragments: anchors can distinguish releases
on the same page. Deduplication uses that full URL or `(source, GUID)`.
When enrichment is introduced, completed queue rows remain known identities but
are excluded from `pending` and `screened_pending` depth. Enrichment readback
separates processing, failed, completed and dead-letter work from pending entries;
queue history is not an unprocessed backlog.

## Calibration and immediate Azure execution

The ingestion azd layer depends on migrations. Initial deployment is explicitly
manual (`INGESTION_SCHEDULE_ENABLED=false`, `SCANNER_THRESHOLD=""`). The image
includes the catalogue and is pinned by digest; its hash changes with catalogue
edits. The job uses only the existing ingestion identity and Consumption profile.
Its separate Entra-authenticated backend key is
`newsloom/<environment>-ingestion.tfstate`; existing platform states are unchanged.
No new fixed-cost service or model capacity increase is required. Compute and
model usage remain metered.

```bash
uv run --locked newsloom-platform calibrate-ingestion
uv run --locked newsloom-platform execute-ingestion
uv run --locked newsloom-platform read-ingestion
uv run --locked newsloom-platform execute-ingestion --force
```

The contextual follow-up is activated and locally/Azure verified; see its
[measured findings](findings/contextual-content-screening.md) and
[delivery evidence](../openspec/changes/archive/2026-10-23-contextual-content-screening/tasks.md#acceptance-evidence).
Its question distinguishes attempts to redirect the current processor from
ordinary reporting, training-use notices, and contextualized examples. A claim of
research or quotation is not an exemption. Source content remains untrusted even
when accepted; screening does not sanitize it or guarantee that attacks are absent.
See the [behavioral contract](../openspec/specs/content-screening/spec.md).

Calibration uses 16 authored complete-entry calibration cases and 16 separate
validation cases, each balanced benign/hostile, plus eight legacy hostile
regressions. The exact production serializer includes metadata, not just the body.
Only calibration scores choose the separating midpoint. Overlap or any holdout/
legacy error blocks admission; do not guess a threshold or relabel failures.
Reports contain scores and application reason codes, not a model explanation.

### Local before/after comparison

This command uses the existing signed-in Azure CLI identity and model deployment;
it does not use a managed identity, connect to PostgreSQL, start/update Azure jobs,
change azd values, or release quarantine. Do not use `calibrate-ingestion` for a
local experiment: that operator command starts a cloud job.

Provide `MODEL_ENDPOINT`, `SCREENING_DEPLOYMENT`, `SCREENING_MODEL`, and
`SCREENING_VERSION` in the shell from the existing ignored environment without
printing its identifiers. Existing developer inference permission is required;
authorization failure blocks the study, not permission to add keys or grants.

```bash
uv run --locked newsloom-ingestion evaluate \
  --review-manifest /private/path/review.json \
  --baseline-threshold <recorded-baseline-threshold> \
  --report /private/path/new-comparison.json
```

The private manifest is an array of exactly 23 records with `id` (`review-00`
through `review-22`), `source`, `guid`, `url`, and a boolean `hostile` label fixed
before inference. An optional `entry` supplies a complete stored `Entry`; its
identity must match. Otherwise only those identities are reconstructed from their
three selected catalogue feeds, with normal protected parsing/recovery and no
article redirects. Missing or ambiguous identities block comparison. The normal
one-RSS/one-Atom fetch restriction is unchanged. No article cache is written.

Both policies consume identical in-memory entries under one sequential rate
budget, with bounded retries and a 880-second total deadline. Calls are metered
and share the deployment's quota with ingestion; throttling is an operational
failure. The preflight uses one authored calibration entry before article retrieval.
The report path must be new and outside the repository, as must the manifest.
It records opaque case IDs, fingerprints, current-feed versus stored provenance,
acquisition path, normalization-boundary flags, scores, dispositions, and error/
false-positive/false-negative counts. It contains no article bodies or prompts.
A text-at-limit flag is conservative: it does not prove the original was longer.

Rollout requires complete inference, separable calibration, zero holdout and
legacy errors, and fewer benign rejections on the selected 23-item regressions.
These known regressions are not an unseen holdout or a population-wide estimate.
Human-reviewed article identities and possible motives belong in
[findings](findings/contextual-content-screening.md), not runtime telemetry;
the model does not supply motives.

### Explicit comparison in the existing Azure job

After local inference authorization failed, the operator explicitly requested
testing directly in the existing feed job. `evaluate-job` uses that job's current
managed identity and the same comparison implementation, not a developer grant
or another worker. It dispatches before any database connection or admission.

The operator supplies `--review-manifest-json` containing only the frozen public
identities and labels (at most 64 KiB; embedded `entry` bodies are rejected) and
`--baseline-threshold` from the verified configuration. Selected article inputs
are reconstructed in memory. One `screening_comparison_case` console record is
emitted per observation, then a `screening_comparison_summary`; all are content-free.
An incomplete or failed comparison exits unsuccessfully after reporting evidence.

Build the immutable candidate image with the existing ingestion build helper.
Invoke the same job through the native Start API with only the image, arguments,
and correlation overrides. Keep the scheduled admission image/threshold/binding
unchanged during this execution. Do not toggle the trigger or create a temporary
job. After measured gates pass, activate the matched image and configuration
through the existing azd ingestion layer, then immediately invoke normal ingestion
and read its actual database aggregates. A failed comparison does not authorize
activation or a guessed threshold.

### Matching configuration and rollback

The candidate report/calibration output supplies a measured `threshold` (or
`candidate_threshold`) and `calibration_id`. Set them as `SCANNER_THRESHOLD` and
`SCANNER_CALIBRATION_ID` only after all evaluation gates pass. The updated runtime
fails before admission if the binding is missing or differs from its question,
packaged fixtures, endpoint/deployment/model/version, or threshold. The identifier
detects accidental mismatch; it is not quality attestation.

Save the old image and matching calibration configuration privately for rollback.
Review the existing ingestion-layer azd preview, then deploy the image, threshold,
and identifier together without toggling the schedule or replacing resources.
Invoke ordinary ingestion immediately and use the existing readback commands.
Rollback restores the image and its matching configuration as a unit, never
database rows. Existing rejected rows remain rejected; the new policy neither
rescans nor releases them. Do not infer per-row equality from aggregate counts.

The execution helper starts immediately, overrides only supported Start API
container fields, and waits for a bounded terminal result. The readback command
runs fixed read-only aggregate SQL under the retained migration identity; no
developer database role or firewall exception is added. It reports actual source,
pending/screened, rejected/deferred, and duplicate aggregates, not inferred log
counts. Publisher errors remain explicit per-source categories.

After manual acceptance and a forced repeat pass, set
`INGESTION_SCHEDULE_ENABLED=true` and provision through azd to enable
`10,40 7-22 * * *` UTC (every 30 minutes while the database runs; see the
[operations runbook](operations.md)). AzureRM 5.10 requires replacing the ingestion job when switching
between manual and scheduled triggers. Review the preview and obtain approval for
that job-only replacement; shared resources and database rows must remain intact.
The job keeps its name, but execution history may reset; retain acceptance evidence
and Log Analytics logs. Never enable it on an unverified threshold. Run overlapping
executions are rejected by the database lock; accepted rows and quarantine history
survive image updates. See the archived ingestion
[tasks/evidence](../openspec/changes/archive/2026-10-23-feed-ingestion/tasks.md) for actual progress.
