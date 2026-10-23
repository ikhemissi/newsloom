# feed-ingestion Specification

## Purpose

Retrieve configured RSS and Atom sources safely and store screened entries
idempotently, with observable manual and scheduled execution in the existing platform.

## Requirements

### Requirement: Catalogue-driven source selection
Ingestion SHALL use the existing validated catalogue as its source of truth,
support RSS and Atom, and allow explicit source-ID selection. Publisher category
filters MUST split comma-separated terms, trim whitespace, and use
case-insensitive exact matches rather than substring matches.

#### Scenario: A filtered source is ingested
- **WHEN** a source has configured category terms
- **THEN** only entries with a matching publisher term proceed to screening,
  and filtered entries are counted without being treated as rejected content

#### Scenario: A smoke-test subset is selected
- **WHEN** the operator selects one configured RSS source and one configured Atom source
- **THEN** only those sources are fetched, and an unknown source ID fails explicitly

### Requirement: Protected public feed retrieval
Feed and robots requests SHALL use verified HTTPS and public addresses only,
pin validated DNS answers for each request and redirect, and honor robots.txt.
Redirects, URL credentials, non-public destinations, and DNS changes MUST NOT
bypass these restrictions.

#### Scenario: A destination is unsafe
- **WHEN** a request, redirect, or resolved address targets a prohibited destination
- **THEN** retrieval fails before contacting that destination and reports a safe category

#### Scenario: Robots policy cannot authorize retrieval
- **WHEN** robots.txt denies the feed path or its retrieval has a transient failure
- **THEN** the feed is not fetched; transient failures remain retryable
- **AND** an explicitly missing robots.txt is distinguished from a retrieval error

### Requirement: Bounded retrieval and processing
Ingestion SHALL enforce the approved byte, concurrency, request, feed, and job
budgets, including decompressed bodies, redirects, retries, entries, and normalized
text. Exhausting a budget MUST produce an explicit outcome, not unbounded work
or a truncated feed falsely treated as fully processed.

#### Scenario: A configured boundary is reached
- **WHEN** body size, redirect count, entry count, concurrency, or elapsed work
  reaches its configured limit
- **THEN** tests prove the exact boundary behavior, resources are released, and
  exceeding a hard limit cannot advance the source as successfully processed

#### Scenario: A publisher requests a delayed retry
- **WHEN** a retryable response includes Retry-After beyond the remaining budget
- **THEN** ingestion defers that work rather than sleeping beyond the deadline
  or silently ignoring the publisher's delay

### Requirement: Safe consistent normalization
Parsing SHALL reject DTDs and entities and normalize source ID, GUID when supplied,
title, canonical URL, UTC published time, author, publisher categories, and bounded
plain text. Relative links MUST resolve against the document's effective base.
Normalization MUST NOT fetch article pages or treat publisher text as instructions.
Canonical entry URLs and deduplication keys MUST preserve query strings and
fragments so that distinct anchored entries are not collapsed into one item.

#### Scenario: RSS and Atom entries are parsed
- **WHEN** valid documents contain namespaced fields, relative links, or embedded HTML
- **THEN** normalized entries preserve usable metadata and readable bounded text
- **AND** a synthetic full-text feed of at least 4 MB is handled within the approved budget

#### Scenario: A document is hostile or malformed
- **WHEN** XML contains a DTD/entity declaration or cannot be safely parsed
- **THEN** the source fails with a content-free diagnostic and no misleading validator update

#### Scenario: Separate releases link to anchors on one page
- **WHEN** entries have distinct GUIDs and distinct fragment-bearing links on the same page
- **THEN** each retains its full entry URL and can be persisted independently
- **AND** repeating those entries still deduplicates by source/GUID or that full URL

### Requirement: Durable conditional-request state
Source fetch state SHALL persist in PostgreSQL. Conditional requests MUST use
previously committed validators, and `--force` MUST bypass them. New validators
MUST NOT be saved when no entries parsed or before all eligible parsed entries
have a durable accepted, rejected, or explicitly retryable disposition.

#### Scenario: A body is empty or persistence fails
- **WHEN** retrieval parses no entries or its entry writes fail
- **THEN** the new validator is not committed in a way that would suppress later retries

#### Scenario: A prior fetch is repeated
- **WHEN** a source returns not-modified, or the operator requests forced retrieval
- **THEN** not-modified uses valid prior state, while forced retrieval obtains the body
  and still preserves entry idempotency

### Requirement: Idempotent screened persistence
Ingestion SHALL persist source state, accepted pending entries, and retained
quarantine entries in the existing database. Deduplication MUST recognize
`(source, GUID)` or canonical URL across ingestion dispositions, including
concurrent or interrupted runs. Retryable screening failures MUST NOT become
accepted work or permanent rejection verdicts.

#### Scenario: An unchanged entry is encountered again
- **WHEN** a feed is fetched again, forced again, or an overlapping run is attempted
- **THEN** the database contains no duplicate entry and a recorded rejection is not
  silently converted to acceptance

#### Scenario: Ingestion is interrupted
- **WHEN** the process stops between persistence operations
- **THEN** committed entries remain, incomplete work can be retried, and source
  validators do not hide unpersisted entries

### Requirement: Independently executable ingestion job
The platform SHALL deploy a real ingestion ACA job through azd using the existing
ingestion identity and immutable image. It MUST support the approved UTC schedule
and immediate manual starts, serialize overlapping runs, and require migrations
before runtime access without granting runtime DDL or administrative privileges.

#### Scenario: A manual run is requested after deployment
- **WHEN** the operator starts the job immediately instead of waiting for cron
- **THEN** it executes the actual ingestion code and exposes a bounded terminal outcome
- **AND** a missing image, failed migration, or runtime failure cannot appear successful

### Requirement: Content-free ingestion visibility
Ingestion SHALL emit correlated, allowlisted feed outcomes, entry/duplicate/filter
counts, accepted/rejected/deferred counts, queue depth, and timings through
structured diagnostics and Entra-authenticated telemetry. Raw URLs, publisher
GUIDs, article content, model payloads, and credentials MUST NOT be logged.

#### Scenario: Success and failure are inspected
- **WHEN** the operator inspects job output and telemetry for a run
- **THEN** safe source IDs, correlation, counts, timings, and failure categories
  distinguish retrieved, skipped, filtered, failed, and persisted work
- **AND** content/credential canaries are absent

### Requirement: Direct execution and persistence evidence
Acceptance SHALL use one RSS and one Atom source for local live testing and the
full configured catalogue for the actual Azure run. The Azure job MUST be started
immediately and its writes independently read back from PostgreSQL; a configured
schedule, synthetic row, or successful fetch log alone MUST NOT satisfy acceptance.

#### Scenario: The deployed job is verified
- **WHEN** the operator starts the full-catalogue job immediately after deployment
- **THEN** evidence records actual execution status, per-source outcomes, and
  nonzero retrieved entries and model-accepted pending rows with safe database aggregates
- **AND** a repeated forced run over unchanged entries proves no duplicate writes
- **AND** unavailable publishers are reported explicitly, not hidden as successful fetches
