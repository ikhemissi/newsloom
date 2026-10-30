## Purpose

Establish a reproducible quality baseline for the actual delegated research
agent using frozen expectations, calibrated semantic checks, bounded execution
and content-free Foundry reports without changing production authority.

## ADDED Requirements

### Requirement: Frozen baseline inputs and declared coverage
A baseline SHALL bind a versioned question/oracle manifest, private evidence
identities and fingerprints, evaluator and deployed-agent provenance, fixed
case/metric applicability, and pass criteria before generation. Local controls,
live requests and expected authorization denials MUST have distinct modalities.
Changing any frozen input MUST require a new version and approval.

#### Scenario: An approved baseline is prepared
- **WHEN** the operator freezes the initial suite
- **THEN** it contains exactly 12 declared live cases and eight authored judge
  controls, plus separately identified offline tool/injection controls
- **AND** the coverage matrix includes explanation, comparison, discovery,
  immutable filters/selection, preferences, limited/no evidence and user access
- **AND** actual item identifiers and authored private oracles stay outside Git
  and Foundry rows, while their hashes bind the reproducible case set

#### Scenario: Evidence or expectations drift
- **WHEN** a selected summary, discovery result set, request, oracle, evaluator
  or target changes after freezing
- **THEN** execution fails explicitly without replacement evidence, a refreshed
  denominator, silently regenerated questions or relabelled baseline results

### Requirement: Actual user-preserving research capture
Live baseline answers SHALL come from the retained deployed A2A agent under
the existing signed-in public-client flow. Successful cases MUST bind validated
stream/task parity, same-user evidence and execution receipts. Expected denials
MUST match their frozen oracle without judging an answer. Direct-model,
scripted and local controller answers MUST NOT substitute for a live result.

#### Scenario: A live research case completes
- **WHEN** the signed-in agent produces its final answer
- **THEN** the captured artifacts exactly match completed task readback
- **AND** the evidence fingerprint checks and validated user-preserving
  receipt match the frozen case and retained target
- **AND** model/tool counts, observed tokens, latency and source/configuration
  are attributed to that request without saving its answer or credentials

#### Scenario: An invocation fails or its outcome is uncertain
- **WHEN** unexpected authentication failure, evidence acquisition, generation, streaming,
  readback or receipt validation fails
- **THEN** the case remains failed or unknown, not a valid zero or omitted case
- **AND** its request slot and uncertain cost reservation remain consumed
- **AND** no automatic request replay, answer repair or judge substitution occurs

#### Scenario: An authorization denial is expected
- **WHEN** a frozen missing-token or wrong-audience case returns its exact
  expected authorization denial
- **THEN** the contract result records that expected denial without expecting
  a successful task/answer receipt or semantic score
- **AND** missing proof of no admitted model work retains conservative exposure,
  rather than reporting unknown cost as zero
- **AND** any unexpected success, denial type or ambiguous send fails that case

### Requirement: Calibrated and evidence-grounded scoring
Semantic scoring SHALL use the frozen Azure judge and only the frozen evidence
relevant to the actual answer. Authored supported/unsupported controls MUST pass
their predeclared labels before live generation. Structural citation validity
and operational correctness MUST remain distinct from semantic support.

#### Scenario: Calibration fails
- **WHEN** any fixed control disagrees with its approved label, records an
  execution error or lacks complete usage
- **THEN** live generation does not begin
- **AND** the failed calibration and reservations remain recorded without
  retuning thresholds, changing labels or rerunning the judge until it passes

#### Scenario: A supported answer is measured
- **WHEN** a live case is declared eligible for semantic scoring
- **THEN** its claims are checked against the exact frozen stored summaries,
  not the judge's background knowledge or a later news snapshot
- **AND** deterministic citation and request-contract checks run independently
- **AND** predeclared inapplicability is explicit; missing/error scores cannot
  become inapplicable or change any metric denominator after execution

#### Scenario: A valid live score misses its quality threshold
- **WHEN** a completed live case produces a finite valid score below its frozen
  quality threshold without an execution error
- **THEN** the original score remains a valid failed-quality measurement and
  eligible for exact publication
- **AND** the bounded suite may complete once, but release acceptance remains
  unchecked; no case is dropped, repaired or rescored to obtain a pass
- **AND** calibration failures, evidence drift and execution errors retain
  their separate stop behavior

### Requirement: Honest tool and injection acceptance
Tool-policy and indirect-injection acceptance SHALL include exact authored
controller/transport assertions for requested operations, arguments, identity
and prohibited dispatch. Live receipt counts alone MUST NOT be called a full
tool trace or proof of indirect-injection resistance.

#### Scenario: Hostile retrieved content is exercised locally
- **WHEN** an authored title, summary or tool result requests a forbidden action
- **THEN** exact offline assertions prove no unauthorized dispatch or scope
  widening and verify the content/credential canaries remain private
- **AND** the result is labelled local controlled evidence, not a live attack
  against the retained news database

#### Scenario: Live user access is tested
- **WHEN** authorized and predeclared denied A2A cases execute
- **THEN** caller preservation, expected denial behavior, actual receipts and
  frozen evidence/citation coverage establish the stated live checks
- **AND** missing per-call observation is reported as a coverage limitation,
  never inferred from aggregate counters or a prior offline result

### Requirement: Finite cumulative baseline admission
A baseline SHALL require fresh explicit approval binding all model, request,
read, mutation, byte, token, cost, retention and time limits. Agent requests
MUST reserve conservative full-request exposure before dispatch; judge calls
MUST share cumulative accounting. Old pilot approvals MUST remain unchanged
and cannot authorize baseline work.

#### Scenario: The initial envelope is approved
- **WHEN** local verification and scoped readiness pass and the user approves
  the exact proposed envelope
- **THEN** at most 12 live requests, 80 judge attempts, six publication creates
  and 180 publication reads fit one three-hour window and USD 10 estimated
  combined agent/judge/query-embedding model-admission ceiling
- **AND** the existing per-request limits remain clamped, calls remain
  single-flight, unknown usage retains its reservation, and read/byte limits
  also cover evidence capture and exact-result polling
- **AND** embedding exposure includes retained transport attempts, and
  unattributed embedding usage remains reserved rather than labelled observed
- **AND** this estimate excludes infrastructure and is not an Azure billing cap

#### Scenario: A limit or authorization expires
- **WHEN** remaining cost, time, identity validity or any count/byte/token
  reservation cannot cover the next operation
- **THEN** no further corresponding request is dispatched
- **AND** restart cannot reset counters, deadlines or unknown exposure; a new
  user-approved run must preserve the failed attempt and original baseline

### Requirement: Exact metadata-only baseline publication
Baseline reports SHALL contain only allowlisted metadata and exact finite
scores, with declared case/metric eligibility and provenance. Their protocol
MUST be distinct from the authored pilot. Every eligible metric/case result
MUST match retained content-free results through API and actual report readback.

#### Scenario: Different metrics have different eligibility
- **WHEN** the baseline publishes its declared metric reports
- **THEN** each report contains exactly its frozen eligible case set and
  original canonical round-trip score values, with no error placeholders
- **AND** the suite index accounts for every case and declared inapplicability
  without mixing unrelated metric averages or uploading question/answer text
- **AND** API and UI show matching case IDs, metric identities and scores

#### Scenario: Publication is incomplete or ambiguous
- **WHEN** a row, page, metric, provenance field or remote outcome is missing,
  changed, duplicated or uncertain
- **THEN** report acceptance remains blocked and exact recovery references remain
  private under the original limits
- **AND** no judge, agent request or uncertain create is automatically replayed
- **AND** existing accepted pilot reports remain unchanged

### Requirement: Independent baseline delivery and preservation
Baseline delivery SHALL require local/offline, signed-in Azure, report,
calibration, scoped preservation and exact-source CI evidence, followed by a
separate measured status publication. No new resource, model, grant, production
write or tracing authority is admitted by baseline planning.

#### Scenario: The baseline is delivered
- **WHEN** the frozen criteria and every required delivery gate pass
- **THEN** the versioned report is preserved as the baseline with its limitations,
  image/source/configuration and complete accounting
- **AND** unchanged workloads/models/grants/configuration and selected evidence
  are verified within the existing scope without claiming a fresh full-database
  or inherited/effective-access proof that was not obtained
- **AND** candidate comparisons and online monitoring remain separate slices;
  broader P2-C06/PRD-2 completion follows the owning phase acceptance

#### Scenario: Necessary preservation or capture requires broader authority
- **WHEN** verification cannot obtain required evidence through existing
  authorized user/resource-scoped interfaces
- **THEN** execution stops for a separate scope decision
- **AND** no migration-identity verification, new grant, wider inventory,
  production-content trace or deployment is introduced as a fallback
