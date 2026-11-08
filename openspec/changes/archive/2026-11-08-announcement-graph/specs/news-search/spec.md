# Spec Delta

## Purpose

Rank items that actually mention a queried product or term before purely
semantic neighbours.

## MODIFIED Requirements

### Requirement: Filtered cosine ranking
Semantic search SHALL rank only rows satisfying all metadata/date constraints.
Eligible items linked to an entity whose name or alias matches the query, or whose
title, summary or announcement statements match the query terms, SHALL rank
first, ordered by descending cosine similarity; the remaining eligible items
follow by descending cosine similarity, with a stable ID tie-breaker and no
arbitrary similarity cutoff. The result MUST NOT be formed by globally
truncating candidates before applying caller filters. A valid request with
enough matches MUST not silently underfill solely because approximate search
discarded filtered rows.

#### Scenario: Global neighbors conflict with a narrow filter
- **WHEN** globally similar items fall outside the requested constraints
- **THEN** eligible items are ranked within the constrained set and no ineligible item appears
- **AND** tests exercise selective filters where global-top-k-then-filter would fail

#### Scenario: Scores are returned
- **WHEN** a semantic request succeeds
- **THEN** each returned stored-news record includes a finite cosine similarity
  score, not a calibrated relevance probability
- **AND** metadata-only responses do not invent similarity scores

#### Scenario: A query names a known product
- **WHEN** the query is "agentcore" and items are linked to "Amazon Bedrock AgentCore"
- **THEN** those items rank before items that only resemble the query semantically
