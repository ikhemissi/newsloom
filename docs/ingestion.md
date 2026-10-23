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

For new eligible items with missing title/text, preserve usable feed fields, then
try JSON-LD article fields/OpenGraph, then visible article text from the same
direct HTML response. Article GETs never follow redirects, execute JavaScript,
fetch assets or resolve remote JSON-LD contexts. The existing HTTPS/public pinned
DNS, robots, streamed/decompressed byte and shared feed/job time limits apply.
Known duplicates and category-filtered items do not trigger article recovery.
Recovered text is screened as untrusted publisher data before acceptance.
Ingestion does not generate summaries; enrichment remains the next slice.
An otherwise valid title-only item remains usable if extra text is unavailable.

`feed_sources.counts` holds **latest-run activity**, tied to `last_run`, not lifetime
totals. Existing found/filtered/duplicate/staged counters are joined by:

| Keys | Meaning |
| --- | --- |
| `accepted`, `security_rejected`, `deferred` | Committed screening decisions in this run; deferred is not current backlog depth. |
| `malformed_rejected` | Individual parsing/normalization drops, not model rejection. |
| `feed_item`, `article_metadata`, `article_body` | New staged items, once each by the deepest tier needed; mixed metadata/body uses article-body. |
| `recovery_attempted`, `recovery_failed`, `recovery_deferred` | Recovery attempts (including authorization), failures, and necessary recovery awaiting retry. |

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

Calibration evaluates eight labelled training cases and eight separate validation
cases, balanced clean/hostile. It derives a separating threshold and requires zero
holdout mistakes. Only safe class counts, threshold, and model metadata are emitted;
fixture text and responses are never logged. Record the observed threshold in the
existing azd environment, reprovision the ingestion layer, and only then run live
admission. A failed calibration is a blocker, not permission to guess a threshold.

The execution helper starts immediately, overrides only supported Start API
container fields, and waits for a bounded terminal result. The readback command
runs fixed read-only aggregate SQL under the retained migration identity; no
developer database role or firewall exception is added. It reports actual source,
pending/screened, rejected/deferred, and duplicate aggregates, not inferred log
counts. Publisher errors remain explicit per-source categories.

After manual acceptance and a forced repeat pass, set
`INGESTION_SCHEDULE_ENABLED=true` and provision through azd to enable
`*/30 * * * *` UTC. AzureRM 5.10 requires replacing the ingestion job when switching
between manual and scheduled triggers. Review the preview and obtain approval for
that job-only replacement; shared resources and database rows must remain intact.
The job keeps its name, but execution history may reset; retain acceptance evidence
and Log Analytics logs. Never enable it on an unverified threshold. Run overlapping
executions are rejected by the database lock; accepted rows and quarantine history
survive image updates. See the active change's
[tasks/evidence](../openspec/changes/feed-ingestion/tasks.md) for actual progress.
