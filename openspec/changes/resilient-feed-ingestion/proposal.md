# Proposal

## Why

One malformed item currently prevents its otherwise usable siblings from being
ingested. The live investigation also identified a normalizer EOF bug and an
item recoverable from a single article response; ingestion needs these focused
corrections and per-feed statistics rather than a new pipeline.

## What Changes

- Isolate item parsing/normalization failures and count malformed drops without
  discarding valid siblings. Preserve whole-document XML and resource protections.
- Flush the HTML normalizer at EOF so ordinary ampersand-containing titles and
  text are not incorrectly treated as empty.
- Fill missing fields from feed data first, then article JSON-LD/OpenGraph, then
  bounded article text from the same response. Permit at most one direct article
  GET for an item needing recovery, without following redirects.
- Apply that fallback to all feeds using existing public-HTTPS, DNS, robots,
  timeout and byte protections. Screen recovered publisher text normally.
- Persist latest-run per-feed accepted, security-rejected, malformed-rejected,
  deferred and acquisition-path statistics in the existing `feed_sources.counts`.
- Remove `solo-io-blog` and retain the already-configured `agentgateway-blog`:
  41 unique active sources, with historical database records preserved.
- Keep the eight existing rejected entries quarantined and leave the Decision
  question, model, threshold and rejection policy unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `feed-ingestion`: item isolation, protected article recovery, validator behavior
  and per-feed outcome/path accounting.
- `repository-foundation`: replace the initial 42-source catalogue guarantee with
  the approved 41-source catalogue after retiring the broken Solo.io entry.

The ingestion contract is delivered but still held in the completed
[feed-ingestion change](../feed-ingestion/specs/feed-ingestion/spec.md), not yet
published in main specs. This change depends on that verified baseline. Publish
its specs through the normal sync workflow before applying this delta to main
specs; do not rewrite its acceptance history or archive it implicitly.
The earlier prohibition on fetching article pages is intentionally replaced by
the narrowly bounded fallback specified here.

## Impact

This is a Phase 1 ingestion robustness follow-up to
[P1-C01 through P1-C04](../../../docs/prd-1-capabilities.md#p1-c02-safe-feed-retrieval-and-normalization),
not the enrichment slice. Prerequisites are the verified ingestion/scanner job,
the existing PostgreSQL tables and the persistent Azure foundation.

Implementation touches the ingestion parser, retrieval/orchestration, repository,
safe diagnostics/readback, catalogue and their tests. Related capability guidance,
the ingestion runbook and current catalogue references must be updated with the
implementation, not represented as delivered by this proposal.

No new service, table, model deployment, inference permission, regional capacity or
fixed-cost resource is required. The JSON counts column already exists; no schema
migration is expected. Additional article requests consume existing bounded
runtime/network budgets. Preserve the current schedule and all shared resources.

The user explicitly chose text extraction now and GPT summarization later in
[P1-C05](../../../docs/prd-1-capabilities.md#p1-c05-structured-model-enrichment-and-embeddings).
GPT summaries, generated categories/tags, embeddings, new queue lifecycle features,
scanner retuning and quarantine release are out of scope. The 1,000-item document
limit remains unchanged; OpenAI's oversized feed remains an explicit failure.
