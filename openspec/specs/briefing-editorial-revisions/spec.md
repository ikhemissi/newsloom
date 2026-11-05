# briefing-editorial-revisions Specification

## Purpose
Let an explicitly authorized operator refresh a published daily briefing for
editorial review while preserving the previous report, execution history and
measured inference usage.

## Requirements

### Requirement: Explicit version-bound revision
An editorial revision SHALL require an operator request ID, the expected current
artifact version and a constrained reason. It MUST target the currently published
daily cutoff, serialize with other generation, and reject a stale version,
concurrent owner or execution that could overlap the next daily cutoff.

#### Scenario: An operator refreshes today's published briefing
- **WHEN** an authorized request names the current published version and sufficient
  execution time remains before the next daily cutoff
- **THEN** exactly one revision claims that version under the existing writer
- **AND** ordinary scheduled execution still refuses an already-claimed slot

#### Scenario: The request is stale, concurrent or too close to the next cutoff
- **WHEN** the current version differs, another generator owns execution, or the
  bounded job could overlap the next daily cutoff
- **THEN** the operation fails explicitly before any model intent or publication
- **AND** it does not change the existing artifact or daily schedule

### Requirement: Immutable revision audit and continuous accounting
Before generation, the system SHALL durably preserve the prior artifact and run
metadata in a restricted append-only revision audit. Existing call rows and
failed-attempt history MUST remain unchanged; new physical calls SHALL continue
their ordinals and retain real usage, price basis and unknown markers.

#### Scenario: A successful publication is revised
- **WHEN** the revision claim succeeds
- **THEN** its request ID, reason, base version, prior payload, run metadata and
  prior last-call ordinal are durably recorded before model dispatch
- **AND** the old successful attempt is not relabelled as a failure
- **AND** the writer cannot update or delete revision-audit rows

### Requirement: Idempotent dispatch without uncertain replay
Reusing a revision request ID MUST NOT dispatch more model operations. Running,
pending or unknown prior usage SHALL block fresh dispatch. An observed validation
failure from a prior revision SHALL require a new explicit request, matching base
version and known complete accounting before another revision is permitted.

#### Scenario: An operator repeats a request after losing its response
- **WHEN** the same request ID is submitted again
- **THEN** the operation reports that the request already exists without generation
- **AND** uncertain generation is reconciled, not automatically repeated

#### Scenario: A revision fails with observed or unknown usage
- **WHEN** its prior operations are fully observed and its failure is explicitly
  recognized as a validation failure
- **THEN** only a fresh version-bound operator request can claim another attempt
- **WHEN** any operation is pending or unknown
- **THEN** no new request can replay generation until uncertainty is reconciled

### Requirement: Atomic last-good publication
The old briefing SHALL remain readable while its revision runs or fails. Only a
fully validated architect-policy summary and its derived TL;DR SHALL replace it
atomically under a fresh artifact version. Publication MUST verify that its base
version is still current; partial results and stale replacements MUST NOT publish.

#### Scenario: Generation succeeds or fails part-way
- **WHEN** the summary and TL;DR both validate and the base version is unchanged
- **THEN** one new artifact replaces both together
- **WHEN** summary, TL;DR, citation, length or publication validation fails
- **THEN** the old artifact remains intact, the failure is explicit and all newly
  incurred usage remains recorded

### Requirement: Stable evidence window and protected reads
A revision SHALL retain the existing daily cutoff and preceding seven-day window,
using a new consistent snapshot of eligible stored news. It MUST use the deployed
architect policy and existing model configuration. Reads, expansion, research and
ordinary failed-run retry SHALL NOT invoke published-artifact revision.

#### Scenario: The new policy is reviewed immediately
- **WHEN** an operator revises the legacy report after the architect rollout
- **THEN** the cutoff/window do not move to the invocation time
- **AND** changed snapshot counts/hash are recorded honestly
- **AND** the new report follows the architect reading ceiling and factual controls
- **AND** protected readers can observe its new version within the existing cache bound
- **AND** this manual result does not prove that the daily scheduler executed

### Requirement: Restricted content-safe operation
Revision SHALL use existing Entra/managed identities without new browser or MCP
write authority. Only the migration principal SHALL create its audit schema;
archive payloads MUST remain protected database data, never logs or telemetry.
No monetary cap or model/region fallback SHALL be introduced.

#### Scenario: Permissions and operational diagnostics are checked
- **WHEN** the revision is deployed and executed
- **THEN** only the existing writer has the new audit read/insert grants
- **AND** MCP/browser callers cannot generate, read the audit or mutate history
- **AND** diagnostics contain only safe identifiers, status and usage metadata,
  not article bodies, report text, prompts, completions or credentials
