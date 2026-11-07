# Tasks

## 1. Acquisition behaviour

- [x] 1.1 Fetch the article for every new accepted item; apply the text selection rule and keep `feed_text`; keep feed identity fields. Tests: teaser vs long body, complete feed text, metadata-only page, redirect, script-only page, title-only item, duplicates/filtered items make no request. Uses an authored roundup-shaped page instead of the real Foundry HTML (a publisher page should not be committed to this public repository).
- [x] 1.2 Cache robots per host per run and parse `Content-Signal` for the applicable group; add the per-host semaphore, `Retry-After` handling and the new user agent. Tests: one robots GET per host per run, `ai-input=no` blocks only articles, throttling defers items, missing/failed robots semantics unchanged.
- [x] 1.3 Add 90-day retention of article text and the new telemetry categories; verify no article text reaches logs, telemetry or API responses.

- [x] 1.4 Add the operator backfill command for items from the last 14 days, idempotent and bounded by the job deadline; tests cover the window, idempotence and unchanged news rows.

## 2. Deliver

- [x] 2.1 Update `docs/ingestion.md` (acquisition, robots/content-signal policy, retention, per-source audit) and the PRD-1 capability note; run `bash scripts/check.sh` and `npm run spec:check`.
- [x] 2.2 Deploy the ingestion image through azd (preview shows only image/revision), run one manual ingestion, and record per-source acquisition outcomes and the stored text size of new items; run the backfill once and confirm the Foundry October roundup now stores its body.
  - Evidence (2026-11-07, dev): migration 010 applied by the migrations job (preview: only the job image changed); ingestion preview changed only the job image; one manual ingestion succeeded. `backfill-articles` processed 190 completed items from the last 14 days: 48 stored the article body (25%), 128 kept already-complete feed text, 14 kept feed text after a failure (9 article redirects, 5 robots denials from Comet's staging host), 0 rejected by screening. Content-free readback by acquisition path: article_body 48 items averaging 1,822 words with feed text retained; feed_item 128 averaging 1,859 words.
  - Correction: the Foundry October roundup's feed already carried the full post (3,555 words), so it correctly kept feed text. Its missing announcements come from the 2-3 sentence summary limit, which `announcement-graph` addresses, not from acquisition. The proposal's teaser diagnosis came from the page metadata, not from stored text.
