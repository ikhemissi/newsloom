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
Parsing SHALL reject DTDs/entities and normalize source ID, optional GUID, title,
canonical URL, UTC published time, author, publisher categories and bounded plain
text. Relative links MUST use the effective document base. Article retrieval MUST
use the protected recovery contract, and publisher text MUST remain untrusted
data. Entry URLs and deduplication keys MUST preserve queries and fragments.

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

#### Scenario: The final HTML-parser chunk contains an ampersand
- **WHEN** an ordinary title or body ends with text such as `Research R&D`
- **THEN** normalization flushes buffered input and preserves that readable text
- **AND** it does not manufacture a missing-title failure or replacement headline

### Requirement: Durable conditional-request state
Source state SHALL persist in PostgreSQL, use committed validators and support
`--force`. New validators MUST wait for durable accounting of eligible items and
explicit malformed-drop counts. They MUST NOT advance after empty parsing,
persistence failure or unfinished transient recovery that needs the body again.

#### Scenario: A body is empty or persistence fails
- **WHEN** retrieval parses no entries or its entry writes fail
- **THEN** the new validator is not committed in a way that would suppress later retries

#### Scenario: A prior fetch is repeated
- **WHEN** a source returns not-modified, or the operator requests forced retrieval
- **THEN** not-modified uses valid prior state, while forced retrieval obtains the body
  and still preserves entry idempotency

#### Scenario: A mixed document has an unrecoverable malformed item
- **WHEN** usable siblings are durably staged and the malformed item is explicitly counted
- **THEN** that item alone is dropped and the source can save its new validators
- **AND** a document with no successfully parsed or already-durable items cannot
  advance validators solely because malformed nodes were counted

#### Scenario: A necessary article recovery is temporarily unavailable
- **WHEN** recovery encounters a timeout, retryable HTTP response or exhausted deadline
- **THEN** usable siblings remain durable, the unresolved recovery is reported as
  retryable rather than malformed or security-rejected, and validators do not hide it
- **AND** repeating the body deduplicates previously stored siblings

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

### Requirement: Item-isolated normalization failures
Ingestion SHALL drop only individual items that cannot be safely parsed or
normalized after applicable recovery and SHALL count them as malformed, not as
model rejections. Valid siblings MUST proceed independently. Whole-document XML,
size, item-count and resource boundaries MUST remain enforced.

#### Scenario: One item is malformed among valid siblings
- **WHEN** RSS or Atom contains usable items before and after a malformed item
- **THEN** both usable siblings can reach screening and persistence
- **AND** exactly the malformed item increments the malformed-rejected count

#### Scenario: The document exceeds its item limit
- **WHEN** a document exceeds the unchanged 1,000-item limit
- **THEN** it remains an explicit document failure, not a partially successful feed
- **AND** item isolation does not disable XML, entity or size protections

### Requirement: Protected single-response article recovery
Recovery SHALL use at most one article GET per item per retrieval attempt, with
verified public HTTPS, pinned DNS, robots policy and bounded bytes/time. Article
redirects MUST NOT be followed. Recovery MUST NOT execute scripts, fetch assets,
resolve remote JSON-LD contexts or navigate canonical/alternate links.

#### Scenario: An article redirects
- **WHEN** the direct article response is a redirect
- **THEN** no request is made to its Location target
- **AND** the item reports a safe recovery outcome while its usable siblings continue

#### Scenario: A destination or body violates policy
- **WHEN** an article or robots request targets a prohibited address, is disallowed,
  or exceeds its byte/time budget
- **THEN** no policy bypass or unbounded work occurs and the failure is explicit

### Requirement: Ordered missing-field recovery
For every source, ingestion SHALL preserve usable feed fields, fill missing
title/text from article JSON-LD/OpenGraph, then use bounded visible article content
from the same response. It MUST NOT generate summaries in ingestion or replace
the feed item's identity using article metadata. Recovered text MUST pass the
existing scanner before acceptance.

#### Scenario: Feed fields are sufficient
- **WHEN** an item already supplies a usable title and text
- **THEN** no article request occurs and the item uses the feed-item path

#### Scenario: Structured metadata supplies the missing fields
- **WHEN** JSON-LD/OpenGraph completes an incomplete feed item
- **THEN** usable feed fields remain unchanged and the metadata path is recorded
- **AND** no second article request or model summarization is performed

#### Scenario: Metadata lacks usable article text
- **WHEN** metadata supplies a headline but not text and the same HTML contains
  readable article content
- **THEN** ingestion combines those fields, records the article-body path and
  submits bounded publisher text to the unchanged scanner

#### Scenario: A known duplicate or filtered item is encountered
- **WHEN** identity or publisher-category information establishes that the item
  is already durable or outside the configured filter
- **THEN** it is counted accordingly without unnecessary article recovery

#### Scenario: Text recovery fails for an otherwise valid title-only item
- **WHEN** the item still satisfies the existing normalization contract but no
  additional article text can be obtained
- **THEN** the failed recovery is explicit and empty text alone does not newly
  invalidate an entry that the existing title-only contract permits

### Requirement: Persisted latest-run per-feed statistics
The existing feed catalogue row SHALL store run-correlated accepted,
security-rejected, malformed-rejected and deferred counts plus mutually exclusive
feed-item, article-metadata and article-body path counts. Statistics MUST separate
new work, duplicates, retryable recovery and screening backlog; they MUST NOT
present latest-run activity as lifetime totals.

#### Scenario: Multiple acquisition paths are used
- **WHEN** new normalized items are staged using feed fields, metadata or visible article text
- **THEN** each item contributes to exactly one path, using the deepest tier needed
- **AND** a mixed metadata/body item is not counted twice

#### Scenario: An unchanged source has deferred screening backlog
- **WHEN** the source returns 304 but previously staged entries are screened
- **THEN** its current-run decision counters reflect those actual outcomes
- **AND** its new acquisition-path counts remain zero

#### Scenario: A screening transaction rolls back
- **WHEN** a decision or its corresponding per-feed counter cannot be committed
- **THEN** both roll back together rather than reporting an uncommitted acceptance

#### Scenario: An unchanged forced run is repeated
- **WHEN** previously accepted or rejected identities are encountered again
- **THEN** duplicates are not counted as new acceptance or security rejection
- **AND** existing rejections remain quarantined without rescoring or release
