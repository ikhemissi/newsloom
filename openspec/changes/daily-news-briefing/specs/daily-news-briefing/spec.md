# Spec Delta

## Purpose

Give signed-in readers one shared daily five-minute overview of the preceding
week, with a summary-derived TL;DR and an expandable cited briefing.

## ADDED Requirements

### Requirement: Daily scheduled seven-day evidence window
The system SHALL start one shared briefing workflow daily at 05:00 UTC, using
committed stored news with publication instants in the half-open interval
[scheduled cutoff minus seven days, scheduled cutoff). The window MUST remain
fixed despite delayed execution, browser timezone, filters or article selection.

#### Scenario: A daily run starts late or a reader changes filters
- **WHEN** a scheduled run starts after 05:00 UTC
- **THEN** it retains that slot's 05:00 UTC cutoff, includes the lower boundary
  and excludes the upper boundary and future-dated records
- **AND** different readers, local timezones and browsing filters receive the
  same shared published version

### Requirement: Evidence-grounded weekly synthesis
The briefing SHALL consider every eligible record in a consistent stored-news
snapshot, synthesize themes and link claims to supplied original sources.
The normal English summary SHALL contain 900-1,100 words excluding citations
and TL;DR. It MUST NOT invent facts, fetch full articles or web-search, silently
sample only the latest page, or claim exhaustive real-world news coverage.

#### Scenario: The week exceeds a single generation context
- **WHEN** eligible stored news spans multiple pages or model contexts
- **THEN** all eligible records are considered through bounded processing
- **AND** exact snapshot/input counts and cited provenance are retained
- **AND** capacity or deadline failure is explicit rather than publishing
  truncated input as complete weekly coverage

#### Scenario: Evidence is empty, sparse or malicious
- **WHEN** the window is empty
- **THEN** an explicit no-news state is published without generation
- **WHEN** evidence cannot support the normal length
- **THEN** a shorter, explicitly limited briefing is permitted without padding
- **WHEN** article fields contain instructions
- **THEN** they remain untrusted data and cannot change tools, authority or task

### Requirement: Summary-derived TLDR and atomic versioning
Each nonempty briefing SHALL include one concise TL;DR paragraph derived from
the completed summary during the same daily workflow. It MUST NOT introduce
claims absent from that summary. The TL;DR, summary, citations, evidence window
and generation metadata SHALL be validated and published atomically as one
version, never combined across runs.

#### Scenario: TLDR derivation or validation fails
- **WHEN** the summary succeeds but its TL;DR fails, is incomplete or invalid
- **THEN** neither new component replaces the last good published briefing
- **AND** a reader cannot observe a new TL;DR attached to an older summary

### Requirement: Once-only daily execution and measured usage
Daily runs SHALL be durably claimed, prevent overlapping/replayed generation
and record model calls, observed tokens, latency and estimated model cost.
Unobserved usage MUST remain unknown, not zero. No daily dollar cap SHALL be
introduced in this slice; normal context, deadline and bounded-retry controls
remain. Hosting/build costs MUST be reported separately.

#### Scenario: A duplicate trigger or uncertain model completion occurs
- **WHEN** the same slot is triggered twice or a process loses its response
- **THEN** durable state prevents automatic regeneration of that slot
- **AND** consumed/uncertain operations remain accounted for without a success
  claim, hidden inference retry or reset

### Requirement: Authorized read-only access
The latest briefing and freshness status SHALL be available through the
existing HTTP news authorization boundary using delegated news.read.
Authentication and authorization MUST precede every read/cache hit. Reads,
panel opening and expansion MUST NOT trigger generation; MCP remains read-only
and the scheduler MUST NOT impersonate a signed-in user.

#### Scenario: Anonymous or unauthorized callers request a cached briefing
- **WHEN** a caller lacks the required valid delegated authorization
- **THEN** access is denied before reading any stored or cached briefing
- **AND** existing safe errors, exact-origin policy and no-store headers apply

### Requirement: Honest availability and freshness
Readers SHALL see the artifact's actual evidence window, generation time,
expected daily cutoff and latest refresh state. A pending/failed update SHALL
retain the last good version with explicit stale status. No prior version,
valid no-news result and service failure MUST be distinguishable.

#### Scenario: Initial generation or a later refresh has not succeeded
- **WHEN** no published version exists
- **THEN** the panel explains pending/unavailable status instead of fabricated
  content, and a read failure remains retryable
- **WHEN** a newer daily slot is pending or failed
- **THEN** the last good artifact remains readable with its old dates and a
  visible stale/update status, not a fresh timestamp

### Requirement: TLDR above a collapsed full briefing
The signed-in Agent panel SHALL show the TL;DR below its heading/Close action
and above research context/composer. The full summary and safe citations SHALL
be inside an accessible collapsible closed by default. Published timestamps
SHALL use browser-local offsets. This display MUST preserve research input,
answer snapshots, selection, panel scrolling and keyboard navigation.

#### Scenario: A reader opens or expands the panel
- **WHEN** the panel first opens or displays a new briefing version
- **THEN** the TL;DR is visible and the full summary starts collapsed
- **WHEN** the reader expands or collapses the summary by keyboard or pointer
- **THEN** no generation or research is dispatched and the current conversation
  state is preserved
- **AND** hostile content remains inert and citations use safe original links

### Requirement: Isolated persistence and content-free diagnostics
The scheduled writer SHALL have its own managed identity and only its required
news-read, briefing-write, model, registry-pull and telemetry permissions.
Migrations alone SHALL create schema/grants. Persisted briefing content MUST
remain in its protected application store, not logs, traces or job output;
credentials, evidence text, prompts and completions MUST NOT enter diagnostics.

#### Scenario: Real workload grants and diagnostics are exercised
- **WHEN** the writer attempts news modification or MCP attempts briefing writes
- **THEN** those operations are denied while intended publication/read succeeds
- **WHEN** successful and failing generation is observed
- **THEN** diagnostics contain only safe counts, timings, usage and categories
  without content or credential canaries
