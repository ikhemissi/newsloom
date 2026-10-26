# Spec Delta

## Purpose

Provide repeatable federated Azure integration evidence for Phase 1 without
publishing test articles, granting production test access or disturbing live jobs.

## ADDED Requirements

### Requirement: Explicit federated acceptance execution
The acceptance workflow SHALL be manually dispatched from the trusted main
revision using a dedicated GitHub-federated Entra identity trusting only this
repository's immutable owner/repository IDs and exact main-branch subject.
Explicit operator dispatch SHALL be the
approval gate, without a separate environment-review requirement. Cloud tests
MUST NOT run on pull requests or use stored credentials, personal tokens,
production identities or migration-administrator grants.

#### Scenario: A permitted operator dispatches a run
- **WHEN** an authorized operator explicitly dispatches the main-revision workflow
- **THEN** OIDC authenticates the dedicated identity and starts only the named
  immutable manual acceptance job
- **AND** the report identifies the tested source/image/configuration revisions
- **AND** no separate environment approval, repository-publication step or
  visibility change is required

#### Scenario: The caller or execution target is not approved
- **WHEN** a fork, pull request, untrusted ref, mismatched federation subject or
  foreign job target requests execution
- **THEN** the run fails before inference or database writes
- **AND** no credential, permission or deployment fallback is introduced

#### Scenario: A token identifies an environment instead of the approved branch
- **WHEN** the presented OIDC subject is an environment, wildcard, other ref,
  or other repository rather than the approved exact main-branch subject
- **THEN** the identity trust rejects it
- **AND** workflow/controller checks do not replace Azure's exact subject,
  issuer and audience validation

#### Scenario: A subject does not bind the approved immutable repository
- **WHEN** the presented subject uses the legacy name-only form or different
  owner/repository IDs, even when its repository names and main ref match
- **THEN** the dedicated credential rejects it
- **AND** no legacy credential, wildcard, extra credential or GitHub OIDC
  policy fallback is introduced to bypass exact immutable-subject validation

### Requirement: Confined disposable test data
Every run SHALL use one explicitly prepared, uniquely named test database on the
existing server. The test identity MUST NOT connect to production news data,
inherit production roles, create databases or administer the server. Cleanup
ownership MUST be confined to that prepared test database.

#### Scenario: The operator prepares an isolated run
- **WHEN** the retained migration authority prepares the exact run database
- **THEN** versioned setup establishes the normal table/vector shapes and a
  verifiable run/owner/fixture manifest without changing production grants or rows
- **AND** existing workload identities, firewall settings and schedules remain unchanged

#### Scenario: Isolation cannot be established
- **WHEN** a target is production, foreign, unprepared, incorrectly owned or
  does not match the retained run manifest
- **THEN** execution and destructive cleanup fail explicitly
- **AND** actual test-identity probes must prove production connection and
  privileged-role denial; network failure alone is not permission evidence

### Requirement: Real end-to-end fixture disposition
The frozen integration corpus SHALL contain two benign and two hostile authored
RSS/Atom items. Real deployed screening MUST accept both benign items and
quarantine both hostile items. Only accepted items may pass through real
enrichment/embeddings to stored-news queries.

#### Scenario: All four fixture items are processed
- **WHEN** the isolated run parses and screens the frozen corpus
- **THEN** exactly two identities enter accepted processing and exactly two
  hostile identities remain rejected in test quarantine
- **AND** valid stored news and 1536-dimensional vectors are produced for both
  accepted identities, with zero published hostile identities

#### Scenario: A stage fails or a fixture is misclassified
- **WHEN** inference fails, a benign item is rejected, a hostile item is accepted,
  or output/vector validation fails
- **THEN** the integration gate fails with the affected opaque case and safe category
- **AND** no fake verdict, model substitution, output repair, label change or
  reduced denominator can turn that run into success

### Requirement: Duplicate-free replay
Replaying the identical integration corpus SHALL preserve its queue/quarantine
identities and dispositions without adding duplicate records or news. Replay
MUST exercise the actual durable ingestion path rather than database seeding.

#### Scenario: The same feed documents are processed again
- **WHEN** the four frozen items are replayed with validators bypassed for the test
- **THEN** all four are recognized as known identities, no extra row is staged,
  and previously rejected items are not released or published
- **AND** final attribution and URL/GUID uniqueness checks pass

### Requirement: Genuine concurrent and interrupted work
The integration run SHALL prove distinct committed claims by overlapping workers
and actual process loss after a claim. Recovery MUST wait for the configured
natural lease, reclaim that identity on the next attempt and publish it once.
The test MUST NOT rewrite lease timestamps or add production fault-injection flags.

#### Scenario: One worker is interrupted and another progresses
- **WHEN** one real worker has committed a claim and its test process is stopped
- **THEN** another worker claims a different accepted identity and completes it
- **AND** the interrupted identity remains uncompleted until natural lease recovery

#### Scenario: The expired claim is recovered
- **WHEN** the original lease expires and the recovery worker runs
- **THEN** the same identity is reclaimed on attempt two and completes exactly once
- **AND** no processing/failed/dead-letter test work remains and no duplicate
  news identity is created

### Requirement: Stored-query and evidence parity
The completed test records SHALL be checked through the real recent/detail/
discovery and filtered semantic query implementation against independent SQL.
The phase report MUST distinguish this isolated repository-path smoke from actual
signed-in production MCP calls and from frozen model-quality studies.

#### Scenario: The accepted test records are queried
- **WHEN** browsing, detail, discovery, metadata search and semantic search run
- **THEN** IDs, attribution, represented filters, date/tag constraints and
  null-versus-finite similarity values match independently read stored data
- **AND** hostile records are absent from every news-serving result

### Requirement: Server-enforced log-only evidence access
The dedicated identity SHALL query Log Analytics using Entra and one conditional
reader assignment on the existing workspace. Azure MUST enforce exact
console-table/job/environment restrictions independently of query text.
Workspace metadata reads are permitted, but unrestricted or unrelated log data
reads and development-token/exec permissions are forbidden.

#### Scenario: The identity queries its own execution
- **WHEN** the federated controller queries the recorded acceptance execution
- **THEN** Azure permits only records inside the conditional table/row boundary
- **AND** the controller independently checks trusted execution metadata,
  prepared run and report fingerprints before accepting evidence

#### Scenario: The caller removes or changes client query filters
- **WHEN** the identity queries without filters or requests production,
  foreign-job or other-table records
- **THEN** Azure still enforces the conditional boundary and reveals no
  unrelated log data, by returning no such records or denying access
- **AND** a caller-supplied filter is never treated as an authorization boundary

#### Scenario: A conditional boundary cannot be established
- **WHEN** a required condition is missing, malformed, unsupported or bypassed
  by another read grant held by the dedicated identity
- **THEN** deployment verification and phase acceptance fail
- **AND** no unconditional reader, development-token or broader-scope fallback
  is introduced

#### Scenario: Log ingestion is delayed or evidence belongs to another execution
- **WHEN** matching records have not arrived or only stale/foreign execution
  evidence is available
- **THEN** collection retries only within the shared remaining workflow/recovery budget
- **AND** unavailable or mismatched evidence fails without changing the
  original outcome or substituting operator-authorized reads

### Requirement: Shared bounded evidence timing
The launcher SHALL share one non-resettable deadline across main and cleanup
within the unchanged 30-minute workflow. Main work, exact stop/recovery, API
calls and read-only retries MUST consume remaining time rather than restart
budgets. The 1,200-second job ceiling and natural lease SHALL remain unchanged.
Expired time or invalid evidence MUST fail closed with fixed content-free
categories and preserve the original outcome.

#### Scenario: Valid execution evidence arrives after a short terminal wait
- **WHEN** exact-run evidence arrives after the former allowance but before
  the applicable main and shared deadlines
- **THEN** the controller may accept it only after all metadata, fingerprint,
  completeness and outcome checks pass
- **AND** later-than-deadline evidence cannot retroactively pass the workflow

#### Scenario: Cleanup starts after the main operation has consumed time
- **WHEN** cleanup loads the recorded execution state
- **THEN** it reuses the original deadline and prepared-run/workflow bindings
- **AND** a missing, stale, foreign or extended deadline fails explicitly;
  a new cleanup process cannot reset the shared allowance

#### Scenario: Read-only transport calls time out
- **WHEN** an execution-status or log-query call times out
- **THEN** only bounded read-only retries within the remaining phase/shared
  budget are permitted, with every call and sleep consuming that budget
- **AND** missing time, malformed/foreign evidence or an exhausted retry
  allowance fails without a broader permission or success-shaped fallback

#### Scenario: A mutation has an uncertain outcome
- **WHEN** a job-start or stop request times out or otherwise has an ambiguous result
- **THEN** the controller must not automatically replay the mutation
- **AND** it retains the safe exact-run recovery reference and fails explicitly
  rather than inventing an execution or stopping an unrelated one

#### Scenario: Diagnostics classify a failed operation
- **WHEN** transport, response parsing, input validation or cleanup fails
- **THEN** reporting uses fixed content-free categories, preserves the original
  failure and records any cleanup failure separately
- **AND** no exception payload, command, query, identifier or credential is
  exported; a historical generic error is not relabelled as a proven timeout

### Requirement: Complete private bounded reporting
The workflow SHALL enforce finite execution/model/recovery budgets and emit only
allowlisted stages, opaque case identities, counts, timings and fingerprints.
Raw feed/query/article text, prompts, completions, tokens, credentials and
arbitrary exceptions MUST NOT enter logs or uploaded evidence.

#### Scenario: A report is evaluated
- **WHEN** the workflow collects the final stage report
- **THEN** all required cases/stages and matching run/revision references must
  be present exactly once with explicit measured outcomes
- **AND** a missing report, malformed count, stale execution, upstream error,
  timeout or exceeded budget fails rather than becoming empty success

#### Scenario: Success or failure diagnostics contain canaries
- **WHEN** tests exercise processing, HTTP/SQL failures, subprocesses and cancellation
- **THEN** exported logs/artifacts contain no content or credential canary
- **AND** the original failed stage remains identifiable through a safe category

### Requirement: Verified exact cleanup
Success SHALL require removal of the exact disposable database and verification
of its absence. Cleanup MUST run on normal completion and failure, with a
bounded cancellation-recovery path. Missing proof, ownership drift or failed
cleanup MUST block acceptance without touching production or unrelated targets.

#### Scenario: A successful or failed run finishes
- **WHEN** worker connections are closed and exact ownership is verified
- **THEN** cleanup removes only that run database from a different connection
  and verifies its absence
- **AND** success is emitted only when both processing gates and cleanup passed

#### Scenario: The main execution is cancelled
- **WHEN** interruption prevents its cleanup from completing
- **THEN** the workflow stops only that execution and invokes exact-run cleanup
  under the dedicated identity, retaining failure/cancellation status
- **AND** if recovery cannot finish, it records the remaining exact target for
  operator recovery and leaves phase acceptance blocked

### Requirement: Honest evidence-based phase readiness
Step 1.6 SHALL close only after the new federated integration, cleanup, current
local/CI gates and the delivered scanner/enrichment/retrieval/native-user
acceptance are all evidenced. Existing valid results may be referenced only with
matching revision/configuration provenance; provisioning or a small smoke alone
MUST NOT imply full quality, identity-isolation or Phase 2 readiness.

#### Scenario: The operator assembles final phase acceptance
- **WHEN** every required check has a measured result and traceable provenance
- **THEN** the phase report links prior quality/native-user evidence separately
  from the new isolated run, records actual unchanged production baselines,
  and passes exact-commit CI before phase status changes
- **AND** unknown, failed, drifted or missing acceptance remains explicitly incomplete
