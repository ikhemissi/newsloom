# user-feedback Specification

## Purpose
Let readers rate briefings and research answers so quality issues are recorded with
enough context to be fixed and turned into evaluation cases.

## Requirements

### Requirement: Rate briefings and research answers
A signed-in reader SHALL be able to give a thumbs up or down, with an optional
comment of at most 1,000 characters, on any published briefing version and on each
completed research answer. Submitting again for the same item SHALL replace the
reader's previous rating for that item.

#### Scenario: Reader rates a briefing
- **WHEN** a reader selects thumbs down on the briefing and adds a comment
- **THEN** the rating, comment and briefing version are stored and acknowledged
- **AND** selecting thumbs up later for the same version replaces the earlier rating

#### Scenario: Comment is too long or the target is unknown
- **WHEN** a comment exceeds 1,000 characters or the briefing version is not in the history
- **THEN** the request is rejected with a validation error and nothing is stored

### Requirement: Research answer snapshot only on feedback
Research answers SHALL NOT be stored unless the reader submits feedback. Feedback on
an answer SHALL store the question, answer, citations, applied filters and task ID
as submitted by the browser, bounded to the existing answer size limits, and marked
as client-supplied.

#### Scenario: Reader rates a research answer
- **WHEN** a reader rates a completed answer
- **THEN** one feedback record holds the rating, comment and the answer snapshot
- **WHEN** a reader never rates an answer
- **THEN** no copy of that answer is stored

### Requirement: Pseudonymous, write-limited storage
Feedback SHALL store a one-way hash of the reader's Entra object ID, never the ID,
name or email. Writes SHALL require the existing delegated `news.read` scope and a
token object ID, and use an insert-only database grant; stored text SHALL never
appear in logs or telemetry.

#### Scenario: Feedback is recorded and inspected
- **WHEN** feedback is stored
- **THEN** the record holds a reader hash but no direct identifier
- **AND** the API's database role can insert but not update or delete feedback
- **AND** logs and telemetry contain only the outcome, target type and rating

#### Scenario: Caller lacks the read scope or object ID
- **WHEN** a token without `news.read` or without an object ID submits feedback
- **THEN** the API responds 403 with `insufficient_scope` and stores nothing

### Requirement: Reviewer access and export
Only callers whose Entra object ID is in the configured reviewer allowlist SHALL
list or export feedback.
The export SHALL produce JSON Lines of the latest rating per reader and item,
filterable by rating, target type and date, for local triage.

#### Scenario: Reviewer exports thumbs-down items
- **WHEN** a reviewer exports thumbs-down feedback for the last 7 days
- **THEN** the file contains one line per item with rating, comment, target and
  snapshot or briefing version, without reader identifiers
- **WHEN** a reader not in the allowlist calls the list or export endpoint
- **THEN** the API responds 403

### Requirement: Feedback feeds evaluation
A local script SHALL convert reviewed export lines into eval regression cases outside
version control: a briefing case references its artifact version and expected issue;
a research case holds the question, filters and the reviewer's expectation.

#### Scenario: A reviewed thumbs-down becomes an eval case
- **WHEN** the reviewer marks an exported item with an expected outcome and runs the script
- **THEN** a case file is written under the ignored cache directory and
  `scripts/eval.sh` can include it
