# Tasks

## 1. Acquisition behaviour

- [ ] 1.1 Fetch the article for every new accepted item; apply the text selection rule and keep `feed_text`; keep feed identity fields. Tests: teaser vs long body, complete feed text, metadata-only page, redirect, script-only page, title-only item, duplicates/filtered items make no request. Include the Foundry roundup as a recorded fixture.
- [ ] 1.2 Cache robots per host per run and parse `Content-Signal` for the applicable group; add the per-host semaphore, `Retry-After` handling and the new user agent. Tests: one robots GET per host per run, `ai-input=no` blocks only articles, throttling defers items, missing/failed robots semantics unchanged.
- [ ] 1.3 Add 90-day retention of article text and the new telemetry categories; verify no article text reaches logs, telemetry or API responses.

- [ ] 1.4 Add the operator backfill command for items from the last 14 days, idempotent and bounded by the job deadline; tests cover the window, idempotence and unchanged news rows.

## 2. Deliver

- [ ] 2.1 Update `docs/ingestion.md` (acquisition, robots/content-signal policy, retention, per-source audit) and the PRD-1 capability note; run `bash scripts/check.sh` and `npm run spec:check`.
- [ ] 2.2 Deploy the ingestion image through azd (preview shows only image/revision), run one manual ingestion, and record per-source acquisition outcomes and the stored text size of new items; run the backfill once and confirm the Foundry October roundup now stores its body.
