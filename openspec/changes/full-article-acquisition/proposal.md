# Proposal

## Why

Feed entries often carry only a teaser. The "What's new in Microsoft Foundry |
October 2026" item stored a 28-word teaser while its page holds 3,725 words of
actual announcements. Ingestion only opens the article when the feed lacks a
title or text, and even then it prefers the page's metadata description (the
same teaser) over the visible article text. Readers, the briefing and the agent
therefore cannot see the news the post exists to announce.

## What Changes

- **BREAKING (contract):** ingestion fetches the article page for every new,
  accepted (not filtered, not duplicate) item instead of only incomplete ones.
  Feed identity fields (title, URL, GUID, dates) stay authoritative.
- Text selection prefers the visible article body when it is substantially
  longer than the feed/metadata text; otherwise the feed text is kept. Any
  failure (robots denial, redirect, error, script-only page) falls back to the
  feed text and is counted.
- robots.txt stays mandatory. It is fetched once per host per run and cached
  for that run (RFC 9309 allows up to 24 hours) instead of once per request.
- `Content-Signal` lines in robots.txt are honoured: `ai-input=no` for our
  group skips the article fetch and the item uses its feed text only (user
  decision 2026-11-07). A feed blocked by robots.txt is still not fetched at all.
- Politeness: one request at a time per host, `Retry-After` honoured, a
  descriptive user agent with the public repository URL as contact.
- An explicit operator backfill acquires articles for items published in the
  last 14 days (about 200), under the same rules, so recent roundups benefit.
- Article text is internal model input only; it is never shown in the UI or
  APIs. Article text older than 90 days is dropped from completed queue
  entries; feed text, summaries and later extractions remain.

Owning slice: PRD-1 feed ingestion (P1-C02). Prerequisite for the
`announcement-graph` change, which extracts announcements from this text.

Out of scope: following redirects, executing scripts or headless browsers,
bypassing paywalls/sign-in, fetching pages of existing items (no backfill
fetch), showing article text to readers.

Decisions surfaced:
- **Robots audit (2026-11-07):** 40 of 41 sources allow `Newsloom` on article
  paths; Comet's feed links to a staging host that disallows all crawlers, so
  that source keeps feed text (no host rewriting). Six sites publish
  `Content-Signal`; all allow `ai-input`, one disallows `ai-train` (we never train).
- **Volume and cost:** about 100 new items per week. One extra GET per item
  plus at most one robots.txt per host per run. Model cost is covered in
  `announcement-graph`.
- **Capacity:** the 32 KiB stored text bound is kept (the 3,725-word roundup is
  24 KiB, about 5k tokens), so a single enrichment call stays below the
  enrichment deployment's 10k tokens/minute. No new capacity or resources.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `feed-ingestion`: article recovery becomes article acquisition for every new
  item, with per-run robots caching, Content-Signal handling, text selection,
  politeness and retention.

## Impact

- `services/ingestion` (job, articles, retrieval), ingestion telemetry
  categories, tests and fixtures.
- Retention runs inside the existing ingestion job; no new resource, identity,
  permission or migration (the queue `entry` already stores bounded text).
- `docs/ingestion.md`; PRD-1 capability notes.
