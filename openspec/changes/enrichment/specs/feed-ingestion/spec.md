# Spec Delta

## MODIFIED Requirements

### Requirement: Content-free ingestion visibility
Ingestion SHALL emit correlated, allowlisted feed outcomes, entry/duplicate/filter
counts, accepted/security-rejected/malformed-rejected/deferred counts, recovery
paths, queue depth and timings through structured diagnostics and authenticated
telemetry. Raw URLs, publisher GUIDs, article content, model payloads and
credentials MUST NOT be logged. Pending-depth readbacks MUST exclude retained
completed queue history and distinguish other processing states.

#### Scenario: Success and failure are inspected
- **WHEN** the operator inspects job output and telemetry for a run
- **THEN** safe source IDs, correlation, counts, timings, and failure categories
  distinguish retrieved, skipped, filtered, failed, and persisted work
- **AND** content/credential canaries are absent

#### Scenario: Enrichment has completed accepted queue entries
- **WHEN** completed queue rows remain stored for source/GUID and URL deduplication
- **THEN** ingestion and operator pending-depth counts include only pending rows,
  while processing, retryable failure, completed and dead-letter counts remain distinct
- **AND** retained completed identities do not become new ingestion work
