# Proposal

## Why

The home page is a newest-first list of hundreds of items. After the
announcement graph, Newsloom knows what changed, for which product and by when,
but the reader still has to scan everything. The user's review asked for a view
that shows at a glance what needs action, what is worth knowing and what can
wait, and noted that TL;DR citations are not clickable and the briefing leans
towards one vendor.

## What Changes

- **Model triage of announcements.** A second, small model call per enriched
  item rates each announcement for an AI solution architect: `act_now`,
  `worth_knowing` or `later`, with a reason of at most 20 words and a short
  capability topic (for example "browser automation"). It reads only stored
  derived data (title, summary, article kind, statements, products), not the
  article text. A bounded backfill triages existing announcements.
- **My stack and card state, stored on the server.** Readers pick vendors and
  products they care about; cards can be marked Done or Snoozed (7 days);
  Follow adds a card's products to My stack. Stored per pseudonymous reader,
  using the same reader key as feedback.
- **Radar API** on the existing news API: ranked announcements for a window,
  My stack read/write, card state, product search, a product timeline and
  upcoming deadlines. Same `news.read` delegated access; per-reader routes need
  the caller's object ID.
- **Personalisation rules** on top of the model tier: with My stack set,
  `act_now` stays only for stack products, security and regulation; others
  move to `worth_knowing`; stack items sort first within a tier.
- **Radar home page** at `/`: the briefing as a header with clickable TL;DR
  citations that open the source, then "Act now", "Worth knowing" and "When
  you have time" (collapsed), a deadlines strip, cross-vendor groups for the
  same capability, and product pages (`/products/{id}`) with their timeline.
  The current list moves to an "All news" tab (`/news`); item pages keep their URLs.
- **Mock-up first:** a local, clickable version on real recent announcements
  is reviewed by the user before the API and storage are built.

Owning slice: PRD-3 reader experience, after `announcement-graph`. The
conversation panel and agent memory are the separate `research-conversations`
change.

Out of scope: notifications or e-mail, sharing state between readers, editing
announcements, a graph extension, changing the daily briefing's generation.

Decisions surfaced:
- **Ranking:** model-rated tiers (user decision 2026-11-09), personalised by
  fixed rules so the model cost is per item, not per reader.
- **State storage:** server-side (user decision), insert/update/delete by the
  MCP identity only on the two new reader tables.
- **Cost (estimate, measured in the mock-up task):** about 1.5k input and 400
  output tokens per item on the existing enrichment deployment: about USD 0.10
  per week; triaging the existing 473 items about USD 0.50 once.
- **Capacity/region:** existing France Central deployments; no new resources,
  identities or models. New database grants only.

## Capabilities

### New Capabilities

- `architect-radar`: announcement triage, reader stack and card state,
  radar/product/deadline API, radar home page with clickable briefing citations.

### Modified Capabilities

None (the news list and item detail keep their contracts; the list moves to `/news`).

## Impact

- Migration `012_radar.sql`: triage columns on `announcements` (UPDATE grant for
  enrichment limited to them), `reader_stack`, `reader_card_state`, grants.
- `services/enrichment` (triage call, job, backfill), `services/mcp` (routes,
  repository, telemetry `API_ROUTES`), `services/web` (routes, radar page,
  product page, stack editor, briefing header).
- Docs: `docs/ui.md`, `docs/news-api.md`, `docs/enrichment.md`, PRD-3 capabilities.
