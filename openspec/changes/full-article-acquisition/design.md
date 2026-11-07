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
  feed text. Store the feed text alongside (`entry.feed_text`) so retention can
  revert to it and evaluations can compare. Alternative: always prefer the body;
  rejected because some feeds (release notes, changelogs) already carry the full
  entry while pages add navigation noise.
- **Per-run robots cache** keyed by scheme+host inside the retrieval client,
  holding the parsed policy, Content-Signal values and robots outcome. Missing
  file allows; other failures deny for the run (unchanged semantics).
- **Content-Signal parsing:** read `Content-Signal:` lines inside the group that
  applies to `Newsloom`, else `*`, with the same group matching as robots rules.
  Only `ai-input=no` blocks acquisition. Unknown keys are ignored.
- **Politeness:** an article semaphore per host (1), `Retry-After` honoured up to
  60 s within the job deadline, otherwise the item is deferred via the existing
  deferred-recovery path. User agent:
  `Newsloom/0.2 (+https://github.com/ikhemissi/newsloom)`; the robots matching
  token stays `Newsloom`.
- **Retention in the ingestion job:** one bounded UPDATE per run sets
  `entry.text = entry.feed_text` and removes article fields for completed rows
  older than 90 days; counts only are reported. No migration is needed.
- **Telemetry:** reuse acquisition-path counts; add fixed categories
  `content_signal_denied`, `article_redirect`, `article_no_body`,
  `article_throttled`, `article_body_selected`, `feed_text_kept`.

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

Ship code with tests, deploy the ingestion image through the existing azd layer
(preview shows only the image/revision change), run one manual ingestion and
compare acquisition outcomes per source. Rollback: redeploy the previous image;
stored items remain valid either way.

## Open Questions

None blocking.
