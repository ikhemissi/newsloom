# briefing-history Specification

## Purpose
Keep every published daily briefing, including its TL;DR, so past briefings can be
evaluated, compared and referenced by reader feedback.

## Requirements

### Requirement: Append-only briefing history
Every published briefing artifact SHALL be appended to a history keyed by its
version, in the same transaction as publication. History rows SHALL never be
updated or deleted by the briefing writer, and readers SHALL keep seeing only the
current briefing.

#### Scenario: A daily or revised briefing is published
- **WHEN** the scheduled run or a guarded revision publishes a briefing
- **THEN** the current briefing is replaced as today and the same artifact is
  appended to the history with its version, cutoff, policy and publication time
- **AND** the writer cannot update or delete history rows

#### Scenario: Publication fails
- **WHEN** generation or publication fails
- **THEN** no history row is added and the existing history is unchanged

### Requirement: Backfill of retained briefings
The migration SHALL backfill the history from the current briefing and from prior
payloads kept by guarded revision audits, without duplicating versions.

#### Scenario: Migration runs on the existing database
- **WHEN** the history migration is applied
- **THEN** the current briefing and every audited prior briefing appear once each
