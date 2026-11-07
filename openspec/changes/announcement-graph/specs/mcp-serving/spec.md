# Spec Delta

## Purpose

Expose each item's announcements in item detail.

## MODIFIED Requirements

### Requirement: Stored item detail and filter discovery
`get_news_item(id)` SHALL return a stored public-news record or an explicit
not-found result for a valid absent ID. `list_sources()` SHALL return source IDs
and categories represented in stored news, with usable catalogue category labels.
Public records MUST include ID, title, summary, source, category, tags, published
time and original URL, never raw articles, vectors, tokens or private processing fields.
Item detail (MCP and HTTP) SHALL also include the item's article kind (or null
for items enriched before extraction existed) and its announcements, each with
statement, change type, status, dates and canonical product names.

#### Scenario: An item or available filter is requested
- **WHEN** an authorized caller requests a valid item ID or source/category discovery
- **THEN** results correspond to committed news and category IDs match their
  approved labels, including Governance distinct from Regulations
- **AND** newly committed news becomes discoverable without restarting the app

#### Scenario: An identifier is not a stored news item
- **WHEN** a valid UUID identifies only queue/quarantine work or no news row
- **THEN** detail returns not-found without exposing that processing state
- **AND** malformed IDs fail as invalid input rather than being interpolated into SQL

#### Scenario: A roundup is requested
- **WHEN** detail is requested for an item with extracted announcements
- **THEN** the announcements are returned in source order with canonical product
  names, and no article text is included
