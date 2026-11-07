# Spec Delta

## Purpose

Turn stored news into grounded announcements linked to the products and vendors
they concern, as the data foundation for triage, follow-ups and agent context.

## ADDED Requirements

### Requirement: Article kind and grounded announcements
Each successful enrichment SHALL also record one article kind from a fixed set
and zero to 30 announcements. Each announcement SHALL have a statement of at
most 40 words, a change type, a status from a fixed set, an optional effective
date and deadline, and one to five product mentions with their vendor. The
existing summary, category and tags contract is unchanged.

#### Scenario: Fixed sets
- **WHEN** an article kind or status is recorded
- **THEN** the kind is one of announcement, roundup, security, retirement,
  regulation, case_study, opinion, tutorial, other, and the status is one of
  announced, preview, ga, updated, deprecated, retired, none

#### Scenario: A roundup lists many changes
- **WHEN** an entry's text lists several product changes
- **THEN** the item is recorded as a roundup with one announcement per supported change,
  each linked to the products it names

### Requirement: Announcement grounding
Announcements MUST come only from the supplied entry. An announcement whose
product mentions do not appear in the entry title or text, or whose dates are
not valid calendar dates within two years of publication, SHALL be dropped and
counted; the rest of the item is still published.

#### Scenario: The model invents an announcement
- **WHEN** an announcement names a product absent from the entry or an impossible date
- **THEN** that announcement is dropped with a fixed category count and the item and its
  other announcements are published

#### Scenario: Opinion with no change
- **WHEN** an entry announces nothing (for example an opinion piece)
- **THEN** it is published with its article kind and zero announcements

#### Scenario: Output violates the schema
- **WHEN** the article kind or an announcement field is outside the closed schema
- **THEN** the attempt fails like any other invalid enrichment output and nothing is published

### Requirement: Conservative entity resolution
Product and vendor mentions SHALL resolve to canonical entities by, in order: a
curated alias list, a normalised exact match on known names and aliases, then
embedding similarity to an existing entity of the same vendor above a fixed
threshold; otherwise a new entity is created. Mentions MUST NOT be merged across
different vendors automatically. Each link SHALL record its resolution method.
Curated aliases override automatic matches.

#### Scenario: Known alias
- **WHEN** a mention reads "Azure AI Foundry" and the curated list maps it to "Microsoft Foundry"
- **THEN** it links to the existing "Microsoft Foundry" entity with method `curated`

#### Scenario: Similar names from different vendors
- **WHEN** two vendors announce products with similar names
- **THEN** they remain separate entities

### Requirement: Relational product graph
Announcements, entities, aliases, announcement-to-entity links and stated
relations (`part_of`, `replaces`) with their evidence announcement SHALL be
stored in the existing database through a migration, readable by the MCP
service and writable only by enrichment. Deleting nothing is required for
normal operation; rows are append-only except for adding aliases.

#### Scenario: Product timeline
- **WHEN** a reader asks what changed for a product since a date
- **THEN** its announcements across all sources are retrievable in date order
  from the stored graph

### Requirement: Bounded announcement backfill
An explicit operator command SHALL extract announcements for news published in
the last 30 days that have none, using the stored entry text, without changing
existing summaries, categories or tags. It SHALL respect the model token budget
per run and be idempotent.

#### Scenario: Backfill is re-run
- **WHEN** the backfill runs twice
- **THEN** the second run makes no model calls for items already extracted
