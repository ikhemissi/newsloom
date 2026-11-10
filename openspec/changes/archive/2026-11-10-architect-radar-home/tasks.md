# Tasks

## 1. Preview and mock-up

- [x] 1.1 Add the triage schema, prompt and a local record/replay triage preview over the recorded announcement week; report tier distribution, tokens and cost.
  - Evidence (2026-11-09): triage preview over 65 items with 313 grounded announcements from the recorded week: Act now 5 (2%), Worth knowing 138 (44%), Later 170 (54%); 57k input and 11k output tokens, about USD 0.10 per week. A first rubric put 84% in Worth knowing (changelog entries); the tightened rubric defaults detail to Later and uses a shared capability vocabulary so cross-vendor groups form (for example model routing across five vendors).
- [x] 1.2 Build the radar page, product page and stack editor in the web app against a fixture client implementing the ranking rules, with component tests.
  - The pages, routes and clickable briefing citations are the production code; `FixtureRadar` remains the test double. The user chose to skip a separate mock-up review and test the live pages instead (2026-11-09); the local preview page is removed once the live API is wired.

## 2. Storage and triage

- [x] 2.1 Add migration `012_radar.sql` with real-database tests for grants (enrichment updates only triage columns; MCP manages only reader tables).
- [x] 2.2 Triage in the enrichment job after extraction, with failures counted and non-fatal, and a `triage-announcements` backfill command.

## 3. API

- [x] 3.1 Implement radar, stack, card-state, product and deadline routes with personalisation and grouping; add every route to `API_ROUTES` with an allowlist regression test; real-database tests for ranking rules and per-reader isolation.

## 4. Web

- [x] 4.1 Wire the radar, product and stack pages to the live API; move the list to `/news`; make briefing citations links; component, browser and axe tests on desktop and mobile.

## 5. Deliver

- [x] 5.1 Update `docs/ui.md`, `docs/news-api.md`, `docs/enrichment.md` and the PRD-3 capability notes; run `bash scripts/check.sh --all` and `npm run spec:check`.
- [x] 5.2 Deploy migrations, enrichment, MCP and web through azd previews; run the triage backfill; record tier distribution and cost; user checks the radar in their browser.
  - Evidence (2026-11-09/10): migration 012 applied; enrichment, MCP and web deployed through image-only previews; `verify-mcp` and `verify-ui` succeeded (MCP revision 10, web revision 17 after the group fix in #20).
  - Live bug found and fixed (#20): one card naming two vendors was sent as a one-card group and the browser rejected the radar; a contract test now runs the browser client against the real server ranking. zod JIT disabled for the CSP `eval` report.
  - Triage backfill: four runs, 464 items and 1,128 announcements triaged, 0 failed, last two runs found nothing left. Tier distribution measured in the local preview (act now 2%, worth knowing 44%, later 54%, about $0.10/week); the live distribution was not read back.
  - User checked the radar in their browser on 2026-11-10: "it looks good".
