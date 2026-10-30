# agent-evaluation Specification

## Purpose

Provide reproducible, secretless and bounded agent-evaluation execution with
Foundry-visible results, preserving production authority, content privacy and
an honest distinction between integration proof and measured agent quality.

## Requirements

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
Existing workload authority, models, capacity, endpoints, schedules and original stored
records within the defined verification boundary MUST remain unchanged; the
lasting account settings MUST NOT be reversed.

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

#### Scenario: The user approves Terraform reconciliation of direct experiments
- **WHEN** the existing CLI/manual data resources and grants are adopted
- **THEN** exact-ID imports preserve the working storage account, project-managed
  identity connection and current operator/project grant scopes without replacing
  the model account, project, storage or deployed workloads
- **AND** shared-key and public-blob denial, HTTPS/TLS controls and the existing
  default-storage/authentication/sharing behavior remain verified
- **AND** the two unused diagnostic telemetry grants are adopted before only
  those assignments are removed through a separate reviewed Terraform plan
- **AND** the Application Insights resource, successful reports and other-project
  assets remain untouched, with no new model, agent setup or logging authority
- **AND** source/plan bindings, locking, before-state backup and independent
  readback prove the actual change; code alone is not adoption evidence

#### Scenario: The user explicitly approves project-scoped Foundry User
- **WHEN** the custom-role catalog path is denied and the user separately
  approves Foundry User for the selected operator on the existing evaluation
  project
- **THEN** the owning Terraform/azd preview admits exactly one assignment
  addition, zero managed-resource changes or destroys, and only its required
  output additions, after local checks pass
- **AND** independent exact-assignment readback verifies the documented built-in
  role identity, selected operator, principal type `User`, exact project scope
  and absence of unexpected conditions
- **AND** existing custom roles, their assignments and all production workload
  authority remain unchanged; no account-, RG- or subscription-scoped Foundry
  User grant or managed-identity grant occurs
- **AND** only the separately approved provider-required exact Foundry User
  definition GETs may exceed the RG boundary; no global role inventory,
  other built-in-definition read or wider preservation claim is admitted
- **AND** only the disclosed refresh-state `null`-to-`[]` changes for project
  `identity_ids`, both custom roles' `not_data_actions`, and their corresponding
  custom-grant output may accompany the assignment/output addition, with every
  other field unchanged and no additional managed-resource mutation
- **AND** the new source/plan/apply/readback receipt links to the immutable
  historical foundation evidence without relabelling or replaying it

#### Scenario: A proposed Foundry User assignment exceeds the approved delta
- **WHEN** the plan or readback names a foreign principal, another role,
  a broader scope, unexpected conditions, extra assignments or another mutation
- **THEN** the permission transition fails explicitly before further work
- **AND** no inferred equivalent role or scope expansion substitutes for approval

#### Scenario: Successful sample upload is followed by failed deletion
- **WHEN** the approved two-case upload succeeds with complete original-score
  and lineage readback, and its subsequent disposable exact-owned deletion fails
- **THEN** the conditional Foundry Project Manager assignment may proceed only
  for the same selected operator, principal type `User`, on the existing
  evaluation project through the owning Terraform/azd workflow
- **AND** local checks, exact owning preview/apply and independent assignment
  readback preserve existing grants and production workload authority
- **AND** provider-required exact role-definition reads require separate
  approval; no global role inventory or account-, RG- or subscription-scoped
  grant is admitted
- **AND** assignment readback alone does not establish working deletion

#### Scenario: The conditional escalation prerequisites are absent
- **WHEN** upload fails or remains uncertain, deletion has not been tested after
  successful upload, or the post-upload deletion succeeds
- **THEN** Foundry Project Manager is not assigned without a subsequent explicit
  approval such as the post-upload-failure transition below
- **AND** historical deletion failures do not substitute for the required
  post-upload deletion outcome

#### Scenario: Catalog authorization is tested after the approved assignment
- **WHEN** the exact assignment is verified and the operator starts the fresh
  authorization-only envelope
- **THEN** at most four exact-owned catalog GETs, including propagation checks,
  use 30-second request timeouts and one recorded ten-minute deadline, without
  hidden retries or wider discovery
- **AND** the observed catalog response, not assignment existence, establishes
  the authorization-test outcome; continued denial leaves lifecycle blocked
- **AND** no model call or artifact mutation occurs, and the expired original
  probe journal, unknown remote version and cumulative paid limits are preserved
- **AND** subsequent reconciliation, cleanup or a fresh lifecycle probe requires
  a separately approved recovery envelope; permission approval alone does not
  establish lifecycle/deletion acceptance or authorize judging

#### Scenario: The user explicitly approves Project Manager after failed upload
- **WHEN** the real scored run fails authorization and the user explicitly
  instructs adding Foundry Project Manager and retrying publication
- **THEN** this instruction supersedes the earlier deletion-dependent ordering
  only for one exact operator/project-scoped assignment through the owning layer
- **AND** local checks, exact saved preview/apply and independent readback prove
  one assignment addition and unchanged Foundry User/custom grants
- **AND** only the separately approved provider-required exact definition GETs
  may exceed the ordinary verification boundary
- **AND** a separately approved bounded publication-only retry preserves the
  original validated scores, lineage, usage, journal and original scoring
  deadline unchanged, without reactivating inference; the renewed publication
  instruction permits only a distinct ten-minute publication window
- **AND** no rescoring, historical create replay, wider grant or inferred upload
  acceptance occurs

#### Scenario: Azure records the approved first child project on the account
- **WHEN** evaluation-layer readback follows the exact approved project/grant
  apply and both account bookkeeping properties were previously absent
- **THEN** only `associatedProjects` containing exactly the approved child
  project's name and `defaultProject` naming that same project may be admitted
- **AND** independent project identity/native endpoints and exact grant checks
  still pass, with all other compared account properties and features unchanged
- **AND** the original source, baseline, reviewed/applied binary, apply evidence,
  failed readback and exact account preimages remain retained and bound to a
  distinct corrected readback receipt
- **AND** a verifier-only source correction does not relabel old evidence, reset
  baselines or admit changed infrastructure, provider locks, models, grants or
  unrelated source
- **AND** no resource reapply, account update, migration verification execution,
  additional permission or wider cloud check occurs

#### Scenario: Project bookkeeping differs beyond the approved transition
- **WHEN** either property identifies another project, additional projects
  appear, only one property transitions or another account property changes
- **THEN** readback fails without a general metadata exemption
- **AND** lifecycle tests, content upload and paid judging remain blocked

### Requirement: Resource-group-bounded cloud verification
Cloud verification SHALL be limited to the selected Newsloom RG and its
resources, its configured Newsloom database, and the exact MCP API/client and
agent API/client app registrations with their federation/consent configuration.
Preparation, preflight, preservation readback, reconciliation and pilot admission
MUST enforce this boundary before dispatch and report its limits.

#### Scenario: The user explicitly approves the two account-scoped role tests
- **WHEN** project-scoped roles and the preview-header test have not established
  upload success, and the user explicitly requests both built-ins on the account
- **THEN** only Foundry User and Foundry Project Manager for the same selected
  human operator on the exact retained account may be added for this diagnostic
- **AND** existing project/custom grants and workload identities remain unchanged
- **AND** separate private intent and exact-assignment readback evidence records
  at most two PUTs and six assignment GETs in one ten-minute envelope
- **AND** no unknown mutation is replayed, no inventory exceeds the RG boundary,
  and experimental assignments are not claimed as Terraform-owned before adoption
- **AND** retesting preserves the saved scores and inference accounting, uses the
  explicit preview header and cannot substitute assignment existence for API parity

#### Scenario: An in-scope verification runs
- **WHEN** the verifier inventories the selected RG and project app registrations
- **THEN** it reads only the allowed resources, database and app configuration
- **AND** it checks exact RG/resource assignment identities, scopes and conditions
  and the approved permissions of the evaluation-owned RG-restricted custom roles
- **AND** built-in role IDs in those assignments do not trigger global definition
  reads or checks of inherited grants, except the separately approved pinned
  provider's exact Foundry User definition GETs for its owned assignment
- **AND** local selected-environment context checks do not authorize additional
  cloud inventories

#### Scenario: A request or pagination target exceeds the boundary
- **WHEN** an inventory, identity lookup, database target or continuation would
  inspect anything outside the allowed verification scope
- **THEN** it is rejected before that request is dispatched
- **AND** no broad query, cross-RG principal search or wider fallback occurs
- **AND** subscription-wide queries followed by filtering, inherited
  subscription/management-group grants, assignments elsewhere, global built-in
  definitions, subscription quota/catalog inventories and unrelated
  directory/database reads are excluded

#### Scenario: A limited verification receipt is produced
- **WHEN** in-scope verification completes
- **THEN** its evidence identifies the request/pagination boundary and omitted
  wider checks
- **AND** it does not claim complete effective-access or wider preservation
  verification

#### Scenario: A necessary check is unavailable within scope
- **WHEN** the selected account/project or another permitted target cannot supply
  evidence needed for the limited verification claim
- **THEN** verification stops with an explicit limitation
- **AND** it neither widens scope nor represents missing evidence as verified

### Requirement: Audited reconciliation after preservation failure
A failed preservation readback MUST stop project/grant provisioning and
evaluation execution until explicit, tested reconciliation establishes the
approved invariants. The original before-baseline, failed after-receipt,
reviewed/applied binary and source/approval lineage MUST remain retained and
unchanged. A fresh aggregate, a rewritten receipt or an arbitrary historical
source exception MUST NOT substitute for proof.

#### Scenario: Only the explicitly reviewed account metadata differs
- **WHEN** the account adds the exact observed CostControls marker
- **THEN** reconciliation may handle only that specifically approved difference
- **AND** all other account properties, local-auth state, identity checks,
  endpoints, RG/resource assignments and evaluation-owned RG-restricted custom
  role identities/types, permissions, exclusions, scopes and conditions remain
  verified within the defined boundary
- **AND** unreviewed features, broader authority or a general custom-role
  exemption still fail closed

#### Scenario: Final observed service metadata and policy resources are reconciled
- **WHEN** the user approves the exact final metadata reconciliation and
  excludes verified policy-managed scanning resources from application ownership
- **THEN** a distinct source/evidence-bound receipt preserves the blocked
  snapshot, original baseline and each component's actual verification time
- **AND** removing only the observed `fal.ai Inference API` descriptor at the
  existing Azure account HTTPS root reproduces the original account fingerprint
- **AND** the actual historical scoped tool evidence permits only the rolling
  `/backup/earliestRestoreDate` substitution that exactly reconstructs the
  original database-boundary fingerprint
- **AND** the observed scanning topic/subscription is classified by its owned
  storage source, Microsoft scanning destination and inherited storage-scoped
  settings, without changing Defender or adopting its resources into Terraform
- **AND** all other in-scope account, resource, role, project, workload, schedule,
  model and original-record checks remain required; unrelated drift still fails
- **AND** bounded history evidence identifies scheduled additions, rolling-list
  aging and the separately authorized verification execution without claiming
  indefinite history retention or repeating that execution
- **AND** no resource mutation, model call, grant, baseline reset or blanket
  endpoint/resource exclusion substitutes for the exact proof

#### Scenario: The user narrows an earlier verification scope
- **WHEN** original failed receipts include broader RBAC evidence and the user
  restricts subsequent checks to the RG, its Newsloom database and project apps
- **THEN** those original receipts remain unchanged and linked to the explicit
  source/scope transition
- **AND** new comparisons use only the original in-scope evidence and fresh
  in-scope reads, explicitly identifying the excluded wider checks
- **AND** global built-in definition checks and their former ten-definition
  timestamp allowance are not continued or expanded
- **AND** neither resetting the baseline nor claiming wider preservation may
  substitute for the remaining in-scope proof

#### Scenario: Scheduled publication grows the news dataset
- **WHEN** existing scheduled workloads add stored news during verification
- **THEN** complete fingerprint evidence proves the original stored-record set
  unchanged and accounts for every admitted addition
- **AND** historical aggregate-only evidence is admitted only after exact
  reconstruction of its fingerprint, count and retained recent-record identities
- **AND** missing, duplicate, changed or deleted original records, partial reads,
  sampling or count-only comparisons cannot pass

#### Scenario: A least-privileged identity cannot read verification metadata
- **WHEN** the existing MCP identity denies a metadata column needed for proof
- **THEN** that denial is retained and MCP privileges are not broadened
- **AND** only the explicitly approved fallback may use at most one fixed-program
  verification execution with the existing migration identity, in a verified
  server-enforced READ ONLY transaction under the design's finite limits
- **AND** it permits no migrations, schema/data writes, new grants, image changes,
  production text in logs or evaluation publishing under that identity
- **AND** inability to enforce those restrictions leaves reconciliation blocked

#### Scenario: Verifier changes follow an already-applied plan
- **WHEN** the approved reconciliation requires a new verifier source version
- **THEN** the historical source preimage and original plan/apply/failure evidence
  remain cryptographically bound to the retained environment and operator
- **AND** the new receipt explicitly identifies the source transition without
  pretending the original readback passed or replaying the completed account plan
- **AND** any subsequent admitted baseline and parent verification retain links
  to the validated reconciliation and original failure

#### Scenario: Completed account identity outputs were not persisted
- **WHEN** independent ARM readback confirms the identity but its two computed
  Terraform outputs are missing, and the user approves state/output recovery
- **THEN** only an exact owning plan with 32 managed-resource no-ops, those two
  output additions and the observed null-to-empty identity-list representation
  may update the existing locked state
- **AND** before/after backups, unchanged lineage, independent output parity and
  the exact binary/source are retained in a linked state-repair receipt
- **AND** no resource mutation, original account-update replay, broader drift
  exemption, state migration or backend reconfiguration is admitted

### Requirement: Faithful score publication
Published metrics SHALL distinguish imported external evaluator scores from
native judgments and preserve the original finite numeric score and provenance.
Missing, boolean, nonfinite, out-of-range or failed results MUST NOT be
normalized, defaulted to zero, silently omitted or represented as a successful
quality measurement.

#### Scenario: An explicitly approved native account POST comparison runs
- **WHEN** the operator compares native AOAI definition creation on the specified
  reference and Newsloom accounts
- **THEN** one verified bearer token and identical serialized payload are used
  for one POST per account on the same legacy API route/version
- **AND** at most two POSTs and six owned-definition GETs fit a ten-minute envelope
  without mutation replay, run creation, inference, role changes or deletion
- **AND** actual HTTP outcomes and exact ownership readback are recorded privately
  without treating definition creation as successful score publication

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

#### Scenario: Fractional scores cross the native evaluation boundary
- **WHEN** validated local scores are submitted through the native Python bridge
- **THEN** the wire schema declares scores as strings containing their canonical
  round-trip float representations, while local results remain strict numbers
- **AND** the grader returns the original finite numeric value without rounding,
  tolerance, rescoring or threshold changes
- **AND** strict readback verifies the complete case/lineage set for flat or
  `datasource_item.item`-wrapped rows and rejects noncanonical score strings
- **AND** boolean, nonfinite, changed or malformed scores and nested sample
  execution errors cannot be accepted as valid imported scores

#### Scenario: Publication encounters preview and nullable error representations
- **WHEN** the publisher submits or reads an evaluation through the project API
- **THEN** every request includes `Foundry-Features: Evaluations=V1Preview`
- **AND** null-only error placeholders do not make a queued run fail, while
  populated or malformed errors still stop publication explicitly
- **AND** source, ownership, read/mutation limits and original deadline checks
  remain enforced without changing historical approval or result artifacts

#### Scenario: The approved native Python protocol publishes existing scores
- **WHEN** the operator publishes validated scores through the native inline
  Python protocol
- **THEN** the evaluation contains the exact reviewed `type="python"` criterion,
  imported-score name, source and diagnostic threshold, with no registered
  evaluator or model-based publication fallback
- **AND** exactly two create slots cover its evaluation definition and
  `file_content` run, with bounded reads and no evaluator-catalog request
- **AND** every returned case, original score, explanation and lineage field
  matches the retained results, with no judge call during publication

#### Scenario: A catalog-era journal is offered to the new publisher
- **WHEN** an old approval or journal records catalog mutation slots or unknown
  catalog outcomes instead of the native inline protocol
- **THEN** it is not silently relabelled, migrated or replayed as a new upload
- **AND** its original evidence and recovery references remain unchanged,
  without claiming absence, deletion or a renewed deadline

#### Scenario: The native metadata-only lifecycle is exercised
- **WHEN** the approved disposable native-Python probe runs, after successful
  sample upload under the explicit sample-first exception or before other paid
  scoring
- **THEN** at most two creates, two exact-owned deletes and 60 GETs fit one
  recorded ten-minute deadline with 30-second requests and no automatic retries
- **AND** readback verifies the original constant score without execution errors,
  followed by exact run/evaluation absence after deletion
- **AND** missing ownership, an uncertain mutation or failed lifecycle/deletion
  proof stops the probe and retains private recovery references without claiming
  cleanup acceptance; outside the sample-first exception, it also blocks judging

#### Scenario: The user explicitly permits the existing sample before deletion
- **WHEN** the operator executes the approved sample-first exception
- **THEN** exactly the existing two authored synthetic cases may be scored and
  uploaded before deletion proof using the existing grants and a fresh
  source-bound native-Python approval and journal
- **AND** the unchanged USD 1 estimated admission ceiling, 12 cumulative judge
  attempts, byte/token and spacing limits, and shared 30-minute scoring/upload
  deadline remain enforced after fresh price/deployment and scoped preflight
- **AND** complete uploaded case, original-score and lineage parity is verified
  before a fresh separately bounded disposable deletion test begins
- **AND** the scored report remains protected by its 30-day manual retention;
  deletion tests target only fresh exact-owned disposable assets
- **AND** no historical unknown mutation is replayed or relabelled, and upload
  success does not establish deletion, UI or overall delivery acceptance

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
