# Design

## Context

See proposal.md (Why). Today `job.py` calls `recover()` only when a candidate
lacks a title or text. `extract()` prefers JSON-LD/OpenGraph `description` over
the visible body, which is how the Foundry roundup stored its 28-word teaser.
`RetrievalClient.fetch()` re-downloads robots.txt before every request,
including feed redirects. Stored text is bounded at 32 KiB, screened, and kept
in `ingestion_queue.entry`; the ingestion role already has UPDATE on that table.
The job has a 900-second deadline and runs about 100 new items per week.

## Goals / Non-Goals

**Goals:** real article text for new items; fewer, not more, robots requests;
explicit outcomes for every non-acquired article; no new resources.

**Non-Goals:** re-fetching existing items (the backlog keeps feed text), raising
the 32 KiB bound, rendering scripts, following redirects.

## Decisions

- **Always fetch, no decision model.** Deciding whether a teaser is enough
  requires the article anyway; a GET is far cheaper than a model call and
  deterministic. Alternative: LLM or heuristic gate; rejected for cost and
  unpredictability.
- **Text selection rule:** use the visible body when it has at least 150 words
  and at least twice the words of the best feed/metadata text; otherwise keep the
  feed text. Store the replaced feed text in a `feed_text` column (not inside
  `entry`, which enrichment sends to the model whole) so retention can revert
  to it and evaluations can compare. An `acquisition` column records the path
  or failure category; legacy rows keep NULL, which the backfill uses for
  idempotence. Alternative: always prefer the body;
  rejected because some feeds (release notes, changelogs) already carry the full
  entry while pages add navigation noise.
- **Per-run robots cache** keyed by scheme+host inside the retrieval client,
  holding the parsed policy and Content-Signal values. Missing file allows; a
  disallow denies. Transient robots failures are not cached, so the next item
  retries them (unchanged semantics per request).
- **Content-Signal parsing:** read `Content-Signal:` lines inside the group that
  applies to `Newsloom`, else `*`, with the same group matching as robots rules.
  Only `ai-input=no` blocks acquisition. Unknown keys are ignored.
- **Politeness:** an article lock per host, one retry on 429/503 when
  `Retry-After` is at most 60 s and fits the deadline, otherwise
  `article_throttled` defers the item via the existing deferred-recovery path
  (the feed validator is not advanced, so the next run retries it). User agent:
  `Newsloom/0.2 (+https://github.com/ikhemissi/newsloom)`; the robots matching
  token stays `Newsloom`.
- **Retention in the ingestion job:** one bounded UPDATE per run (at most 500
  rows) sets `entry.text` back to `feed_text` and clears `feed_text` for
  completed rows whose article was acquired more than 90 days ago; only the
  count is reported.
- **Backfill:** `backfill-articles` (ingestion CLI, dispatched by
  `newsloom-platform backfill-articles` into the ingestion job) processes
  completed queue rows with NULL `acquisition` published in the last 14 days,
  screens any richer text with the production scanner before storing it, and
  records an outcome for every attempted row.
- **Telemetry:** reuse acquisition-path counts; add per-source counters
  `article_attempted`, `article_body_selected`, `feed_text_kept` and the run
  counter `article_text_retired`; failure categories include
  `content_signal_denied`, `article_redirect` and `article_throttled`.

## Risks / Trade-offs

- [Pages add navigation/footer noise to text] → body extraction already limits to
  visible article content; the selection rule keeps feed text when the gain is
  small; the scanner still screens everything.
- [Longer text raises screening and enrichment tokens] → bound unchanged (32 KiB,
  about 8k tokens); measured in `announcement-graph` before deployment.
- [More requests to publishers] → about 100 GETs per week plus at most one
  robots.txt per host per run, fewer robots requests than today.
- [Prompt injection in full pages] → unchanged screening and untrusted-data prompts.

## Migration Plan

Ship code with tests, apply migration 010 through the migrations job, deploy
the ingestion image through the existing azd layer (preview shows only the
image/revision change), run one manual ingestion and
compare acquisition outcomes per source. Rollback: redeploy the previous image;
stored items remain valid either way.

## Open Questions

None blocking.
