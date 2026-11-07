# Tasks

## 1. Measure before building further

- [ ] 1.1 Add the extended schema, prompt and grounding checks behind a local record/replay preview command; run it on the most recent week of real items (article text acquired locally under the acquisition rules) and record tokens, cost, announcements per kind, drops by category and new entities. User reviews the private announcement file, including the Foundry October roundup, before work continues.

## 2. Storage and resolution

- [ ] 2.1 Add migration `011_announcements.sql` (tables, `news.article_kind`, indexes, grants) with real-database tests for privileges and append-only behaviour.
- [ ] 2.2 Implement entity resolution with `config/entities.json` (seeded with major vendors and known renames) and batched embeddings; tests cover curated, exact, similar same-vendor, cross-vendor separation and alias addition.
- [ ] 2.3 Write announcements, links and relations in the news transaction; add token-aware admission; enrichment tests for roundups, opinion pieces, invalid output and partial grounding drops.

## 3. Read paths

- [ ] 3.1 Include article kind and announcements in MCP and HTTP item detail; show them as a plain list in the web item detail panel.
- [ ] 3.2 Add tiered search (entity/text match, then cosine) with a generated tsvector index; extend the frozen retrieval evaluation with product-name queries and keep existing gates passing.

## 4. Deliver

- [ ] 4.1 Add the 30-day backfill command; update `docs/enrichment.md`, `docs/news-api.md` and capability notes; run `bash scripts/check.sh --all` and `npm run spec:check`.
- [ ] 4.2 Raise enrichment capacity to 100 units through the application layer (preview shows only that change; read back the rate limits), apply the migration, deploy enrichment, MCP and web through azd previews, run the backfill in bounded runs, and verify detail for the Foundry October roundup and an "agentcore" search; record measured weekly cost.
