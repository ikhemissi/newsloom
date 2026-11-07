# Proposal

## Why

A news item is the wrong unit for an architect. One roundup can carry 20
announcements, the same launch appears in several posts, and product names vary
("Azure AI Foundry" vs "Microsoft Foundry", "AgentCore" vs "Amazon Bedrock
AgentCore"). Summaries of 2-3 sentences cannot list a roundup's contents, and
pure vector search returned unrelated items for "agentcore". The planned radar
home page, follow-up suggestions and agent context all need announcements linked
to the products and vendors they concern.

## What Changes

- Enrichment also classifies each item's **article kind** (announcement,
  roundup, security, retirement, regulation, case study, opinion, tutorial,
  other) and extracts up to 30 **announcements**: a short statement, change type,
  status (preview, GA, retired...), effective date, deadline, and the products it
  concerns. This happens in the same model call; the summary, category and tags
  contract is unchanged.
- Grounding checks drop unsupported announcements (product not named in the
  text, implausible dates) instead of failing the whole item.
- A **product graph** in the existing PostgreSQL, as ordinary tables:
  entities (vendor, product, model, standard, regulation) with aliases and
  embeddings, announcements, announcement-to-entity links, and stated
  `part_of`/`replaces` relations with evidence. Name matching uses a curated
  alias file, normalised exact matches, then same-vendor embedding similarity;
  it never merges across vendors.
- Item detail (MCP `get_news_item` and HTTP detail) includes the item's
  announcements with canonical product names.
- Search: a query that names a known product or matches stored text ranks those
  items before purely semantic neighbours.
- Backfill: extract announcements for news from the last 30 days.

Owning slice: PRD-1 enrichment (P1-C05) and search (P1-C07), as the data
foundation for the PRD-3 radar home page. Prerequisite: `full-article-acquisition`.

Out of scope: the radar UI, follow/snooze state, cross-vendor `competes_with`
grouping and all UI beyond a plain announcement list in item detail (the
`architect-radar-home` change), re-summarising existing news, a graph extension
such as Apache AGE, new model deployments.

Decisions surfaced:
- **Cost (estimate, measured before deploy):** about 100 new items per week at
  about 5k input and 1k output tokens each: about USD 0.4 input and 0.5 output
  per week, plus small embedding cost, roughly USD 4 per month. The 30-day backfill
  (about 430 items) is about USD 2 once. Task 1.1 measures this on a real week
  locally before anything is deployed.
- **Capacity (user decision 2026-11-07):** raise the existing enrichment
  deployment from 10 to 100 capacity units (100k tokens and 100 requests per
  minute) through the application layer's `ENRICHMENT_CAPACITY`. Data Zone
  quota for this model in France Central had 120 of 1,000 units used. Billing
  stays per token, so cost is unchanged; the 30-day backfill drops from about
  9 hours to about 30 minutes. Token-aware admission stays as a safeguard.
- **Graph storage:** relational tables with recursive queries, not a graph
  extension; our queries are one or two hops over thousands of nodes.

## Capabilities

### New Capabilities

- `news-announcements`: article kind, announcement extraction and grounding,
  entity resolution, product graph storage, exposure in item detail, backfill.

### Modified Capabilities

- `news-search`: entity- and text-aware ranking before semantic neighbours.
- `mcp-serving`: item detail includes announcements.

## Impact

- `ENRICHMENT_CAPACITY` 10 → 100 on the existing deployment (application layer).
- Migration `010_announcements.sql` (tables, `news.article_kind`, grants:
  enrichment insert/select, MCP select).
- `services/enrichment` (schema, prompt, grounding, resolution, backfill
  command), `services/mcp` (detail, search), `services/web` types if the
  detail panel shows announcements (minimal list).
- `config/entities.json` curated aliases; `docs/enrichment.md`,
  `docs/news-api.md`; capability notes in PRD-1/PRD-3.
