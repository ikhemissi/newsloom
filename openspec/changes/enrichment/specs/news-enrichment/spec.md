# Spec Delta

## Purpose

Turn already-screened queue entries into validated summaries, primary categories,
tags and embeddings, with recoverable processing and atomic durable news writes.

## ADDED Requirements

### Requirement: Approved structured news output
Each successful enrichment SHALL produce an English summary of 2-3 sentences and
at most 100 words, one approved primary category, and 3-5 concise unique lowercase
tags. Output MUST satisfy a closed schema and MUST NOT invent facts absent from
the source. Invalid, refused, truncated or incomplete results MUST NOT publish
news or complete queue work.

#### Scenario: A valid entry is enriched
- **WHEN** the configured model returns a complete result conforming to the contract
- **THEN** the summary, category and tags are validated before embedding or publication
- **AND** the original source identity, URL, title and publication attribution remain intact

#### Scenario: Output is outside the contract
- **WHEN** a result has extra fields, an unknown category, invalid tags, excessive
  length, a refusal, or an incomplete provider response
- **THEN** it is recorded as an explicit failed attempt without publishing partial news
- **AND** no guessed category, accepting fallback, or unapproved repair-model call is used

### Requirement: Fixed primary category taxonomy
The approved primary categories SHALL be Regulations, Models, Agents &
Applications, Developer Tools, Infrastructure, Research & Evaluations, Security &
Safety, Governance, Industry & Business, Service Providers, and FinOps.
Every news item MUST use exactly one stable category identifier chosen by its
main subject, not by publisher identity or untrusted instructions.

#### Scenario: Laws and regulatory requirements are reported
- **WHEN** an article's central event is a binding law, regulatory rule, or enforcement action
- **THEN** its primary category is Regulations
- **AND** Regulations is distinct from technical AI-agent and AI-gateway governance

#### Scenario: AI-agent governance or AI gateways are the main subject
- **WHEN** an article primarily concerns AI-agent governance or AI gateways,
  including model/tool access policies, approval flows, enforcement or auditability
- **THEN** its primary category is Governance
- **AND** technical governance is not classified as Regulations merely because
  it enforces policies

#### Scenario: Commercial and technical subjects overlap
- **WHEN** the main subject concerns AI cost allocation, spend control or cost optimization
- **THEN** FinOps takes precedence over a generic commercial classification
- **AND** managed-provider offerings use Service Providers, underlying compute or
  deployment architecture uses Infrastructure, and funding/deals use Industry &
  Business when those are the main subject

### Requirement: Isolated untrusted model processing
Enrichment SHALL use one structured generation request and one embedding request
per successful logical attempt, apart from bounded transport retries. Each entry
MUST be supplied as untrusted data separately from trusted task instructions,
without shared article conversation history, tools, URL fetching, secrets, or
authority to change queries, configuration, or trusted metadata.

#### Scenario: Source content requests a different task
- **WHEN** title, body or metadata contains role spoofing, verdict manipulation,
  disclosure requests or an instruction disguised as a research example
- **THEN** those strings remain source data rather than trusted instructions
- **AND** the model cannot invoke tools or alter the stored source identity or category list

### Requirement: Validated search embeddings
Every published news item SHALL include a nonzero 1536-dimensional embedding of
its title, validated summary and selected metadata using the configured embedding
deployment. Every component MUST be finite numeric data, excluding booleans.
Invalid embeddings MUST prevent atomic publication; vector storage and the
cosine-similarity index belong to the existing PostgreSQL database.

#### Scenario: Embedding validation fails
- **WHEN** a response is missing, has the wrong length, contains invalid numbers,
  or is a zero vector
- **THEN** no news item is published and its queue attempt fails explicitly
- **AND** no placeholder vector, silent truncation or different model is substituted

### Requirement: Fenced recoverable queue processing
Workers SHALL claim only accepted eligible queue entries in short transactions,
using nonblocking row claims and expiring fenced ownership. States MUST distinguish
pending, processing, completed, failed and dead-letter work. Retries MUST be finite
and scheduled; expired ownership MUST be recoverable, and stale workers MUST NOT
complete or fail another worker's claim.

#### Scenario: Concurrent or restarted workers claim work
- **WHEN** workers overlap or a worker exits after claiming an entry
- **THEN** active claims do not overlap, expired claims can be reclaimed, and
  attempt limits eventually terminate exhausted work rather than orphaning it
- **AND** model calls do not hold a database transaction or row lock open

#### Scenario: A stale worker returns after ownership changed
- **WHEN** the old worker attempts to persist a result after its lease expired or was replaced
- **THEN** its ownership check fails and none of its news or completion writes commit

### Requirement: Atomic news completion
Validated news, embedding and completion of its owned queue item SHALL commit in
one transaction, idempotently by queue identity and source identity or full URL.
Completed queue identities MUST remain known to ingestion. Quarantined entries
MUST NOT be claimed, released, deleted or published by enrichment.

#### Scenario: Completion is interrupted or repeated
- **WHEN** a process fails during persistence or completed work is encountered again
- **THEN** news and queue completion both commit or both roll back
- **AND** retry does not publish duplicates or lose ownership of unfinished work

### Requirement: Bounded independently executable enrichment
The enrichment job SHALL use the existing workload identity and platform, support
immediate manual execution, and process at most 25 entries per execution within
finite request and job deadlines. Only after acceptance SHALL it run every
30 minutes in UTC. Unfinished work MUST remain recoverable rather than be
silently completed to meet a deadline.

#### Scenario: Initial verification is requested
- **WHEN** the operator starts the first real smoke execution immediately
- **THEN** it processes at most 10 live eligible entries, not the whole backlog
- **AND** there is no dependency on developer database/model grants or waiting for cron

#### Scenario: Deadline or quota prevents further work
- **WHEN** requests are throttled, retry budgets expire, or insufficient job time remains
- **THEN** work stops with explicit partial/failure counts and recoverable queue state
- **AND** the worker does not weaken output validation, add capacity, or exceed its item cap

### Requirement: Evidence-gated enrichment acceptance
Rollout SHALL require 20 frozen labelled quality cases, all yielding schema-valid
outputs and at least 18 matching their primary-category labels, plus zero
successful instruction overrides in separate hostile fixtures. Missing cases,
incomplete inference or unmet expectations MUST block rollout. Evaluation fixtures
MUST NOT be published as production news.

#### Scenario: The quality and hostile sets are evaluated
- **WHEN** the fixed prompt, taxonomy and configured models are evaluated
- **THEN** evidence records actual case counts, category/schema outcomes and
  hostile-fixture results without using the holdout to revise its own labels
- **AND** English, sentence/word limits, tag quality and source-fact expectations
  are checked, not inferred from JSON validity alone

#### Scenario: The service explicitly filters a hostile jailbreak request
- **WHEN** a hostile fixture receives HTTP 400 with the service's confirmed
  content-filter code, responsible-AI policy violation and detected/filtered
  jailbreak flags
- **THEN** it counts as an explicit upstream safety block, separately from a
  valid generated response and without publishing or inventing an embedding
- **AND** unknown or malformed HTTP 400 responses remain errors, and a block on
  a benign quality case cannot satisfy that case's required valid output

#### Scenario: Real persistence and recovery are verified
- **WHEN** local checks pass and the real 10-entry Azure smoke run completes
- **THEN** independent readback proves nonzero valid news with matching completed
  queue entries, correct embedding dimensions and no duplicate identities
- **AND** rerun, concurrent-claim and crash-recovery evidence is retained at the
  local and Azure boundaries actually exercised

### Requirement: Private observable enrichment
Diagnostics SHALL expose correlated identifiers, queue-state and result counts,
model latency and token usage through authenticated telemetry. Article text,
prompts, model completions, credentials and arbitrary provider error bodies MUST
remain absent from logs and traces. Safe errors MUST distinguish failed work
from successful publication.

#### Scenario: Success and failure paths are observed
- **WHEN** generation, embedding, persistence, throttling or ownership failure is exercised
- **THEN** safe categories and counts agree with committed database state
- **AND** captured output excludes content, prompt, completion and credential canaries

### Requirement: Migration-owned enrichment privileges
Versioned migrations SHALL evolve the queue and create news storage without
replacing existing ingestion data or editing applied migration checksums. The
enrichment identity MUST have only its required queue/news privileges and
configured inference, registry-pull and telemetry access, without quarantine
access, runtime DDL, administrator roles or registry push.

#### Scenario: The enrichment schema is introduced or replayed
- **WHEN** the migration identity applies the new migration and reruns it
- **THEN** existing feed/queue/quarantine rows remain intact and work is not duplicated
- **AND** the real enrichment identity can perform its domain operations while
  forbidden quarantine and administrative operations remain denied
