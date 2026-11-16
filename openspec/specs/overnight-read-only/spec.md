# overnight-read-only Specification

## Purpose
Keep Newsloom readable from a read snapshot, refreshed during the day, while the database sleeps or is unreachable, with
actions that need the database clearly unavailable.

## Requirements

### Requirement: Read snapshot refreshed during the day
The system SHALL refresh the read snapshot every 30 minutes from 07:15 to
22:45 UTC, five minutes after each scheduled ingestion and enrichment start,
so the latest snapshot before the nightly database stop is written at 22:45
UTC.

#### Scenario: The snapshot job runs
- **WHEN** the job runs at a quarter past or a quarter to the hour between
  07:15 and 22:45 UTC
- **THEN** it replaces the latest snapshot and logs only counts

#### Scenario: The API is serving from the snapshot
- **WHEN** a refreshed snapshot replaces the latest one
- **THEN** the API serves the refreshed data after its next ETag check, without
  a restart

### Requirement: Read snapshot contents and access
The snapshot SHALL contain news items with details and announcements, radar
cards of the last 30 days, their product pages, the current briefing and each
reader's stack and card states keyed by the existing pseudonymous reader key.
It MUST NOT contain embeddings, tokens or article bodies, and access MUST use
the MCP managed identity with Entra only.

#### Scenario: A snapshot is written
- **WHEN** the snapshot job writes the latest snapshot
- **THEN** it contains the listed read data and no embeddings, tokens or
  article bodies

### Requirement: Read-only serving without the database
When the database cannot be reached, the API SHALL serve the radar, briefing,
news list and filters, item detail, sources and product pages from the latest
snapshot, with each reader's own stack and card states applied, and mark every
response with `X-Newsloom-Read-Only` carrying the snapshot time.

#### Scenario: A reader opens the radar at night
- **WHEN** the database is stopped and a snapshot exists
- **THEN** the reader receives their personalised radar from the snapshot with
  the read-only header

#### Scenario: The database returns
- **WHEN** the database answers again after the remembered failure expires
- **THEN** responses come from the database without the read-only header

### Requirement: Explicit read-only failures and fast fallback
Search, research tools, feedback and reader-state changes SHALL fail with
`503 read_only` while serving from the snapshot. A connection failure MUST be
remembered so later requests do not wait for connection timeouts, and
readiness MUST succeed while a snapshot is loaded.

#### Scenario: A reader tries to change state at night
- **WHEN** they mark a card done, follow a product, search or send feedback
- **THEN** the API answers `503 read_only` and nothing is stored

### Requirement: Clear read-only browser state
While responses carry the read-only header, the browser SHALL show one line
stating that Newsloom is read-only until 08:00 and the data time, and hide
search, research, feedback and reader-state actions.

#### Scenario: The site is opened at night
- **WHEN** the first API response carries the header
- **THEN** the line appears and the hidden actions are not offered
