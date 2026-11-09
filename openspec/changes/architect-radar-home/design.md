# Design

## Context

See proposal.md (Why). Announcements, entities and links exist (migration 011;
insert-only for enrichment, select for MCP). The news API runs in the MCP app
with delegated `news.read`, a per-route telemetry allowlist (`API_ROUTES`) and
the feedback pattern for per-reader writes (`reader_hash`, object-ID check).
The web app is one `App.tsx` with a hand-written router (`navigation.ts`), the
`BriefingPanel` with focus-only citation buttons, and the research panel.

## Goals / Non-Goals

**Goals:** a useful default page from existing data, cheap triage, per-reader
state with the same privacy model as feedback, reviewable product matching.

**Non-Goals:** conversations (separate change), push notifications, admin
editing of the graph.

## Decisions

- **Separate triage call, not part of extraction.** Triage needs only derived
  data, can be re-run when the policy changes, and keeps extraction's schema
  stable. One call per item rates all its announcements together (consistent
  relative tiers). Rubric: `act_now` = security issue, retirement/deprecation
  or breaking change with a deadline within 90 days, regulation in force, or a
  GA of a widely used platform capability; `later` = case studies, opinion,
  tutorials, minor SDK/CLI releases; else `worth_knowing`.
- **Personalisation by rules in SQL**, from stack membership via
  `announcement_entities`/`entities.vendor_id`.
- **Storage (migration 012):** `announcements` gains nullable `tier`, `reason`,
  `capability`, `triaged_at`; enrichment gets `UPDATE (tier, reason, capability,
  triaged_at)` only. `reader_stack(reader, entity_id)` and
  `reader_card_state(reader, announcement_id, state done|snoozed,
  snoozed_until, updated_at)`; MCP gets select/insert/update/delete on these two
  only. Reader key reuses `reader_hash` (same pseudonym as feedback).
- **Routes:** `GET /api/v1/radar?window=7|30`, `GET|PUT /api/v1/me/stack`,
  `PUT /api/v1/me/cards/{announcement_id}`, `GET /api/v1/products?query=`,
  `GET /api/v1/products/{id}`, `GET /api/v1/deadlines`. All added to
  `API_ROUTES` with a regression test that every routed path is allowlisted
  (the 500 found in feedback acceptance). Reader routes are never cached;
  radar is not cached because it is per reader.
- **Grouping:** same tier, normalised capability, two or more distinct vendors
  in the window.
- **Web:** `/` radar, `/news` list, `/news/{id}` detail, `/products/{id}`,
  `/stack`. Cards show tier colour only for "Act now". TL;DR markers become
  links to the citation URL.
- **Mock-up first:** a local triage preview over the recorded
  `.cache/announcement-preview` week produces a fixture; the radar page is
  built against that fixture with the web test harness and reviewed by the
  user in a local browser before API/storage work.

## Risks / Trade-offs

- [Model over-rates urgency] → rubric with examples, measured distribution in
  the preview (target: "Act now" under 10% of a week), user review.
- [Reader data is personal preference data] → pseudonymous key, no names,
  per-reader access only, documented; no logging of stack contents.
- [Hidden-only-for-me mistakes] → Done/Snooze are reversible from a "Hidden"
  filter on the radar.
- [Route move breaks bookmarks to `/`] → `/` stays the signed-in home; old item
  URLs unchanged.

## Migration Plan

Preview and mock-up, then migration 012 and triage in enrichment, backfill
triage, deploy MCP then web. Rollback: redeploy previous images; new columns
and tables are unused by old code.

## Open Questions

None blocking.
