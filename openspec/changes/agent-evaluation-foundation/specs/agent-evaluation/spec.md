## Purpose

Provide reproducible, secretless and bounded agent-evaluation execution with
Foundry-visible results, preserving production authority, content privacy and
an honest distinction between integration proof and measured agent quality.

## ADDED Requirements

### Requirement: Isolated reproducible evaluation pilot
The evaluation pilot SHALL run on the repository's supported Python version
in a standalone evaluation-only project with its own locked dependencies and
environment. The application lock and resolved production dependency closures
MUST remain unchanged. The pilot MUST NOT add evaluation libraries to production
installations or require Azure access or paid inference for ordinary local and
pull-request checks.

#### Scenario: Locked local checks run without cloud access
- **WHEN** the documented application and evaluation checks run in their
  respective locked environments through the primary local and CI gate
- **THEN** scripted-provider tests run without credentials or network access
- **AND** the isolated production agent imports and starts without the
  evaluation libraries installed

#### Scenario: Evaluation dependencies conflict with production versions
- **WHEN** an evaluation dependency requires a version incompatible with the
  application lock
- **THEN** it resolves only in the separate evaluation lock and environment
- **AND** verification proves the application lock and production dependency
  closures remain unchanged, without combining environments to bypass isolation

#### Scenario: Required compatibility cannot be established
- **WHEN** a dependency, credential adapter or actual SDK wire contract is
  incompatible with the supported runtime
- **THEN** execution fails explicitly before paid work or provisioning
- **AND** no runtime downgrade, dependency substitution or production packaging
  change silently bypasses the compatibility gate

### Requirement: Controlled pilot inputs and provenance
The pilot SHALL accept only its versioned authored question, evidence and
precomputed-answer fixtures. Every result MUST identify its case, fixture
digest, tested source, metric implementation/configuration and judge deployment.
This pilot MUST NOT read production news, invoke the deployed research agent or
capture user conversations.

#### Scenario: The two-case pilot is selected
- **WHEN** the operator invokes the supported and deliberately unsupported
  synthetic-answer cases
- **THEN** both cases are represented exactly once with matching provenance
- **AND** their labels are diagnostic expectations, not a calibrated phase-wide
  release threshold or evidence of deployed-agent quality

#### Scenario: Inputs or result identities drift
- **WHEN** a foreign input, edited fixture, missing case, duplicate case,
  mismatched metric configuration or stale source receipt is presented
- **THEN** the pilot fails validation before scoring or publication as applicable
- **AND** it does not substitute other evidence or reduce the denominator

### Requirement: Secretless preserved evaluation foundation
Evaluation access SHALL use Entra only and separately reviewed project and
inference permissions. The existing model account MUST be retained, with
approved project-management and identity additions performed without replacement.
Existing workload authority, models, capacity, endpoints, schedules and stored
data MUST remain unchanged; the lasting account settings MUST NOT be reversed.

#### Scenario: The foundation is provisioned
- **WHEN** local checks pass and the operator approves the exact owning previews
- **THEN** account prerequisites are updated in place and the evaluation project
  is created through the retained azd environment
- **AND** readback verifies local-key authentication remains disabled, the
  explicit grant inventory matches and existing workloads remain preserved

#### Scenario: Existing resources or authority would change beyond scope
- **WHEN** the plan replaces or destroys the model account, creates a new model,
  expands existing workload grants or cannot reuse the approved chat deployment
- **THEN** deployment and paid acceptance stop for an explicit scope decision
- **AND** no new account, model, key, credential or broader-role fallback is used

### Requirement: Faithful score publication
Published metrics SHALL distinguish imported external evaluator scores from
native judgments and preserve the original finite numeric score and provenance.
Missing, boolean, nonfinite, out-of-range or failed results MUST NOT be
normalized, defaulted to zero, silently omitted or represented as a successful
quality measurement.

#### Scenario: Valid imported scores are published
- **WHEN** both pilot cases produce valid external metric results
- **THEN** the published score for each case equals its original score and is
  explicitly labelled with the external metric's origin
- **AND** the pipeline does not regenerate answers, rerun a judge during
  publication or reinterpret an expected poor answer as an execution failure

#### Scenario: An evaluator or bridge fails
- **WHEN** judging fails, the score is malformed, or the cloud evaluator records
  an item error even if it supplies a numeric placeholder
- **THEN** the pilot records an explicit failed execution with its safe category
- **AND** publication or acceptance cannot turn that error into a valid zero
  score or a passing run

### Requirement: Actual Foundry evaluation visibility
The pilot SHALL create a real Foundry evaluation report whose case identities,
imported scores and metric provenance match independently retained results.
Acceptance MUST include complete API readback and inspection of the actual
Evaluations report, not only local files, a dataset upload or an asynchronous
submission acknowledgement.

#### Scenario: The report is verified
- **WHEN** the exact submitted evaluation run reaches a terminal state
- **THEN** all output pages contain the two matching cases, original scores,
  explicit metric origin and consistent configuration/source lineage
- **AND** the operator verifies those cases and scores in the actual report
  using its returned report reference

#### Scenario: Visibility or parity is incomplete
- **WHEN** the report is unavailable, an item is missing or duplicated, only
  aggregate values exist, or API/UI results disagree with the original results
- **THEN** integration acceptance remains failed or blocked
- **AND** storage-only evidence or a different run cannot satisfy the gate

### Requirement: Finite cumulative evaluation accounting
Each paid pilot SHALL require an explicitly approved finite envelope for
attempts, bytes, output tokens, estimated spending and time. Admission MUST cover
internal metric calls and in-flight reservations. Failed, cancelled and
unobserved usage MUST remain accounted for or explicitly unknown; restarting
publication MUST NOT reset the inference envelope.

#### Scenario: A metric makes multiple model requests
- **WHEN** a metric attempts another provider call
- **THEN** the shared controller checks remaining time, attempts, byte/token
  bounds and conservative cost reservations before dispatch
- **AND** exceeding any bound rejects the request without dispatch, retries,
  model fallback or budget expansion

#### Scenario: Usage is incomplete or execution is cancelled
- **WHEN** a provider attempt has no reliable usage receipt or is interrupted
- **THEN** its admission remains reserved and the report marks usage incomplete
- **AND** token placeholders do not imply zero consumption, and cost estimates
  remain distinct from Azure invoices and infrastructure charges

#### Scenario: Publication has an ambiguous outcome
- **WHEN** a create or submit operation times out after it may have succeeded
- **THEN** execution retains an exact recovery reference and does not
  automatically repeat the mutation or rerun inference
- **AND** only bounded read-only reconciliation can establish the outcome

### Requirement: Private evaluation diagnostics and data handling
Evaluation diagnostics SHALL contain only allowlisted outcomes, case references,
counts, timings and fingerprints. Credentials, prompts, evidence, answers, judge
explanations and raw exceptions MUST NOT enter logs. Only approved authored
synthetic evaluation data may enter the selected Foundry evaluation artifacts;
vendor telemetry, external result sync and production-content collection are
forbidden.

#### Scenario: Success, failure or forced instrumentation is exercised
- **WHEN** tests inject content and credential canaries through judging,
  publishing, errors and cancellation
- **THEN** diagnostics and unintended caches contain none of those canaries
- **AND** recorded outbound requests target only the approved Azure surfaces,
  with no vendor telemetry or external dashboard synchronization

#### Scenario: An evaluation artifact is retained
- **WHEN** the pilot uploads synthetic inputs, scores or bounded explanations
- **THEN** their data classification and observed retention/deletion behavior
  are recorded separately from content-free operational telemetry
- **AND** unavailable deletion proof is explicit and never claimed as successful
  cleanup; production text remains excluded from the pilot

### Requirement: Honest source-bound foundation delivery
Foundation delivery SHALL require matching local, Azure, report-visibility,
preservation and exact-source CI evidence, with separate measured status
publication. The interoperability pilot MUST NOT mark P2-C06 or Phase 2 complete,
claim calibrated quality thresholds, or imply online production-quality
evaluation, signed-in research acceptance or a frozen agent-quality baseline.

#### Scenario: The foundation is released
- **WHEN** all foundation acceptance and publication gates have measured evidence
- **THEN** only this delivery slice is marked complete
- **AND** the frozen baseline, calibrated judges, candidate comparisons and
  private online monitoring remain explicitly assigned to follow-up changes

#### Scenario: Only local implementation or provisioning passed
- **WHEN** actual judging, Foundry API/UI parity, preservation or publication CI
  remains unverified
- **THEN** the owning change stays active with those tasks unchecked
- **AND** no compatibility, cloud or quality success is inferred from scaffolding
