# Design

## Context

See [the proposal](proposal.md#why) for motivation and the
[evaluation delta](specs/agent-evaluation/spec.md) for the observable contract.
This is the interoperability foundation, not P2-C06's baseline delivery.

The repository has one Python 3.15 uv workspace, six packages and a
credential-free [primary check](../../../../scripts/check.sh). The
[agent image](../../../../services/agent/Dockerfile) installs only the agent package,
without development dependencies. Existing research, signed-in client and
content-free telemetry stay unchanged.

The retained AIServices account is owned by the application Terraform root,
uses disabled local authentication and has `prevent_destroy`. At initial
preflight it had neither project management nor an account managed identity.
AzureRM 5.10.0 documents both `project_management_enabled` and
`azurerm_cognitive_account_project`; the latter requires a managed account
identity and custom subdomain. No new provider is needed for those resources.

The user selected account reuse on 2026-10-28 after reviewing the lasting
configuration trade-off. Disabling project management or removing the required
identity later would require account replacement. They must therefore remain
configured even if the evaluation project is subsequently retired.

The approved prerequisite plan has since been applied, but parent preservation
readback failed. Diagnosis found an added service-reported CostControls marker,
timestamp-only differences in inherited built-in role definitions, and news
growth from 2,106 to 2,108. Original-record append-only proof remains blocked by
the MCP identity's deliberately restricted column access. At that failure, the
project and evaluation grants remained uncreated. The user approved the audited
reconciliation decision below; this is not evidence that it is implemented or
that preservation has passed.
The user subsequently restricted verification to the selected Newsloom resource
group, its Newsloom database and the project's app registrations. The boundary
below supersedes the earlier global built-in timestamp policy; it is not yet
evidence that the existing checker enforces the narrower scope.

## Goals / Non-Goals

**Goals:**

- Exercise the real evaluation libraries and actual Azure interfaces before
  investing in dataset breadth or release thresholds.
- Prove exact score/provenance transfer and useful case inspection in Foundry.
- Keep inference, publishing, diagnostics and resource changes explicitly bounded.

**Non-Goals:**

- Scoring the deployed agent or measuring production-user answer quality.
- Claiming a calibrated faithfulness judge from two illustrative answers.
- Introducing an evaluation service, persistent worker, scheduler or paid CI.
- Reusing production identities as evaluation publishers.

## Decisions

### 1. Operator-run tooling in a separately locked project

The initial shared-lock probe on Python 3.15.1 found that DeepEval 4.3.2 requires
`click>=8,<8.4`. Resolution downgraded Click from 8.5.0 to 8.3.3 in the production
agent and MCP closures, despite evaluation dependencies being development-only.
The original manifests, lock and environment were restored; both affected
dependency graphs matched their original snapshots and isolated agent startup
passed. No DeepEval metric or Projects SDK execution was verified by that probe.
The user selected a separate evaluation-only project rather than a production
dependency downgrade.

Use `tools/agent-evaluation/` as a standalone Python 3.15 uv project with
`package = false`, its own manifest, lock and virtual environment. Explicitly
exclude it from the application workspace. Put the typed runner in that
project's `agent_evaluation/` directory and its tests in its `tests/` directory;
keep authored fixtures under the repository's `config/`. This adds neither a
seventh distributable package nor a production service. Do not add evaluation
dependencies to the root development group or service manifests.

Pin DeepEval, `azure-ai-projects` and the required checking tools in the
evaluation project. Keep the application lock and all six production dependency
closures unchanged. Each project must install, import and execute using its
own locked environment; do not join environments through implicit import paths
or an active application environment. Any reused local dependency must be
explicitly declared and resolved in the evaluation lock.

Keep the existing primary check and CI as the entry point, adding the isolated
evaluation project's locked lint, strict type and scripted-provider tests.
Ensure test discovery and third-party pytest plugins cannot initialize DeepEval
before its privacy opt-outs. Ordinary checks require neither Azure credentials
nor paid inference. Document distinct application and evaluator commands in the
README and evaluation runbook.

Verify root-lock equality, all production dependency closures and evaluation
library absence in production installations, as well as the existing isolated
agent-startup check and six package builds. The root workspace exclusion and
documentation are still agent image build inputs: keep the evaluator source
digest distinct from the unchanged deployed agent's accepted source/image.
Bind the evaluation manifest, lock, code, fixtures and relevant shared inputs
to evaluator provenance; do not claim the new checkout built the existing image.

DeepEval 4.3.2 and Projects SDK 2.9.0 remain compatibility candidates, not accepted
pins. Their metadata permits Python 3.15 but does not establish working imports,
isolated coexistence or wire behavior. Add the separate manifest before
installation, then test the actual metric and SDK with controlled local
transports. Failure blocks cloud work; do not lower Python, alter production
dependencies or silently change the connector.

### 2. A two-case faithfulness pilot, not an agent benchmark

Commit one authored evidence passage, a question, one supported answer and one
answer containing a clear unsupported claim, each with a stable opaque case ID.
Bind the exact fixture digest and input schema before execution. The production
database, MCP service, signed-in A2A client and research controller are not targets
of this slice.

Run one DeepEval `FaithfulnessMetric` on each precomputed answer through an
evaluation-owned asynchronous judge adapter. All internal model calls must pass
through its fixed Azure chat endpoint, Entra credential and shared accounting.
Use public library interfaces, not global monkeypatching or provider defaults.
Reuse applicable shared transport/error patterns without importing the agent's
delegated-user authorization or changing its instrumentation.

Prefer direct metric measurement over automatic suite/dashboard machinery.
Verify that imports, metric execution and error handling do not create unintended
result caches, crash reports, vendor telemetry or external synchronization.
Configure supported opt-outs before library initialization and test actual
outbound requests. Never use a Confident AI login or a vendor API key.

Persist actual scores and bounded synthetic-only explanations, including a
counterintuitive judge result. No rerun-until-pass loop is allowed. Known
positive/negative labels are useful diagnostics, not calibrated acceptance
thresholds.

### 3. A labelled imported-score bridge into Foundry

Use the current Foundry project evaluation API for precomputed datasets, not the
classic-only local-result logging path. The typed publication row contains the
case ID, fixture/source/metric digests, judge configuration, original finite
score and bounded synthetic explanation. Validate strict numeric scores in
`[0, 1]`, reject booleans and require exact case-set equality.

For the Foundry wire representation, declare the score column as a string and
encode each validated local float with its canonical round-trip representation.
Keep local results and lineage numeric and unchanged. The native grader parses
the score text, rejects invalid/nonfinite/out-of-range values and returns the
original numeric score. Strict readback accepts only canonical score text,
checks the exact decoded value without tolerance or rounding, and handles both
flat rows and the observed `datasource_item.item` wrapper. The 2026-10-30
publication regressions exposed numeric-column precision loss and verified this
string representation on fractional and adjacent-to-threshold values.

Send `Foundry-Features: Evaluations=V1Preview` on every publication request.
Treat null-only service-error placeholders as absent, but reject populated
service errors and nested item/grader sample errors even when a score is present.
Preserve original scoring approvals/results/deadlines; changing the runtime
source does not authorize relabelling an old journal or repeating inference.

Embed a minimal native Python grader directly in the evaluation definition,
with `type="python"`, `name="imported_deepeval_faithfulness"`, the exact reviewed
`source`, and diagnostic `pass_threshold=0.5`. Its `grade(sample, item)` returns
the already computed finite score unchanged. It does not register or reference
a catalog evaluator, import DeepEval, call a judge or reinterpret the score.
Foundry's documented code sandbox has no
network access and returns a float, not an explanation. Preserve the explanation
as an explicit synthetic dataset field and verify its accessibility in case
details, rather than promising a native judge-reason field.

Native Python publication requires no judge model or orchestration deployment
reference. Continue verifying the existing approved deployment for local
DeepEval scoring only; do not create or invoke a deployment for publication.
A demonstration display threshold is not a phase-quality
gate; an intentionally poor answer may remain visibly failed.

Read every output page and compare exact case IDs, numeric values and metric
provenance with the original validated results. Inspect item execution errors:
the service can assign a `0.0` placeholder when code fails, which is not a valid
import. Open the returned report and verify actual per-case scores, explanations
and lineage. Missing fields or UI/API disagreement blocks delivery; local JSON,
dataset storage or a classic-portal substitute is not acceptance.

An endpoint-hosted evaluator is deliberately excluded: it introduces another
service and authentication boundary before the simpler bridge is disproved.
If the proposed bridge cannot satisfy the contract, stop for a design decision.

### 4. Reuse the account with explicit owning-layer changes

Update the existing application root only for project management, its required
system-assigned identity and necessary outputs. Retain the current account,
subdomain, keys-disabled setting, endpoints, deployments, capacities, tags and
workload grants. Keep the lasting properties configured directly, not behind a
default-off flag or conditional child-project count.

Add an `agent-evaluation` azd/Terraform layer depending on `application` for one
system-assigned-identity project and the reviewed evaluation-specific grants.
Use the existing provider versions and normal platform preparation conventions.
Do not grant either new identity production database, MCP, registry, telemetry
reader, management or unrelated model access. Service-added assignments must
appear in readback, not be treated as invisible defaults.

The pilot runs with the selected operator's explicit Entra CLI credential and
validated tenant/account context, not an environment-secret fallback. Inventory
only RG/resource-scoped operator assignments before proposing any missing
project or chat permission. Do not infer the operator's complete effective
access from that intentionally limited inventory. Management authority is not proof of a
least-privilege automation identity; dedicated federated execution is a later
slice. Existing workload identities receive no new grants.

The user selected a custom chat-completions-only grant for that operator at
the retained account scope, plus project-scoped evaluation permissions. This
is operation-level restriction, not deployment-level IAM isolation: it also
authorizes future chat-capable deployments in that account. The runner must
still admit only the approved deployment and model snapshot. The separately
approved operator-only Foundry User addition in section 4c and the conditional
project-scoped Foundry Project Manager addition in section 4e are the only
exceptions to the custom project-role design. Do not assign these built-in roles
or inference grants to either new managed identity.
The exact catalog and evaluation lifecycle permission mapping remains a
preflight gate; an unverified mapping must not trigger any other broader-role
fallback or scope expansion.
This permission-design choice does not approve provisioning or paid inference.

Before provisioning, verify project/evaluation support through the retained
account/project interfaces, deployment visibility, capacity exposed on the
retained deployment and local-auth state, all within the boundary below. Do not
inspect subscription quota or regional catalogs. Record unsupported or
unavailable checks explicitly rather than widening scope. Review the exact
application and evaluation plans and the in-scope principal/scope/operation
inventory. Account
replacement, new accounts/models, unsupported scopes or unavoidable broader
permissions require a separate user decision, not an implicit fallback.

#### Verification scope

The user-defined cloud verification boundary applies to preparation, preflight,
preservation readback, reconciliation and pilot admission:

- ARM inventories and resource reads target only the selected Newsloom RG and
  its descendant resources, including the retained model account, its projects
  and deployments, workloads, identities and database server.
- RBAC inventories include only assignments whose scope is the RG or a
  descendant resource. Use scope-targeted requests; never collect
  subscription-wide assignments and filter afterward. Exclude inherited
  subscription/management-group grants and all assignments elsewhere, including
  those belonging to the selected operator or a Newsloom identity.
- Read custom role metadata only for the evaluation-owned roles restricted to
  this RG, through RG-scoped requests. Check their exact approved permissions,
  assignable scope and assignments. Do not fetch global built-in definitions
  referenced by existing assignments; compare those assignments' role IDs,
  principal IDs, scopes and conditions without claiming definition preservation.
  Section 4c contains the sole separately approved provider-required exact
  Foundry User definition-read exception; it authorizes no global inventory.
- Database reads target only the configured Newsloom database on the server in
  that RG. The bounded, content-free, READ ONLY record proof below remains
  required; this boundary authorizes no other databases.
- Directory reads target only the exact MCP API/client and agent API/client app
  registrations and their associated federation/consent configuration. Do not
  enumerate the tenant, other applications, users, groups or service principals.
  Existing local azd/CLI context may be checked without additional cloud
  identity or subscription inventories.

Validate request targets and pagination against this boundary before dispatch.
No subscription quota/catalog inventories, cross-RG principal searches or
broader fallback reads are permitted. If a necessary operation cannot be
verified within scope, stop and report that limitation. This is a reduced
verification claim, not proof of unchanged inherited or complete effective
access. It changes no roles, grants, production behavior or deployment authority.

### 4a. Evidence-bound reconciliation after failed readback

The user approved reconciliation of the observed parent-readback failure.
This adds no permission to waive preservation, reset the original baseline,
replay the applied account plan or continue project provisioning on an
unexplained difference. Preserve original before/failed-after receipts and
the exact reviewed/applied binary as immutable evidence.
Retain the original wider-scope evidence unchanged. New receipts must explicitly
bind the reduced verification scope and its source transition, compare only the
original in-scope evidence with fresh in-scope reads, and name the omitted wider
checks. Do not reread excluded resources, claim wider preservation, rewrite the
failure or substitute an unexplained fresh baseline.

Before changing verifier code, preserve the historical source preimage and
its digest. Any verifier-source transition must explicitly bind the original
baseline, review, apply-intent/completion evidence, failed readback and new
reconciliation proof to the same retained environment and approved operator.
Verify that owning infrastructure, provider locks, models and grant intent
remain byte-bound to the reviewed plan. Do not accept an arbitrary historical
source hash or rewrite an earlier failed receipt as successful.

The user separately approved recovery of two missing computed account-identity
outputs through an exact state/output-only owning plan. Require all 32 managed
resources to be no-ops, with only the observed `identity_ids` null-to-empty-list
state representation and creation of those two outputs. Match their values to
independent ARM identity readback. Preserve before/after state backups and
lineage; use the retained backend, exact reviewed binary and locking, with no
resource writes, account-update replay, state migration or reconfiguration.
Bind the distinct state-repair receipt into subsequent reconciliation evidence.
This is not a general drift/nullable-value exemption.

For the original parent reconciliation, the only admitted metadata difference is:

- The observed account transition to the exact reported
  `Microsoft.CognitiveServices/CostControls` feature marker. Bind raw account
  preimages to the original before/after fingerprints; preserve all other
  account properties, endpoints, local-auth denial and approved identity/
  project-management checks. Additional or unexplained features still fail.

The former allowance for timestamps on ten global Microsoft built-in definitions
is historical and superseded by the user's reduced verification scope. Do not
expand that allowlist, normalize or reread those definitions as a current gate.
Continue checking all RG/resource assignments and the evaluation-owned,
RG-restricted custom roles exactly as specified above. The original timestamp
diagnosis remains retained evidence, not a claim of current global-role
preservation.

A changed news count is not append-only proof. Reconciliation must establish
that every original stored-record fingerprint remains unchanged, identify
every admitted addition, and fail on missing/duplicate/changed original
records, incomplete reads or an unexplained fingerprint. For historical
receipts containing only the original aggregate, an authorized deterministic
reconstruction must exactly reproduce that aggregate, count and retained
recent-record fingerprints; no sampling, count-only comparison or arbitrary
subset search is sufficient. Establish versioned, complete per-record
fingerprint evidence for subsequent comparisons so continued append-only
publication can be checked without broadening the MCP role.

Use an existing least-privileged authorized verification route first. If it
cannot obtain the required metadata, the approved fallback is at most one
verification-only execution with the existing migration identity, which has
database-administrator authority. Bind its exact existing job, accepted image
and identity, and a fixed verification program. Use a server-enforced READ ONLY
transaction and verify that mode before data reads. Bound the execution to
600 seconds, individual SQL statements to 60 seconds, fingerprinted rows to
4,096 and returned evidence to 512 KiB. Only hashes, counts, identity/configuration
fingerprints and timing metadata may leave the verification program. No
migration startup, schema/data writes, new grants, image deployment or article
text in logs is permitted. Preserve the existing job configuration/schedule
and record the additional verification execution separately. If this cannot
be enforced, stop rather than create a broader verification service or grant.

Produce a distinct reconciliation receipt only after all meaningful authority,
runtime, model, database-boundary and original-record checks pass. Link any
subsequent admitted baseline and parent readback to that receipt and the
original failure. A fresh aggregate alone cannot clear the gate. If code or
evidence changes require new previews, verify them through the retained owning
workflow; do not reapply the already-completed account update.

### 4b. Exact first-project bookkeeping after evaluation-layer apply

The approved evaluation-only apply subsequently created the child project and
its four grant resources. Its independent readback failed because Azure added
`associatedProjects` and `defaultProject` to the retained account. Exact-account
diagnosis found no other compared account change; the reconciled CostControls
list itself was unchanged. The user explicitly approved admitting only this
owned-project bookkeeping transition.

During evaluation-layer readback only, admit the transition from both properties
being absent to `associatedProjects` containing exactly the approved child
project's name and `defaultProject` naming that same project. Independently
verify that project under the retained account, its identity/native endpoints
and exact grants through the existing scoped checks. Reject partial transitions,
additional projects, another default, changed features and every other account
property difference. This is not a general account-metadata exemption or a change
to the historical CostControls reconciliation.

Retain the original baseline, reviewed/applied binary, apply intent/completion,
source and failed readback unchanged. Bind the exact before/after account
preimages and a verifier-only correction to those artifacts in a distinct
source-bound readback receipt. Do not silently relabel old evidence with the
corrected source, reset the baseline or admit changed infrastructure, provider
locks, model/grant intent or unrelated source through this transition. Test
accepted and rejected metadata/source/ownership cases before repeating readback.
No resource reapply, account update, migration verification execution, additional
permission or wider cloud check is authorized.

### 4c. Approved project-scoped Foundry User authorization test

The metadata-only lifecycle probe reached a native evaluator-catalog
`401 PermissionDenied`. Subsequent exact-owned reads, including one with the
documented evaluation preview header, returned the same denial. The existing
custom role and exact operator/project assignment matched the verified
foundation evidence. These observations do not identify a missing DataAction
or prove a service defect.

On 2026-10-29, the user explicitly approved testing the documented Foundry User
role after reviewing its broader permissions. Add exactly one assignment for
the already selected operator, with principal type `User`, at the existing
evaluation project's resource scope. Keep both existing custom roles and their
assignments unchanged, including the account-scoped chat-completions-only grant.
Do not grant Foundry User at account, RG or subscription scope, to the project
or account managed identity, or to any production workload. No new project,
identity, application, model, capacity or credential is needed.

Use the evaluation-owned Terraform/azd layer in the retained environment.
Resolve the built-in role's identity from Microsoft's public reference and
private environment inputs; do not query global role definitions or enumerate
directory principals for discovery or verification. The user separately chose
to allow the pinned AzureRM provider's unavoidable exact Foundry User
role-definition GETs during assignment creation/readback and subsequent refresh.
This exception is limited to that documented built-in identity; it permits no
role-definition listing, other built-in reads or wider preservation claim.
Use AzureRM rather than adding AzAPI for this assignment. Local checks and an
exact owning preview must establish
one role-assignment addition, zero managed-resource changes or destroys, and
only the corresponding declared output additions. Stop on any other planned
mutation. No application prerequisite, completed project apply, state recovery
or migration verification execution may be replayed.

The role-only native preview subsequently showed exactly the intended one
addition and five retained resource no-ops, plus refresh-only `null`-to-`[]`
differences for project `identity[0].identity_ids` and each custom role's
`permissions[0].not_data_actions`. The existing custom-grant output also
represents both empty exclusions as `[]` instead of `null`. After these exact
differences were disclosed, the user instructed proceeding with the role.
Admit only those state/output representation changes, comparing all other
fields exactly and rejecting nonempty exclusions or authority/output drift.
Keep the original failed-review binary unchanged; the fresh source-bound
review must record these differences without claiming a resource update.

Treat this as a new, explicit permission transition, not a verifier-only
correction under section 4b. Preserve the successful historical foundation
receipt, sources, plans and all failed probe evidence unchanged. Record the
new source, reviewed/applied role-only plan and exact assignment readback in a
separate receipt linked to that foundation. Check the precise role identity,
operator, principal type, project scope and absence of unexpected assignment
conditions; reject a foreign principal, broader scope or extra assignment.
Retain the existing RG/database/project-app verification boundary without
claiming unchanged global definitions or complete effective access.

After assignment readback, use a fresh authorization-only envelope for at most
four catalog GETs against the original exact-owned evaluator name, with
30-second request timeouts and one ten-minute deadline recorded before dispatch.
Include explicit propagation-wait reads in that count; disable hidden retries
and wider catalog discovery. Bound assignment readback separately to the exact
planned assignment. Reuse local context rather than silently performing extra
account/project reads. Assignment existence alone does not establish catalog
authorization; record the actual response and stop on continued denial.

This authorization test permits no evaluator create/update/delete, dataset
upload, evaluation/run creation or model call. The original lifecycle envelope
is expired and its catalog version remains unknown. Preserve that journal and
do not reset its deadline, replay creation, infer absence from denial or claim
deletion. Any subsequent exact-owned reconciliation, cleanup or fresh lifecycle
probe requires its own explicitly approved recovery envelope. Lifecycle and
deletion acceptance remain prerequisites to paid judging and score publication
except for the subsequent explicit sample-first exception in section 4e.
Existing cumulative limits are not enlarged by either role approval.

### 4d. Approved native inline Python publication

The user explicitly selected native inline Python graders on 2026-10-29 after
live read-only inspection of the supplied reference project. A registered
custom rubric and seven evaluation definitions were observed; a native-Python
recorded-score replay completed with 16 output rows, seven metrics and zero
execution errors. This proves an alternative reference protocol, not Newsloom
authorization, imported-score parity or delivery acceptance.

New publication uses only `POST /openai/v1/evals` with the inline Python
criterion from section 3, then `POST /openai/v1/evals/{id}/runs` containing
the two explicit `file_content` rows. The new approval and durable journal
must identify this protocol and bind exactly two mutation slots, 60 reads,
30-second request timeouts and five-second poll spacing to the original
scoring/publication deadline. Validate the returned definition's exact source,
name, type, threshold and schema as well as complete per-case output parity.
No evaluator-catalog request or further judge call may occur during publication.

Preserve all historical approvals, failed catalog intents and unknown versions
unchanged. Never reinterpret a catalog-era journal or three-slot approval as
an inline-Python publication, reset old deadlines, replay an attempted mutation
or claim old probe removal. Existing custom and Foundry User grants remain;
there is no new infrastructure, role, account scope, model or capacity change.
Use explicit existing Azure CLI authentication, not browser credentials.

Except for the sample-first exception in section 4e, before paid execution the
approved fresh native-Python metadata probe must
create one evaluation and one constant-score inline run, verify the original
fractional score and zero execution errors, then delete only that exact owned
run and evaluation and independently verify their absence. Bound this whole
probe to one recorded ten-minute deadline, 60 GETs total, two creates, two
deletes and 30-second request timeouts, without retries or hidden discovery.
An uncertain mutation is not replayed; retain exact recovery references and
stop on failed ownership, execution, deletion or authorization.

Update cleanup for the new protocol without requiring a catalog version.
Historical catalog-owned cleanup must remain explicitly distinguished and
must not silently adopt new ownership rules. The two authored scored cases,
12 cumulative judge attempts, USD 1 estimated admission ceiling, shared
30-minute deadline and manual 30-day report retention remain unchanged.
Fresh price/deployment and in-scope acceptance gates still apply; successful
reference reads or a changed publisher do not satisfy them. The user may view
the returned report in their normal signed-in browser; do not require entering
credentials in the integrated browser or infer UI acceptance from API success.

### 4e. Approved sample-first sequencing and conditional permission escalation

The user subsequently instructed scoring and uploading the existing tiny sample
before testing deletion, and adding Foundry Project Manager only if deletion
fails after successful evaluation upload. This supersedes the deletion-first
ordering in sections 4c, 4d and 6 only for the already approved two authored
synthetic cases. It does not establish lifecycle/deletion acceptance or authorize
production content, additional cases, models, capacity or wider verification.

Use the existing project-scoped Foundry User assignment and custom grants.
Refresh the required prices, deployment readiness and scoped preflight, then
score and publish under a fresh source-bound native-Python approval and journal.
Preserve the USD 1 estimated admission ceiling, 12 cumulative judge attempts,
single-flight spacing and byte/token limits, and the shared 30-minute
scoring/publication deadline. Verify the actual uploaded run and complete original
case/score/lineage parity before beginning the deletion test. A failed or uncertain
upload does not satisfy the permission-escalation condition.

Only after successful upload, exercise a fresh disposable metadata-only probe
under section 4d's separate ten-minute, 60-GET, two-create/two-delete envelope.
Delete only its exact-owned disposable run and evaluation, never the scored pilot
report protected by the approved 30-day manual retention window. Preserve every
historical unknown catalog or native mutation; do not renew old approvals, replay
uncertain mutations or claim their absence from unrelated probe success.

If that post-upload deletion fails, the user permits adding Foundry Project
Manager for the same selected operator on the existing evaluation project only.
Use the owning Terraform/azd inputs, preview, exact saved apply and independent
assignment readback, retaining all existing grants. Do not assign it before the
conditional outcome, to a managed identity, or at account, RG or subscription
scope. If project scope is insufficient, stop for separate scope approval rather
than broadening it silently. Obtain approval for any additional exact built-in
role-definition reads required by the provider before that transition; no global
role inventory is authorized. Assignment existence is not proof of working
deletion; any subsequent cleanup needs fresh bounded exact-owned verification.

### 4f. Explicit Project Manager approval after the real upload failure

After both cases were scored and the submitted native run failed with
`UserError` naming missing `OpenAI/evals/write`, the user explicitly instructed:
add Foundry Project Manager and retry uploading the evaluations. This supersedes
section 4e's conditional-escalation ordering for this exact transition only.
The user also approved provider-required GETs of the exact built-in definition.
No global role inventory, unrelated definition or wider grant scope is permitted.

Add exactly one assignment for the selected human operator at the existing
evaluation-project scope through the owning Terraform/azd layer. Retain Foundry
User, both custom roles/assignments and production authority unchanged. Bind the
documented role through private input and public fingerprint validation, verify
one addition and zero changes/destroys in the exact saved plan, then independently
read back the exact assignment. The built-in role grants project-management and
data authority, including constrained delegation of Foundry User; this is broader
than evaluation-only access and is explicitly approved. Assignment existence
does not establish working upload or justify account/RG/subscription scope.

Retry only the existing validated synthetic scores, preserving their original
source, fixture, metric, context, explanations and cumulative eight-call usage.
Use a distinct publication-only approval/journal, bound to the exact original
approval/results/failed-state fingerprints and the independently verified grant.
Permit at most two new creates, 60 reads, 30-second requests and five-second
polling within a distinct ten-minute publication-only window under the user's
subsequent instruction to apply and retry. Preserve the expired original scoring
approval/deadline unchanged; this new publication approval must not reactivate
inference. Use a fresh retry ownership marker; do not
replay either historical create, reuse an ambiguous mutation slot, reset old
state/deadlines or invoke another judge. A failed retry remains a failed upload.
Deletion testing still follows successful score/API parity; the scored report
retains its 30-day manual protection.

### 4g. User-approved account-scope diagnostic test

After the explicit preview-header test still failed authorization, the user
instructed adding Foundry User and Foundry Project Manager at the account rather
than project scope and retesting. This supersedes the earlier account-scope
exclusion only for these two built-ins, the same selected human operator and
the exact retained Foundry account. This expands that operator's authority
across the account's models/projects, not production workload identities.

For this requested test, add the two account assignments without removing the
existing project bindings or custom grants. Use deterministic exact assignment
IDs, documented role identities, explicit CLI Entra authentication and separate
private intent/readback evidence. Bound the direct ARM diagnostic to two PUTs,
six assignment GETs, 30-second requests and one ten-minute envelope, with no
automatic mutation retry, directory lookup, global role inventory or credential
logging. Independently verify each exact account/principal/role/condition tuple.
The user requested testing before further workflow hardening; these controlled
experimental grants must be adopted by exact ID into the owning Terraform/azd
layer before formal delivery acceptance, not falsely reported as managed.

Then use a distinct ten-minute publication-only approval/journal for the same
two retained scores, native Python protocol and explicit
`Foundry-Features: Evaluations=V1Preview` header. Retain two create slots,
60 reads, 30-second requests and five-second polling, original lineage/usage
and immutable expired scoring authority. Permit bounded read-only consistency
checks of an uncertain newly created run, never POST replay or new judging.
Record actual API parity or failure; neither role assignment nor reference
success establishes a minimum necessary role or successful upload.

### 4h. Approved native account POST A/B diagnostic

The user approved identical minimal native AOAI POSTs against the specified
successful reference account and the retained Newsloom account. Target the
exact downstream route reported by the portal:
`POST /openai/evals?api-version=2025-04-01-preview`. Use one verified operator
token and byte-identical explicit schema, deterministic Python grader and
diagnostic ownership metadata for both requests.

This narrowly authorizes one new evaluation definition per account, at most
two POSTs and six exact-owned GETs within ten minutes and 30-second requests.
Persist each intent and returned ID immediately; never retry an uncertain POST
or modify existing reference assets. No run, dataset content, inference, role
change or deletion is authorized. Retain private exact-target cleanup references.
Compare actual HTTP outcomes and independent definition readback; definition
creation is not score publication or run/API/UI acceptance. This reference
write exception does not authorize wider resource or permission inventories.

### 4i. Reconcile CLI/manual resources into the owning Terraform layer

The user explicitly requested proper Terraform management and cleanup after
the storage/permission experiments. Keep the existing environment/backend and
adopt exact deployed IDs before changing anything. The owning evaluation layer
adds pinned AzAPI 2.13.0 only for ARM-only storage, its project connection and
the retained diagnostic assignments; AzureRM remains pinned at 5.10.0.
ARM-only storage management avoids key reads and unrelated operator data-plane
permissions. Existing foundation resources and workload authority stay unchanged.

The opt-in data resource configuration owns the existing StorageV2/LRS account
with shared keys and public blobs disabled, HTTPS/TLS controls preserved, the
exact portal-created connection name with `ProjectManagedIdentity` authentication,
its default-storage/user-sharing flags and the project identity's exact storage
Blob Data Contributor binding. It also adopts the two already approved
account-scoped human-operator built-ins. This is management of existing
authority, not a claim that those broad built-ins are minimum permissions.

Adopt the two experimental project-identity telemetry grants only temporarily,
then disable their explicit retention flag and destroy only those assignments
through Terraform. The retained Application Insights resource is not deleted or
duplicated; no Application Insights connection exists. Do not introduce the
unused basic-agent experiment, new models, keys or content logging.

AzAPI's embedded schema does not yet include the observed, working connection
auth type. Disable that schema validation only on the fixed connection resource,
with exact auth/category/endpoint/default-sharing/metadata readback postconditions.
Preserve service-reported private endpoint status rather than configuring it.
Import/provider-state reconciliation must not change the managed connection
behavior or grant scopes. Source-bound native plan review, exact regenerated
plan comparison, state backup, locking and independent readback remain required.
Use a separate reviewed two-assignment destruction plan after adoption.

Keep all successful scored reports under their retention window. Experiment
cleanup targets only assets proven owned by immutable private journals and
current exact-resource metadata; other-project assets and uncertain historical
catalog outcomes are not implicitly adopted or declared absent.

### 4j. Final audited preservation reconciliation

The user approved reconciliation of the final observed metadata differences,
then clarified that policy-managed Defender resources must not expand this
delivery or become experiments to adopt or delete. Record a distinct,
source-bound receipt against the retained final snapshot and original admitted
baseline; neither rewrite the blocked snapshot nor claim a fresh collection.
Keep each component's actual collection/verification time and immutable source.

Admit only the observed `fal.ai Inference API` descriptor whose exact value is
the existing account's HTTPS `cognitiveservices.azure.com` root URL. Removing
only that descriptor must reconstruct the original account fingerprint exactly.
Do not follow the endpoint, invoke a model or admit another endpoint/property.
The PostgreSQL boundary proof must likewise reconstruct the original fingerprint
by substituting only `/backup/earliestRestoreDate`, using the actual original
server/RG-scoped tool evidence rather than a guessed date or general exclusion.

Classify the observed Event Grid system topic/subscription using its exact
evaluation-storage source, regional Microsoft storage-scanning destination and
storage-scoped inherited Defender settings. Exclude that verified policy-managed
side resource from direct application IaC ownership and orphan-experiment
cleanup. Do not query or change subscription security policy, import those
resources, or change scanning. This is not permission to ignore arbitrary
resource additions, workload identities, grants, endpoints or data changes.
The user's permission to delete a storage account when necessary is not a
request to remove the working evaluation storage or bypass a reviewed plan.

Independently compare all original in-scope resources, custom roles, projects,
workload/configuration/schedule fingerprints and grants. Admit only the five
already approved Terraform-owned grant additions and the owned storage.
Execution-history evidence must distinguish unchanged common executions,
scheduled additions, the service's observed rolling 100-entry lists and the
single separately authorized READ ONLY migration verification execution.
Do not claim that aged-out history was deleted or preserved indefinitely.
Bind the complete original-record proof, API/user-attested UI parity,
disposable lifecycle proof, exact Terraform adoption/removal readbacks and
owned experiment cleanup. No additional job start, grant, model call, resource
mutation or historical approval renewal is authorized by this reconciliation.

### 5. Finite accounting before the first paid request

Propose the following small pilot envelope for explicit execution approval:

| Surface | Proposed ceiling |
| --- | --- |
| Dataset | Exactly two precomputed answers; one metric; one measurement each |
| Judge transport | 12 attempts total, including failures and internal metric calls |
| Judge concurrency | One; at least 70 seconds between attempts |
| Judge output | 1,024 tokens per attempt |
| Judge request/response | 64 KiB each per attempt; 512 KiB each cumulatively |
| Shared deadline | 30 minutes, including bounded publication/readback |
| Estimated chat spending | USD 1, with conservative pre-dispatch reservations |

The user explicitly approved these limits for the two-case pilot and selected
the existing GPT-5.4-mini after comparison with GPT-6 Luna. This does not
authorize a Luna deployment or prove current prices, judge calibration,
preservation or lifecycle feasibility. Refresh the existing deployment's
throughput and prices first. Admission must use a verified
conservative input-token bound for the actual serialized request, output ceiling
and current prices. If that cannot fit safely, stop rather than dispatch on an
optimistic estimate. Disable provider/library generation retries; transport
admission remains authoritative even if a library attempts an extra call.

Include all admitted attempts in the cumulative receipt. Track observed usage
separately from reserved/unobserved usage; never release an uncertain reservation
or label cancellation as free. Shared scheduled workloads retain priority:
avoid active enrichment windows and do not increase deployment capacity.

Define finite counts/timeouts for the two native evaluation/run mutations and
read-only polling in the execution manifest before dispatch. A timed-out mutation
must not be automatically repeated. Retain exact recovery references privately
and reconcile only within the remaining original envelope. Publication recovery
reuses validated scores, not new inference.

The spending ceiling is runner admission based on estimates, not an Azure billing
kill switch. Report chat separately from project/storage/compute costs and from
later agent, embedding or native-judge charges, which this pilot does not invoke.

### 6. Separate synthetic artifacts from content-free diagnostics

Only the committed synthetic inputs, their generated judge explanations and
their scores may be uploaded as evaluation data. Production prompts, preferences,
news text and answers are not accepted inputs. Existing telemetry contracts
remain unchanged; logs, CI output and measured status receipts use allowlisted
case IDs, outcomes, counts, timings and fingerprints only.

Keep actual tenant/principal/resource IDs, endpoint configuration and remote run
references in ignored environment/session records. Never commit credentials or
deployment identifiers. Reuse existing azd environment outputs instead of adding
a duplicate `.foundry` deployment configuration or enabling agent content tracing.

Propose a 30-day pilot-artifact retention window, with explicit operator-owned
cleanup rather than an assumed automatic TTL. Document the actual service
retention/backup limits and demonstrate the exact-owned deletion/reconciliation
path using a disposable metadata-only probe. Section 4e explicitly permits the
approved two-case upload before this deletion demonstration. Verify that
cleanup cannot target foreign evaluations, shared data or the retained model
account. Outside that narrow sample-first exception, unsupported deletion or
retention behavior requires a policy decision before pilot-content upload.

Retain the accepted synthetic report for its approved window; remove temporary
files and probe assets with verified ownership. Do not promise hard erasure of
provider backups or claim a scheduled expiry mechanism exists.

## Risks / Trade-offs

- Shared-lock compatibility failed -> use the approved independent tool project
  and prove unchanged application locks/closures; isolated Python/API behavior
  still requires real-library and local wire/error tests before cloud work.
- Account enablement is not simply reversible -> retain `prevent_destroy`, keep
  lasting settings and use the explicit forward-only foundation decision.
- Scores can import without useful report detail -> require actual API and UI
  parity, including explanation/lineage access.
- Model-judge errors can look like poor scores -> separate execution status,
  usage completeness and quality values; inspect sandbox item errors.
- Shared deployment throughput can be disrupted -> one admitted call at a time,
  fresh quota checks, conservative spacing and the original cumulative deadline.
- Pilot success can be mistaken for quality readiness -> retain separate
  baseline/calibration and online-monitoring follow-up slices.

## Migration Plan

1. Review/synchronize/archive completed Step 2.2 with its existing evidence.
2. Implement the separately locked evaluation project and pass cross-environment
   isolation, actual-library compatibility, privacy, budgeting and publication
   tests, then the integrated primary local gate and all six package builds.
3. Perform the read-only Azure preflight and obtain approval for exact owning
   previews, identities/grants, retention and the finite paid envelope.
4. Apply the application prerequisite change in place, verify preserved runtime
   configuration, then provision and independently verify the evaluation layer.
   A failed readback stops that sequence. Complete the approved evidence-bound
   reconciliation, retaining the original failure and source/apply lineage,
   before admitting any subsequent baseline or resuming project provisioning.
5. Execute the bounded pilot, reconcile actual Foundry API/report parity, and
   verify unchanged application workload, model, grant and stored-data baselines.
6. Publish implementation with exact-source CI first, then separate measured
   evidence/status with its own exact-source CI. Only then mark this slice done.

Rollback stops evaluation execution and reconciles exact owned pilot assets.
Remove only reviewed evaluation-owned grants/project if necessary; keep the
account identity and project-management settings. Never restore the old account
configuration by replacing the account. No agent image rollback is required
because this slice does not change or deploy the agent runtime.

## References

- [uv workspaces and conflicting requirements](https://docs.astral.sh/uv/concepts/projects/workspaces/#when-not-to-use-workspaces)
- [DeepEval 4.3.2 dependency metadata](https://pypi.org/pypi/deepeval/4.3.2/json)
- [Cloud evaluation and prerequisites](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation)
- [Precomputed dataset evaluations](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-datasets)
- [Custom evaluator contracts and limits](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/custom-evaluators)
- [Foundry evaluation permissions](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluation-permissions)
- [Built-in AI roles](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/ai-machine-learning)
- [Result readback and report references](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-results)
- [DeepEval Azure authentication](https://deepeval.com/integrations/models/azure-openai)
- [Pinned account provider documentation](https://github.com/hashicorp/terraform-provider-azurerm/blob/v5.10.0/website/docs/r/cognitive_account.html.markdown)
- [Pinned project provider documentation](https://github.com/hashicorp/terraform-provider-azurerm/blob/v5.10.0/website/docs/r/cognitive_account_project.html.markdown)
