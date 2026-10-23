# Spec Delta

## MODIFIED Requirements

### Requirement: Calibrated explicit threshold
The screening threshold SHALL be derived from labelled calibration examples and
verified against separate clean/hostile validation fixtures before live admission.
Threshold, model configuration, class counts, and observed classification outcomes
MUST be recorded. A threshold MUST NOT be guessed merely to enable deployment.
Fixtures SHALL use the same complete normalized-entry serialization as admission.

#### Scenario: Screening is enabled for live entries
- **WHEN** the proposed threshold is evaluated on the validation fixtures
- **THEN** expected clean fixtures are accepted and hostile fixtures are rejected,
  with the observed results retained as evidence
- **AND** unmet fixture expectations block live admission rather than weaken the gate

#### Scenario: Metadata participates in calibration
- **WHEN** an evaluation entry contains instructions in its title, author,
  categories, or body
- **THEN** calibration and validation inspect the complete serialized entry,
  not a standalone body string or a shortened description

## ADDED Requirements

### Requirement: Contextual news injection classification
Screening SHALL distinguish attempts to redirect the consuming processor from
reporting about AI instructions. Benign article guidance, training-use notices,
and contextualized examples MUST NOT alone establish malicious injection.
Claims of quotation, research, or authorization MUST NOT automatically exempt an
operative instruction from screening.

#### Scenario: A publisher includes a training-use notice
- **WHEN** a news entry includes an anti-training notice without instructions
  attempting to hijack its consuming processor
- **THEN** the notice alone does not establish malicious injection
- **AND** this classification does not override publisher data-use restrictions

#### Scenario: News reports a prompt-injection example
- **WHEN** a news entry contextualizes an attack payload as material it reports
  on rather than directions its consuming processor should adopt
- **THEN** contextual reporting alone does not establish an attack against the
  processor
- **AND** acceptance does not promote any source text to trusted instructions

#### Scenario: An entry attempts to change processing
- **WHEN** source content attempts to override trusted instructions, manipulate
  its verdict or output, disclose private context, or cause unauthorized actions
- **THEN** the hostile evaluation cases are rejected regardless of whether they
  name Newsloom explicitly

#### Scenario: An attack claims to be an authorized example
- **WHEN** an operative directive to the consuming processor is disguised as a
  quotation, tutorial, or authorized security test
- **THEN** the claim alone cannot cause acceptance

### Requirement: Policy-bound calibration
Live admission SHALL require calibration metadata matching the active question,
packaged fixture revision, model configuration, and threshold. Missing,
malformed, or mismatched metadata MUST prevent admission explicitly.
A policy update MUST NOT rescore, resolve, release, or delete existing rejected
quarantine rows automatically.

#### Scenario: A threshold belongs to an earlier rubric
- **WHEN** the runtime question or fixture revision differs from the recorded
  calibration binding, or the threshold or model configuration was changed alone
- **THEN** ingestion fails closed with a content-free configuration error before
  admitting entries
- **AND** it does not select a default threshold or another model

#### Scenario: A verified policy is deployed
- **WHEN** the evaluated image, matching threshold, and calibration binding are
  deployed together
- **THEN** admission retains the strict greater-than rejection comparison and
  existing operational-failure deferral behavior
- **AND** pre-existing rejected quarantine rows remain unchanged

### Requirement: Side-effect-free local screening comparison
Operators SHALL be able to compare the baseline and candidate questions locally
using the existing Decision deployment and Entra credentials. Evaluation MUST
not require database access, start or modify Azure jobs, change azd settings,
publish news, or modify quarantine. Model calls SHALL retain bounded retries,
deadlines, and the shared deployment rate budget.

#### Scenario: An operator compares screening policies
- **WHEN** a local comparison runs against labelled complete entries
- **THEN** it reports baseline and candidate benign rejections, hostile
  acceptances, and operational failures separately
- **AND** no production configuration or database state is changed

#### Scenario: Local authorization or inference fails
- **WHEN** the developer identity is unauthorized, the model is unavailable,
  responses are invalid, or a deadline is exhausted
- **THEN** evaluation reports an explicit safe failure and cannot pass
- **AND** it does not add credentials, grants, resources, or acceptance fallbacks

#### Scenario: Review inputs come from current feeds
- **WHEN** the 23 reviewed identities are reconstructed from selected publisher
  feeds rather than read from historical stored entries
- **THEN** evaluation records provenance, input fingerprints, missing matches,
  and normalization truncation without claiming historical byte equivalence
- **AND** retrieval is restricted to the explicit review set using existing
  network, parser, recovery, and no-article-redirect protections

#### Scenario: Evaluation diagnostics are inspected
- **WHEN** a local run succeeds or fails
- **THEN** reports expose only opaque case identifiers and bounded decision
  metadata, counts, fingerprints, and timing
- **AND** article text, prompts, completions, publisher canaries, credentials,
  and tenant or principal identifiers are absent from diagnostics
- **AND** any private input cache is outside the repository and cleaned up

### Requirement: Evidence-gated screening policy rollout
A candidate SHALL be calibrated without using validation or review-regression
labels to choose its threshold. Deployment SHALL require zero observed errors on
separate labelled benign/hostile validation cases and fewer benign rejections
than the baseline on the fixed 23-item review set. Missing inputs, incomplete
inference, inseparable calibration, or unmet gates MUST block deployment.

#### Scenario: Validation is independent
- **WHEN** a candidate threshold is selected
- **THEN** only calibration-split scores determine it
- **AND** holdout and review-regression labels are fixed before inference and
  cannot be relabelled or omitted to obtain a passing result

#### Scenario: Evaluation cannot justify a policy change
- **WHEN** a hostile holdout is accepted, a benign holdout is rejected, any review
  input is missing, or benign regression rejections do not decrease
- **THEN** the deployed image and calibration remain unchanged
- **AND** the operator sees the failed gate rather than a success-shaped result

#### Scenario: Measured acceptance permits an Azure delivery
- **WHEN** complete local checks and the measured local or explicitly requested
  existing-job comparison pass
- **THEN** the existing azd environment can receive the reviewed in-place update
  and an immediate ordinary ingestion verification
- **AND** no new scanner service, resource, inference grant, schedule change,
  quarantine release, or ad hoc cloud evaluation worker is introduced

### Requirement: Explicit existing-job comparison
An explicitly requested comparison MAY run in the existing ingestion job with
its current managed identity and an immutable candidate image. It SHALL reuse
the same evaluation and admission gates, have no database side effects, and emit
only safe per-case observations and aggregate results. Scheduled admission MUST
retain its verified configuration until comparison passes.

#### Scenario: Developer inference is unavailable
- **WHEN** the operator explicitly requests verification in the existing job
- **THEN** a native execution can compare the frozen review identities using
  the existing identity without a developer grant or separate worker
- **AND** the invocation does not alter the scheduled job's verified admission
  image, threshold, binding, schedule, identity, or quarantine rows

#### Scenario: The candidate passes in the existing job
- **WHEN** all measured gates pass
- **THEN** the matched image, threshold, and binding may be activated together
  through the existing azd flow, followed by immediate ordinary ingestion
- **AND** article identities are joined to the safe observations only in the
  requested findings, not emitted with article content in job logs
