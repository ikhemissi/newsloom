## RENAMED Requirements

- FROM: `### Requirement: Nightly read snapshot`
- TO: `### Requirement: Read snapshot refreshed during the day`

## MODIFIED Requirements

### Requirement: Read snapshot refreshed during the day
The system SHALL refresh the read snapshot every 30 minutes from 07:15 to
22:45 UTC, five minutes after each scheduled ingestion and enrichment start,
so the latest snapshot before the nightly database stop is written at 22:45
UTC. The snapshot SHALL contain news items with details and announcements,
radar cards of the last 30 days, their product pages, the current briefing and
each reader's stack and card states keyed by the existing pseudonymous reader
key. It MUST NOT contain embeddings, tokens or article bodies, and access MUST
use the MCP managed identity with Entra only.

#### Scenario: The snapshot job runs
- **WHEN** the job runs at a quarter past or a quarter to the hour between
  07:15 and 22:45 UTC
- **THEN** it replaces the latest snapshot and logs only counts

#### Scenario: The API is serving from the snapshot
- **WHEN** a refreshed snapshot replaces the latest one
- **THEN** the API serves the refreshed data after its next ETag check, without
  a restart
