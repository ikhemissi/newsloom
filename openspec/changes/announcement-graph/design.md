# Design

## Context

See proposal.md (Why). Enrichment makes one structured generation call per item
(`Enrichment`: 2-3 summary sentences, category, 3-5 tags; strict closed schema)
and one embedding call (`text-embedding-3-large`, 1536 dimensions) before an
atomic insert into `news`. Recent volume is about 100 items per week at about
2,550 input tokens per generation call. The enrichment deployment currently
allows 10k tokens and 10 requests per minute (raised to 100 units by this change); embeddings 10k tokens/minute and 10 requests
per 10 seconds. Search (`repository.py`) ranks eligible rows by cosine only.
The briefing preview already shows the value of record/replay for model work.

## Goals / Non-Goals

**Goals:** grounded announcements per item; stable canonical products; detail and
search that use them; measured cost before deployment.

**Non-Goals:** UI beyond a minimal announcement list in item detail;
`competes_with` grouping; re-summarising news; a graph extension.

## Decisions

- **One generation call, extended schema.** Add `article_kind` and
  `announcements[]` to the closed schema. Alternative: a second call only for
  roundups; rejected because classification needs the same call and it doubles
  request count. The prompt keeps the
  untrusted-data rules and forbids external knowledge.
- **Grounding drops, not fails.** Lesson from the briefing: one bad element must
  not discard a whole item. Product mentions must appear (case-insensitive,
  whitespace-normalised) in title or text; dates must parse and fall within two
  years of publication. Dropped counts go to telemetry.
- **Entity resolution, in order:** curated aliases (`config/entities.json`,
  reviewed in PRs) → normalised exact match (casefold, punctuation and known
  vendor prefixes removed) on names and aliases of the same vendor → cosine
  similarity of "vendor: name" embeddings ≥ 0.92 within the same vendor → new
  entity. All mentions of an item are embedded in one batched request. New exact
  or similar matches add an alias. Method recorded per link.
- **Schema (migration 010):** `entities(id, kind, vendor_id, canonical_name,
  embedding, created_at)`, `entity_aliases(entity_id, alias_normalised UNIQUE per
  vendor, method)`, `announcements(id, news_id, ordinal, statement, change_type,
  status, effective_date, deadline)`, `announcement_entities(announcement_id,
  entity_id, method)`, `entity_relations(source_id, target_id, relation,
  announcement_id)`, `news.article_kind` (nullable for legacy rows). Enrichment
  gets INSERT/SELECT (and UPDATE of `news.article_kind` for the backfill only);
  MCP gets SELECT. Writes happen in the same transaction as the news insert.
- **Search tiers:** tier 1 = eligible items linked to entities matched by the
  query (normalised alias lookup) or matching `websearch_to_tsquery` over title,
  summary and statements (a GIN index on a generated tsvector); tier 2 = the
  rest by cosine. Ordering within tiers by cosine then ID; filters apply before
  ranking, as today.
- **Token-aware admission:** estimate tokens per claimed item from stored text
  size and stop claiming when the run's estimate would exceed the per-minute
  budget times the remaining deadline. Backfill uses the same admission.
- **Local preview first.** A record/replay command runs extraction over a chosen
  week of real items locally (article text acquired under the same rules,
  nothing written to Azure), prints a content-free cost/count report and writes
  a private review file of announcements for the user. Replay reruns
  resolution/search changes at no model cost.

## Risks / Trade-offs

- [Output tokens grow with roundups] → cap 30 announcements and 40 words each;
  measured in the preview.
- [Over-merging products] → same-vendor only, high threshold, curated overrides,
  method recorded so a bad merge can be found and corrected with an alias edit.
- [Entity table fills with noise] → only mentions grounded in text create
  entities; kinds limited; review of top new entities in the preview.
- [Search behaviour change] → the frozen retrieval evaluation must still pass;
  add labelled cases for product-name queries.

## Migration Plan

1. Local preview on the most recent week; user reviews announcements (including
   the Foundry October roundup) and the cost report.
2. Merge; raise `ENRICHMENT_CAPACITY` to 100 through the application layer
   (preview must show only that capacity change); apply migration 010 via the migrations job; deploy enrichment then MCP
   (previews show only images and the migration job).
3. Run the 30-day backfill in bounded runs; verify counts and detail output.
Rollback: redeploy previous images; new tables are additive and unused by old code.

## Open Questions

None blocking.
