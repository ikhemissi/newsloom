# Spec Delta

## Purpose

Find stored enriched news by meaning and metadata while preserving caller filters,
bounded inference and measurable retrieval quality.

## ADDED Requirements

### Requirement: Combined metadata search
`search_news(query?, source?, category?, tags?, from?, to?, limit)` SHALL support
semantic, metadata-only and combined requests over stored news. Source/category
filters MUST match exact stable IDs; tags MUST match all requested normalized
tags. Limits MUST default to 10 and accept only integers 1-50. User values MUST
remain parameters, never SQL identifiers or expressions.

#### Scenario: Several filters are combined
- **WHEN** valid source, category and tag constraints are supplied together
- **THEN** every result satisfies every supplied constraint, with all requested
  lowercase/whitespace-normalized tags present
- **AND** source/category labels are not silently substituted for IDs or broadened

#### Scenario: No semantic query is supplied
- **WHEN** the request omits `query`
- **THEN** matching metadata rows are ordered by newest publication and stable ID
- **AND** no query embedding or generation call is made, even when the filter set is empty

#### Scenario: Search input is invalid or unmatched
- **WHEN** a supplied query is blank, a category is unknown, a limit is invalid,
  or any field exceeds its defined bound
- **THEN** the request returns an explicit input error without model or database work
- **AND** a syntactically valid unmatched source/tag yields an empty result,
  not a relaxed or fallback query

### Requirement: Precise publication date filtering
All dates SHALL be timezone-aware timestamps normalized to UTC. `since` and
`from` lower bounds MUST be inclusive; `to` MUST be exclusive. Reversed or equal
search date bounds and malformed/naive dates MUST fail explicitly, not be guessed
or silently reordered.

#### Scenario: Publication times are at the interval boundaries
- **WHEN** matching news is published exactly at `from` or `to`
- **THEN** the lower-bound item is included and the upper-bound item is excluded
- **AND** equivalent timestamps in different offsets produce the same interval

### Requirement: Validated query embeddings
A nonempty semantic query SHALL use the existing embedding deployment at the
same dimensions and compatible model configuration as stored news. Exactly 1536
finite non-boolean numeric components with nonzero norm MUST be established before
vector search. Errors, unavailability or model mismatch MUST NOT silently turn a
semantic request into metadata-only results or change models.

#### Scenario: The query is embedded successfully
- **WHEN** the configured deployment returns a valid compatible query vector
- **THEN** it is used for cosine comparison without an enrichment or chat-model call
- **AND** the user's access token is not forwarded to inference

#### Scenario: Inference cannot supply a usable vector
- **WHEN** the request is unauthorized, throttled beyond budget, timed out or
  receives malformed/wrong-length/nonfinite/zero data
- **THEN** search returns a safe operational error rather than fabricated,
  partially ranked or silently fallback results

### Requirement: Filtered cosine ranking
Semantic search SHALL rank only rows satisfying all metadata/date constraints,
using descending cosine similarity with a stable ID tie-breaker and no arbitrary
similarity cutoff. The result MUST NOT be formed by globally truncating candidates
before applying caller filters. A valid request with enough matches MUST not
silently underfill solely because approximate search discarded filtered rows.

#### Scenario: Global neighbors conflict with a narrow filter
- **WHEN** globally similar items fall outside the requested constraints
- **THEN** eligible items are ranked within the constrained set and no ineligible item appears
- **AND** tests exercise selective filters where global-top-k-then-filter would fail

#### Scenario: Scores are returned
- **WHEN** a semantic request succeeds
- **THEN** each returned stored-news record includes a finite cosine similarity
  score, not a calibrated relevance probability
- **AND** metadata-only responses do not invent similarity scores

### Requirement: Frozen evidence-based retrieval quality
Acceptance SHALL use 20 frozen labelled queries over an isolated authored corpus,
with filtered and unfiltered groups scored separately. Each group MUST achieve
mean recall@5 of at least 0.80, with zero filter violations. Evaluation MUST use
the production embedding and search path without publishing fixture news.
Missing cases, model errors or unmet gates MUST block retrieval acceptance.

#### Scenario: Labelled retrieval is measured
- **WHEN** the fixed corpus/query relevance labels are evaluated with real embeddings
- **THEN** evidence records both group denominators, per-query relevant/retrieved
  identity sets, recall scores and filter checks
- **AND** only relevant eligible corpus items count toward a filtered query's denominator

#### Scenario: A real evaluation uses the existing database
- **WHEN** the migration identity prepares the explicitly approved isolated
  schema for evaluation-only read access
- **THEN** only authored fixture projections and vectors are staged there,
  production news/queue/quarantine rows are untouched, and cleanup removes the
  temporary schema and grant on success or failure
- **AND** the public serving tools cannot access the evaluation relation

#### Scenario: Evaluation fails or live data changes
- **WHEN** a group misses its recall gate, a case is incomplete, or a filter is violated
- **THEN** acceptance remains blocked instead of dropping cases, relabelling them
  after inference or reporting empty results as success
- **AND** changing live news does not replace the frozen evaluation corpus or labels
