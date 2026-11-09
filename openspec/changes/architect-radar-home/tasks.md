# Tasks

## 1. Preview and mock-up

- [x] 1.1 Add the triage schema, prompt and a local record/replay triage preview over the recorded announcement week; report tier distribution, tokens and cost.
  - Evidence (2026-11-09): triage preview over 65 items with 313 grounded announcements from the recorded week: Act now 5 (2%), Worth knowing 138 (44%), Later 170 (54%); 57k input and 11k output tokens, about USD 0.10 per week. A first rubric put 84% in Worth knowing (changelog entries); the tightened rubric defaults detail to Later and uses a shared capability vocabulary so cross-vendor groups form (for example model routing across five vendors).
- [ ] 1.2 Build the radar page, product page and stack editor in the web app against a fixture from the preview; run it locally for the user's review and adjust before continuing.

## 2. Storage and triage

- [ ] 2.1 Add migration `012_radar.sql` with real-database tests for grants (enrichment updates only triage columns; MCP manages only reader tables).
- [ ] 2.2 Triage in the enrichment job after extraction, with failures counted and non-fatal, and a `triage-announcements` backfill command.

## 3. API

- [ ] 3.1 Implement radar, stack, card-state, product and deadline routes with personalisation and grouping; add every route to `API_ROUTES` with an allowlist regression test; real-database tests for ranking rules and per-reader isolation.

## 4. Web

- [ ] 4.1 Wire the radar, product and stack pages to the live API; move the list to `/news`; make briefing citations links; component, browser and axe tests on desktop and mobile.

## 5. Deliver

- [ ] 5.1 Update `docs/ui.md`, `docs/news-api.md`, `docs/enrichment.md` and the PRD-3 capability notes; run `bash scripts/check.sh --all` and `npm run spec:check`.
- [ ] 5.2 Deploy migrations, enrichment, MCP and web through azd previews; run the triage backfill; record tier distribution and cost; user checks the radar in their browser.
