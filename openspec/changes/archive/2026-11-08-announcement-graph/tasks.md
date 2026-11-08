# Tasks

## 1. Measure before building further

- [x] 1.1 Add the extended schema, prompt and grounding checks behind a local record/replay preview command; run it on the most recent week of real items (article text acquired locally under the acquisition rules) and record tokens, cost, announcements per kind, drops by category and new entities. User reviews the private announcement file, including the Foundry October roundup, before work continues.
  - Evidence (2026-11-08): local preview over 98 real items from the previous week: 92 extracted, 315 announcements kept, 8 dropped as unsupported, 345k input and 34k output tokens, about USD 0.45 per week (USD 3.24 in a first run was a concurrency over-count in the preview's token accounting, fixed by per-item clients). The Foundry October roundup yields 11 announcements with status and dates. A prompt fix removed invented dates ("by 2027") and customer-project announcements in case studies. The user reviewed the private review file and approved deployment; graph relations are reviewed after the backfill from the real database.

## 2. Storage and resolution

- [x] 2.1 Add migration `011_announcements.sql` (tables, `news.article_kind`, indexes, grants) with real-database tests for privileges and append-only behaviour.
- [x] 2.2 Implement entity resolution with `config/entities.json` (seeded with major vendors and known renames) and batched embeddings; tests cover curated, exact, similar same-vendor, cross-vendor separation and alias addition.
- [x] 2.3 Write announcements, links and relations in the news transaction; add token-aware admission; enrichment tests for roundups, opinion pieces, invalid output and partial grounding drops.

## 3. Read paths

- [x] 3.1 Include article kind and announcements in MCP and HTTP item detail; show them as a plain list in the web item detail panel.
- [x] 3.2 Add tiered search (entity/text match, then cosine) with a generated tsvector index; keep the frozen retrieval evaluation passing and cover product-name queries with a real-database regression (the frozen 20-query contract is not changed).

## 4. Deliver

- [x] 4.1 Add the 30-day backfill command; update `docs/enrichment.md`, `docs/news-api.md` and capability notes; run `bash scripts/check.sh --all` and `npm run spec:check`.
- [x] 4.2 Raise enrichment capacity to 100 units through the application layer (preview shows only that change; read back the rate limits), apply the migration, deploy enrichment, MCP and web through azd previews, run the backfill in bounded runs, and verify detail for the Foundry October roundup and an "agentcore" search; record measured weekly cost.
  - Evidence (2026-11-08, dev): enrichment capacity raised 10 → 100 units (preview showed only that change; readback 100 requests and 100,000 tokens per minute). Migration 011 applied by the migrations job. Agent, enrichment, MCP and web deployed in that order (agent first because it validates MCP item details); every preview changed only the image and revision marker; readbacks passed. MCP in-container access verification passed (10 database, 1 anonymous, 1 wrong-resource, 2 model and 3 app-only denials, 5 tool checks); the operator command needs a terminal for `az containerapp exec`.
  - Backfill: 473 of 475 recent items received announcements over six runs; 2 items keep failing the existing summary rules and stay without announcements. The first runs exposed `embedding_response_limit` (64 mention vectors per request exceed the shared 256 KiB response cap), fixed in #16 with six per request; affected items succeeded on later runs.
  - Live checks: the Foundry October roundup detail lists 9 announcements linked to canonical products; a search for "agentcore" returns five Amazon Bedrock AgentCore items. Known quality gap: a version string can be read as a date (Model Router "2025-11-18" stored as effective 2026-11-18). The graph is reviewed through item details; a product browsing view belongs to the radar home page.
