# Tasks

## Archival review

On 2026-10-30 the user approved synchronization and archival of this verified
change. All four artifacts and 26 tasks were complete. Delivery head
`e4a4b4f22987d7f028e232e1c6226b67a89dafe2` passed
[exact-SHA CI](https://github.com/ikhemissi/newsloom/actions/runs/41095374175).
All ten requirements and their scenarios, together with the original purpose,
were synchronized into the
[main spec](../../../specs/agent-evaluation/spec.md).
The original planning/acceptance chronology below is retained; its earlier
unsynchronized/unarchived statements predate this review. Only archive-relative
links and this review note were added. No acceptance, paid run, cloud mutation
or migration verification was repeated. Archival publication requires separate
exact-source CI and does not complete Step 2.3/P2-C06.

## Current delivery status

On 2026-10-30, all 26/26 foundation tasks are verified. Implementation
`4eae16851ed664a6d29a145d1cb7a5c5f9b182f5` passed
[exact-SHA primary CI](https://github.com/ikhemissi/newsloom/actions/runs/41092639258):
290 evaluator tests and 1,576 PostgreSQL-enabled application tests passed;
the sole skip is the intentionally excluded live-publisher test.
The separate measured receipt `6531aaea8bbea611aefc91d6412d1b2b1ebed155`
also passed [exact-SHA CI](https://github.com/ikhemissi/newsloom/actions/runs/41093707423).
Completion ledger `aa87b98e48faf8a0d002a980d77b68acb1f67a09` then passed
[its exact-SHA CI](https://github.com/ikhemissi/newsloom/actions/runs/41094492939)
before task 7.3 was checked. The final checklist/status closure must also pass
its own exact-head CI before handoff; prior successful runs do not establish
that final result.
The [final audited preservation receipt](../../../../docs/agent-evaluation.md#final-audited-preservation-acceptance)
closes 1.2, 6.1 and 6.5 against measured evidence, not a reset baseline.
The earlier checkpoints below retain their historical failures and task counts.
Step 2.3/P2-C06 is not complete, and this change is not synchronized or archived.

Closure audit:

- **1.2:** original scoped inventory, model/version/capacity and exact owning
  previews preceded the in-place account/project applies. Actual native
  publication, API/user-attested UI parity and disposable exact-owned deletion
  now establish the previously missing interface/lifecycle feasibility.
  Wider historical inventory is not reused as current scoped proof.
- **6.1:** separately recorded approvals bind the two owning plans, each later
  permission/storage transition, USD 1/12-attempt pilot, finite publication
  windows and 30-day manual report retention. The real pilot refreshed the
  retained deployment and USD 0.825/4.95 per-million input/output prices before
  its eight calls; observed usage is complete with no unknown reservations.
  The explicit sample-first exception preserved the later deletion gate.
  Publication-only retries never renewed inference or historical deadlines.
- **6.5:** the distinct final receipt binds the unchanged failed snapshot and
  baseline, exact approved metadata reconstructions, policy-resource exclusion,
  unchanged custom roles/projects/workloads/models and original grants, five
  approved Terraform-owned grant additions, complete 2,116-record preservation
  with 23 additions, lifecycle/UI evidence and all 16 failed experiment pairs
  API-absent. Common execution histories are unchanged; scheduled lists each
  rolled by 61 entries and the sole added migration execution is the separately
  authorized READ ONLY proof. No helper/client remains running. The receipt
  uses the actual component observation times, makes no fresh-collection,
  backup-erasure or wider/effective-access claim, and caused zero cloud calls,
  new executions, resource mutations or model calls.

The research prerequisite is archived and published as `d3483504aa673adc9b10031cd564b0916008d70f`,
with passing [exact-commit CI](https://github.com/ikhemissi/newsloom/actions/runs/40664742550).
The first dependency-isolation check found a blocker: DeepEval 4.3.2 requires
`click>=8,<8.4`, but the production agent and MCP closures use Click 8.5.0.
The candidate resolution downgraded both closures to Click 8.3.3, so the manifest,
lock and development environment were restored. The user selected a separate
evaluation-only Python 3.15 project/lock rather than a production downgrade.
The isolated environment, bounded runner, publication/recovery bridge,
exact-target cleanup and privacy guards pass 218 actual-library/offline
tests, lint, formatting and strict types on Python 3.15.1. The application lock
and all six production closures remain unchanged; isolated agent startup and
six-package builds pass. Mocked wire evidence is documented in the
[evaluation runbook](../../../../docs/agent-evaluation.md), not Azure/report acceptance.
Fresh read-only workload/directory/model/grant preservation now passes after an
earlier interrupted preflight. Native account/operator inventory and an
independent count/hash-only stored-record baseline also pass. Evaluation
API/retention feasibility and deployed-grant acceptance remain pending.
Subsequent project provisioning is recorded below; no paid evaluation is
complete. Both source-bound native owning
previews now pass: one in-place parent update and five evaluation resources,
with no replacement, new model/capacity or production grant expansion.
Task 1.2 remains open for exact regional catalog/lifecycle authorization and
observed deletion/retention feasibility; the separately approved metadata-only
probe is still required. Evaluation enablement was restored to false at that
preflight and re-enabled for the subsequently approved project apply.
Apply the [design](design.md) and
[evaluation contract](specs/agent-evaluation/spec.md). This is Step 2.3's
interoperability foundation, not its frozen quality baseline.

The user subsequently limited all cloud verification to the selected Newsloom
RG and its resources, the Newsloom database there, and the project's four app
registrations. Earlier preflight evidence does not establish that the checker
enforces this narrower scope. Pending task 4.4 must be completed before live
reconciliation or provisioning resumes; no cloud actions are resumed by this
planning revision.

The user selected reuse of the existing account after reviewing the lasting
project-management/identity settings. That planning choice is not approval for
an unreviewed deployment, new roles, retention policy or paid run. The proposed
USD 1/12-attempt pilot envelope requires task 6.1's explicit execution approval.

## 1. Prerequisite and read-only foundation preflight

- [x] 1.1 Review the completed `agent-research` change and its existing local/Azure and exact-SHA implementation/status evidence; synchronize/archive it through the owning workflow before applying this slice. Verify the delivered research contracts, updated local links and archival publication CI without repeating paid research acceptance merely for archival.
- [x] 1.2 Within the [verification scope](design.md#verification-scope), inspect the retained `dev` account/project inventory, project-management/identity state, evaluation interfaces, existing chat deployment/version/throughput/capacity, RG/resource-scoped operator assignments and evaluation API/retention contracts. Do not query subscription quota/catalog inventories or infer complete effective access. Record content-free before-baselines for in-scope application images/configuration, workload identities/grants, all retained-account models, schedules and stored-record fingerprints using existing authorized verification paths. Verify that one in-place account prerequisite update and one child project can satisfy the chosen design without replacement, new capacity or broader production access; report unavailable in-scope proof and blockers before cloud writes.

## 2. Locked library compatibility and production isolation

- [x] 2.1 Add the non-packaged `tools/agent-evaluation/` Python 3.15 uv project with its own manifest, lock, environment and pinned evaluation/checking dependencies; explicitly exclude it from the application workspace. Keep root development dependencies, service manifests, the application lock and all six production dependency closures unchanged. Verify actual imports in the evaluation environment, isolated production agent startup with evaluation libraries absent and all six existing package builds. Document distinct locked commands in the README and a new evaluation runbook; stop on incompatibility or cross-environment leakage rather than downgrading Python or production dependencies.
- [x] 2.2 Add focused actual-library tests under the evaluation project using controlled local transports for the selected metric's asynchronous/schema contract and the Projects SDK's Entra evaluation endpoints, serialization and error handling. Prove real metric/SDK execution performs no paid network work, emits no vendor telemetry and does not inherit key credentials, external provider defaults or application-environment imports. Verify test discovery/plugins cannot initialize DeepEval before privacy opt-outs, and test that the conflicting evaluation dependency cannot alter the application lock or production closures. Record verified versions and wire shapes in the evaluation runbook before Azure execution.

## 3. Bounded synthetic runner and Foundry publication

- [x] 3.1 Implement the strict two-case authored fixtures under repository `config/` and the operator CLI under `tools/agent-evaluation/agent_evaluation/`, invoked only through its locked environment. Add the fixed-endpoint asynchronous judge adapter, shared attempt/byte/output/deadline/cost reservations and usage-completeness reporting. Exercise the real faithfulness metric against scripted responses; test input/configuration digests, unknown fields, internal extra calls, exact-boundary/one-over limits, throttling, rejected redirects/fallbacks, disabled retries, failures and cancellation without resetting reservations. Document the proposed finite envelope, diagnostic labels and the absence of an agent-quality claim.
- [x] 3.2 Implement strict result/lineage validation, the labelled imported-score evaluator, explicit dataset/evaluator/evaluation/run submission and complete paginated readback. Test exact score/case equality, preserved synthetic explanations, missing/duplicate/stale rows, boolean/nonfinite/range rejection, sandbox error placeholders, partial runs, bounded polling and ambiguous-mutation recovery with zero repeated inference. Document how to locate the returned report and distinguish imported scores from native judges.
- [x] 3.3 Implement operator-owned exact-target retention/cleanup and safe recovery records for the selected project, datasets and evaluations. Add forced-instrumentation/content/credential canaries across imports, judging, publication, failure, cancellation, diagnostics and filesystem caches; verify only approved Azure requests and intentional synthetic artifacts occur. Test foreign/missing ownership rejection and unknown deletion outcomes; document the proposed 30-day manual retention window, service limitations and the absence of automatic expiry or production-content capture.

## 4. Owning Terraform and azd boundaries

The 2026-10-30 corrective integration for task 3.2 adds canonical-string score
wire encoding, a dependency-free numeric replay grader, preview headers,
flat/wrapped output validation and nullable/nested-error regressions.
The isolated evaluator passes 278 local tests, strict types, lint and formatting.
The earlier two-case and fractional Azure diagnostics remain separate evidence.
A subsequently approved publication-only upload exercised the updated main
publisher and verified both original cases through the Azure API with two
creates, eight reads and no model calls. Its fresh admission binds historical
producer evidence to the current publisher source without changing original
scoring journals or deadlines. The user subsequently confirmed the matching
completed report, both exact case scores and visible explanations/provenance
in Foundry; task 6.4 is complete. Lifecycle, preservation, infrastructure
reconciliation and delivery CI remain pending.

- [x] 4.1 Add in-place project management and the required account identity/outputs to the existing application root, preserving `prevent_destroy`, local-auth denial and all existing account/model/workload settings. Add the evaluation-owned project/grants layer, its application dependency and retained-environment preparation/outputs using the pinned providers. Add mocked-provider and preparation tests proving no account replacement, new model, unrelated resource or production grant expansion; document the lasting parent configuration and safe rollback.
- [x] 4.2 Add exact native-plan and deployed-readback verification for both owning layers, including principal/scope/operation inventory, unexpected service-added assignments, key-auth state, retained model/version/capacity/endpoint and existing runtime/data boundaries. Test replacement, foreign account/project, unsupported scopes, drift and missing evidence failures; wire the new layer into existing validation/CI and document preview/review commands without storing deployment identifiers.
- [x] 4.3 Implement the approved [evidence-bound reconciliation](design.md#4a-evidence-bound-reconciliation-after-failed-readback) before resuming 6.2; complete 4.4 before live verification. Preserve the historical verifier source preimage before edits and bind original baseline/review/apply/failure receipts to the explicit verifier-source and reduced-scope transition. Handle only the observed CostControls marker, preserving all in-scope authority/account/runtime checks; do not continue global built-in definition or timestamp checks. Prove unchanged original-record fingerprints and complete append-only additions; introduce complete, versioned per-record evidence for subsequent comparisons without replacing the failed baseline. Prefer existing least-privileged verification; if necessary, use at most one fixed-program execution with the existing migration identity in a verified READ ONLY transaction against the configured Newsloom database under the approved 600-second/60-second-SQL/4,096-row/512-KiB bounds. Permit no migrations, schema/data writes, new grants, image changes or production text in logs. Test invalid ownership/source/scope bridges, unreviewed features, changed in-scope permissions, missing/duplicate/changed/deleted rows, incomplete/oversized evidence and read-only enforcement; run focused checks, the PostgreSQL-enabled primary gate and six builds. Record a distinct, explicitly scoped reconciliation receipt and link any subsequent admitted baseline/parent verification to the original failure; do not replay the completed account update or claim wider preservation.
- [x] 4.4 Enforce the user's [verification scope](design.md#verification-scope) across evaluation preparation, preflight, baseline/plan/readback, reconciliation and pilot admission before finishing live 4.3 or resuming 6.2. Target reads to the selected RG/resources, its configured Newsloom database and the exact four project app registrations; inspect only RG/resource assignments and the evaluation-owned RG-restricted custom roles. Remove subscription-wide role queries, cross-RG principal searches, inherited-grant checks, global built-in definition reads, subscription quota/catalog probes and unrelated directory/database lookups. Guard request targets and pagination before dispatch, including all verification entry points; do not query broadly and filter afterward. Retain original evidence unchanged and bind new scope-aware receipts to the historical source/failure with explicit omitted checks, rejecting unscoped evidence as current proof. Add regression tests proving forbidden requests are never dispatched, valid in-scope verification remains complete and missing proof fails explicitly. Update the README/runbook with the limited claim, run focused checks and the relevant primary gate, and leave provisioning/evaluations paused.

Local 4.4 evidence: 253 focused platform regressions and 25 isolated context
tests pass. The PostgreSQL-enabled primary gate passes with 1,493 application
tests, 218 evaluator tests and 83 Terraform mock runs; strict types and all six
package builds pass. Documentation records the reduced claim and omitted
checks. Original wider receipts remain immutable; live reconciliation,
provisioning and evaluations were not run by this local scope gate.

Historical task 4.3 clarification: read-only replay found that the ten timestamp-different
definitions are global Microsoft built-ins, but three also have resource-scoped
assignments. The user explicitly approved timestamp normalization for exactly
those ten definitions, regardless of assignment scope. Derive and bind that
allowlist from the original immutable before/failed-after receipts; additional
definitions, custom roles and all permission/assignment changes remained excluded.
The user's later RG/database/project-app boundary supersedes this timestamp
policy: do not expand its allowlist or continue global built-in checks. Retain
the diagnosis unchanged; new evidence must explicitly state the reduced scope.
The user also explicitly approved a separately reviewed state/output-only
recovery of two missing computed account-identity outputs: 32 managed-resource
no-ops and only the observed null-to-empty identity-list representation. Require
independent identity parity, exact binary/source, locking and retained
before/after state lineage. No resource write, original account-update replay,
state migration or reconfiguration is authorized by that recovery.

Local 4.1 evidence: 183 focused platform regressions, including 42 new
preparation/boundary tests, pass, as do 12 evaluation-layer and three application-root Terraform
mock runs, strict types, lint, formatting, platform packaging and CLI help.
These verify the declared boundaries and destruction guards, not native update
actions or working catalog authorization. See the
[owning-layer runbook](../../../../docs/agent-evaluation.md#owning-infrastructure-boundary).
Local 4.2 evidence: 124 verifier tests and the combined 307 focused platform
regressions pass, with strict types over 135 files, lint, formatting, CLI and
documentation checks. Actual saved-plan decoding and pinned-provider mock JSON
establish native serialization shapes, not fresh Azure preview acceptance.
The verifier binds embedded source/lock bytes, supports staged parent readback,
and preserves failed drift receipts. An independent native PostgreSQL boundary
check passes with three metadata reads and no mutations/model calls.
Task 1.2 and the Azure acceptance gates remain pending; no cloud writes occurred.

## 5. Complete local integration gate

- [x] 5.1 Wire the isolated evaluation project's locked lint, strict type and scripted-provider tests into the existing primary check and CI without merging environments or requiring Azure credentials/paid inference. Run focused tests first, then the PostgreSQL-enabled `bash scripts/check.sh` and six-package `uv build --all-packages`, including new Terraform mocks, unchanged application-lock/closure assertions, production package isolation and privacy checks. Validate documentation links/anchors, command syntax and identifier/whitespace guards. Bind the evaluation manifest/lock/code and fixture/configuration inputs to evaluator provenance, separately from the unchanged deployed agent's accepted image/source; do not build or redeploy the agent solely for this evaluation slice.

Complete local gate: PostgreSQL-enabled primary checks pass with 1,496 application
tests, 218 isolated evaluation tests and 83 Terraform mock runs. The sole skip is
the intentionally excluded live-publisher test. Strict types, lint, formatting,
OpenSpec/identifier guards, all six package builds, unchanged original production
dependency graphs and actual isolated production-installation checks pass.
The application lock is unchanged; evaluator source provenance is recorded in
the [runbook](../../../../docs/agent-evaluation.md#complete-local-integration-gate).
The owned temporary PostgreSQL container was stopped and removed. This is local
acceptance, not Azure foundation, paid judging, report visibility or publication CI.

## 6. Approved deployment and actual Foundry acceptance

Foundation-only approval, 2026-10-28: the user explicitly approved refreshing
and applying the two owning foundation plans: the retained account's lasting
project-management/system-identity prerequisites, one project with its own
identity, two custom data-only operator roles and their two scoped assignments.
This approval excludes paid inference, evaluation runs, content uploads, new
models and production redeployment. It does not complete the full pilot
approval in 6.1 or authorize the metadata-only lifecycle mutation probe in 6.3.
Stop on an unexpected plan, broader permission or preservation failure.

The user subsequently approved the bounded two-case synthetic pilot and
preliminary lifecycle probe: USD 1 estimated chat admission ceiling,
12 attempts, single-flight/70-second spacing, one 30-minute scoring/publication
deadline, three publication mutations/60 reads and manual 30-day synthetic
report retention, with the documented billing and deletion limitations.
After live Azure availability, quota, capability and pricing comparison, the
user explicitly selected the existing GPT-5.4-mini for this pilot. No Luna
deployment, new model/capacity or production-content upload is approved.
Approval does not establish lifecycle feasibility or successful acceptance.

Actual foundation progress: the exact reviewed application binary was applied
with backend locking, enabling only the lasting account prerequisites.
Independent parent readback failed preservation comparison. Read-only diagnosis
found one additional service-reported `CostControls` feature flag, timestamp-only
changes in inherited role-definition metadata, and a stored-news count increase
from 2,106 to 2,108. Original-record append-only proof remains unavailable:
the existing MCP role correctly denies the needed `created_at` column.
See the [blocked readback evidence](../../../../docs/agent-evaluation.md#applied-parent-and-blocked-preservation-readback).
Project/grant provisioning, metadata lifecycle mutation and paid evaluation
execution are stopped. No task checkbox is completed by this partial apply.

The user explicitly approved the audited reconciliation and its single
verification-only migration-identity fallback. Task 4.3 records that additional
implementation gate. Approval is not proof: the fallback must be server-enforced
READ ONLY and content-free, and missing evidence or any broader authority still
stops execution. Original failed receipts and the already-applied account plan
remain immutable acceptance evidence.

Live 4.3 evidence, 2026-10-29: exact historical reconstruction proves all 2,106
original records unchanged, two additions at failed readback and seven later
additions, with complete per-record evidence for 2,115 records. One READ ONLY
verification execution, zero writes/model calls, unchanged job/image/identity;
exact-execution hash-only log recovery stayed within its original deadline and
byte bound after CLI replica lookup timed out. The failed retrieval receipt and
original wider failure remain immutable and linked. Scoped current metadata and
source/state-repair lineage passed; the distinct reconciliation receipt permits
fresh admitted baselines, not account-update replay or wider preservation claims.

Subsequent 6.2 progress, 2026-10-29: the exact reviewed evaluation binary was
applied through retained azd with locking: five additions, zero changes and
zero destroys. A prior pre-apply failure was limited to the ordering of identical
Terraform dependency attributes; its log is retained separately from the
successful retry. Fresh complete MCP hashes covered 2,116 records. Independent
readback then stopped because Azure added `associatedProjects` containing only
the approved child project and `defaultProject` naming that project to the
parent account. One exact-account read found no other compared account change;
the CostControls list is unchanged. The user explicitly approved admitting only
those two absent-to-owned-project bookkeeping additions; the revised
[design](design.md#4b-exact-first-project-bookkeeping-after-evaluation-layer-apply)
defines that narrow transition. The failed receipt is retained, no lifecycle
asset creation or paid call was confirmed at that failure.

Subsequent 6.2 completion, 2026-10-29: the separately approved exact bookkeeping
correction and narrow native serialization handling pass 241 focused
regressions. A distinct source-bound full scoped readback passed with
41 metadata reads, zero mutations/model calls and 2,116 complete record
fingerprints; original sources, baseline, applied binary and failed receipts
remain bound and immutable. No account/project apply or migration execution
was replayed. Final local primary checks pass with 1,461 application tests,
67 skips, 218 evaluator tests and 83 Terraform mock runs; this run did not
enable temporary PostgreSQL integration tests.

Task 6.3 is blocked by actual service authorization: the metadata-only probe's
first catalog-create attempt returned `401 PermissionDenied`; three bounded
GETs of its exact owned evaluator name also failed. Audience/tenant/operator
bindings match, but the service does not identify a missing permission.
The pre-dispatch credential failure and original probe deadline/approval are
retained; no catalog create was replayed and no evaluation/run create or paid
judge call occurred. Catalog absence/deletion is unproven, with the exact
attempt retained privately for recovery. No broader role or scope was added.
Tasks 1.2, 6.1 and 6.3-6.5 remain open.

Subsequent permission decision, 2026-10-29: the user explicitly approved Foundry
User for the selected operator on the existing evaluation project. The
read-only investigation used four Azure GETs: two exact-owned catalog requests
with and without the documented preview header returned identical
`401 PermissionDenied`, and the existing evaluation custom role and exact
operator/project assignment matched saved evidence. That diagnostic allowance
is exhausted. No additional role has been applied by this planning amendment,
and no paid judge call has run. The new
[operator-only permission transition](design.md#4c-approved-project-scoped-foundry-user-authorization-test)
must retain all existing grants and historical receipts. Its fresh bounded
authorization-only reads do not extend or reset the expired lifecycle probe.
Implementation clarification: the pinned AzureRM assignment resource always
reads the assigned role's definition. The user explicitly selected permission
for those exact Foundry User definition GETs rather than adding AzAPI.
This provider-only exception permits neither global role inventories nor
definition reads for other built-ins; all other scope restrictions remain.
The first role-only review stopped on three disclosed refresh-only empty-set
representations and the matching custom-grant output. After disclosure, the
user instructed proceeding with the role. Admit only those exact `null`-to-`[]`
fields identified in design 4c, test rejection of every other difference, and
retain the first review binary unchanged. This is not a new resource mutation
or permission to rerun historical reconciliation.

Live 6.2a-6.2b evidence, 2026-10-29: 237 focused platform tests, strict types,
lint and 14 evaluation-layer Terraform mock runs pass. The successful azd run
also passed its primary-check hook without temporary PostgreSQL integration.
The exact source-bound role plan was applied with locking: one assignment
addition, zero changes and zero destroys; both existing custom roles and
assignments remained no-ops with only the disclosed empty-set representations.
An earlier preprovision formatting-check rejection occurred before any apply
intent; its failed log is preserved. Independent exact-assignment readback
passed with one GET, linking the current source/plan/apply to the immutable
historical foundation without replaying preservation checks.
The fresh bounded catalog test made three exact-owned GETs: two
`401 PermissionDenied` responses followed by `404 UserError`, then stopped.
Its recorded outcome remains blocked because no complete successful listing
was observed. Task 6.2b completes only that diagnostic execution, not catalog,
lifecycle/deletion or paid acceptance. No artifact mutation, upload or model
call occurred. The expired original probe and its unknown remote catalog
version remain unchanged; exact-owned recovery/lifecycle execution still needs
a separately approved fresh envelope.

Fresh 6.3 attempt, 2026-10-29: the user explicitly instructed trying the upload.
A distinct metadata-only journal links the original expired probe and verified
Foundry User grant. Initial launch/credential failures occurred before dispatch;
only proven never-dispatched stages resumed within that same fresh ten-minute
deadline after a successful 30-second CLI-credential runtime check. The actual
native SDK evaluator-registration POST then returned `401 PermissionDenied`.
One catalog-create intent is pending with unknown remote version; no replay,
evaluation/run create, paid judging or two-case score upload followed. Both old
and new uncertain targets remain retained, without absence/deletion claims.
Task 6.3 remains unchecked and the original paid envelope remains unused.
The [runbook](../../../../docs/agent-evaluation.md#actual-publication-retry) records
the private service request reference. Initial inspection of the supplied
public repository found only its local runner, but that did not establish the
absence of another live upload workflow. Subsequent read-only inspection of the
user-linked reference project verified a completed native-Python recorded-score
replay with 16 result rows, seven metrics and zero execution errors, plus the
registered custom rubric. See the
[verified reference](../../../../docs/agent-evaluation.md#verified-native-python-replay-reference).
The user subsequently approved adopting its native inline Python protocol,
including fresh metadata-only lifecycle verification followed by the original
bounded two-case scoring/upload. Design 4d owns that transition. It does not
complete Newsloom acceptance or authorize new resources, grants or paid limits.

- [x] 6.1 Refresh prices, retained-deployment throughput/capacity and explicitly RG/database/project-app-scoped preservation baselines; do not query subscription quota/catalog inventories. Present both exact owning previews, every proposed principal/grant, the verified retention/deletion policy and the cumulative pilot envelope for explicit approval. Include finite publication mutation/read-only polling limits, conservative token-cost reservations, shared deadlines and all prior attempt/unknown-usage reservations. Record unavailable in-scope evidence explicitly. Record approval before applying resources, granting roles or running paid evaluation; expand neither scope nor budget silently.
- [x] 6.2 After 4.4 and live 4.3 pass, apply only the reviewed in-place application prerequisite plan, verify unchanged in-scope account/endpoints/models/workload authority, then apply the reviewed evaluation-layer plan through the existing azd environment. Both approved applies are now complete; do not replay them. Implement and test only the approved absent-to-owned-project `associatedProjects`/`defaultProject` transition described in design 4b, rejecting partial/foreign/additional projects, other account or feature drift and invalid source/evidence bridges. Preserve the original baseline, reviewed/applied binary, source, apply evidence, failed readback and exact account preimages; bind the verifier-only correction in a distinct readback receipt without resetting baselines or admitting changed infrastructure/provider/model/grant intent or unrelated source. Independently verify the project, identities, exact in-scope grants, local-auth denial, deployment visibility and stable runtime settings before dataset upload or judging. No resource reapply, additional migration verification execution, broader permission/check or inherited/effective-access claim is permitted. Keep required parent identity/project-management settings enabled on failure; no account recreation or production image deployment is permitted.
- [x] 6.2a Implement only the separately approved design 4c delta: one Foundry User assignment for the selected operator, principal type `User`, on the existing evaluation project, retaining both custom roles and assignments unchanged. Wire the owning Terraform/azd inputs/outputs, preparation, exact plan/readback checks and directly related runbook guidance consistently. Resolve the built-in role identity through public documentation/private inputs, not global role-definition or directory inventories. Add focused tests for the exact accepted delta and rejected foreign principals/roles/scopes/conditions, extra mutations and historical-source relabelling; run local checks before deployment. Review the saved owning preview for one addition, zero managed-resource changes or destroys and only corresponding output additions, then apply that exact plan in the retained environment and independently read back only the exact assignment. Retain a separate source-bound permission-transition receipt linked to the successful historical foundation; do not replay completed application/project applies, state repair or migration verification.
- [x] 6.2b After 6.2a passes, record and use the fresh authorization-only envelope in design 4c: at most four GETs against the original exact-owned evaluator name, 30-second request timeouts and one ten-minute deadline, counting explicit propagation checks and disabling hidden retries/discovery/context reads. Record the observed authorization outcome without treating assignment existence as catalog success. Permit no artifact mutations, uploads or inference. Preserve the original expired probe approval/journal and unknown catalog version. Continued denial stops work; even successful authorization requires separately approved exact-owned recovery/lifecycle execution before deletion acceptance, judging or publication.
- [x] 6.2c Implement approved design 4d consistently in the publisher, typed approval/journal, exact definition/result verification and ownership-bound cleanup: native inline Python criteria, two create slots, no catalog or publication model request, and explicit separation from historical catalog journals. Preserve existing score/provenance, accounting, privacy, retention and ambiguous-mutation protections. Add actual-SDK offline regressions for native wire shapes, source/threshold/schema drift, fractional and failed scores, missing/duplicate/error outputs, no catalog dispatch, exact two-mutation bounds, historical-journal rejection and run/evaluation-only cleanup. Run focused evaluator tests, lint/types and the relevant primary gate; update the runbook without changing existing grants, infrastructure, production closures or acceptance claims.

Local 6.2c evidence, 2026-10-29: the primary check passes with 240 isolated
evaluation tests, 1,494 application tests and 67 skips, strict types, lint,
formatting, 14 OpenSpec checks and 85 Terraform mock runs. Temporary PostgreSQL
integration was not enabled in this run. Native wire/readback and cleanup tests
match the reference's `completed` execution statuses while retaining failed
quality scores; schema-2 protocol binding rejects old publication journals.
Fresh explicit `catalog-v1` cleanup remains tested without migrating old evidence.
A separately saved one-row lifecycle helper passes an actual-SDK offline test:
two creates, two deletes, nine total GETs and one shared original deadline.
These are local results, not Newsloom sandbox, deletion or paid/UI acceptance.

Live 6.3 native attempt, 2026-10-29: the fresh journal recorded one evaluation
create intent. Its successful HTTP response failed strict definition readback
before an evaluation ID was accepted (`native_probe_definition_drift`).
Execution stopped with zero GETs, no run creation, no deletion and zero model
calls. The exact evaluation name/approval and pending intent are retained
privately; its remote outcome and precise definition mismatch require bounded
read-only recovery. No create was replayed, no check was relaxed and neither
older catalog outcome changed. Native lifecycle/deletion and paid scoring remain
blocked; this is not a successful upload.

Separately approved native recovery used five of its six GETs and one
exact-owned evaluation delete attempt. A two-GET diagnosis verified ownership,
the exact Python source/name/type/threshold and the submitted schema preserved
under `data_source_config.schema.item`, with returned `item_schema` empty.
The publisher's exact-schema check and actual-SDK tests now support that service
representation while rejecting conflicting schemas. Cleanup rechecked ownership
and an empty run inventory, then attempted deletion once. Its acknowledgement
was unvalidated; a subsequent GET returned HTTP 400 reporting missing
`Microsoft.CognitiveServices/accounts/OpenAI/evals/write` for an upstream POST.
Absence remains unproven. No delete/create replay, run, role change or paid call
occurred. The recovery receipt and original failed probe remain unchanged;
additional authorization investigation or another probe needs a fresh decision.
After the schema-only correction, the complete evaluator gate passes 243 tests,
strict types, lint and formatting with the application lock unchanged.

The subsequent approved sample-first instruction in design 4e changes the next
execution order to 6.4, then 6.3, then the conditional decision in 6.3a. It does
not change the historical outcomes above, establish deletion acceptance or spend
any of the still-unused judge allowance.

- [x] 6.3 Only after the successful sample upload and complete API score/lineage readback in 6.4, use a fresh native-Python metadata-only probe in design 4d to verify the actual evaluation publication/reconciliation and exact-owned deletion path, including observed service retention limitations. Within one fresh ten-minute deadline and 60 total GETs, allow at most two creates and two deletes with 30-second requests and no retries. Verify the constant score and zero execution errors, then exact owned disposable run/evaluation removal without affecting foreign assets or the scored report's 30-day retention. Preserve all historical unknown catalog/native outcomes without replay, relabelling or absence claims; retain safe recovery references for new uncertain outcomes. A failed deletion leaves cleanup acceptance unchecked but does not retroactively invalidate the explicitly approved sample-first ordering.
- [x] 6.3a Implement the user's subsequent explicit design 4f approval after the real upload failure, superseding 4e's conditional ordering for this transition only: add Foundry Project Manager for the same selected operator, principal type `User`, at the existing evaluation-project scope through the owning Terraform/azd inputs, outputs, exact preview/apply and independent readback. The exact provider-required definition GETs are separately approved. Run local tests and verify exactly one assignment addition with zero other resource changes/destroys; preserve Foundry User, custom grants and production authority. No account/RG/subscription scope, global inventory, historical apply replay or inferred upload/deletion success is permitted. Retry the retained scores under a distinct bounded publication-only approval/journal and separate ten-minute publication window without rescoring, renewing original inference authority or replaying failed creates; preserve the original scoring approval/deadline unchanged.
- [x] 6.3b Perform only the explicitly requested design 4g account-scope diagnostic: add Foundry User and Foundry Project Manager for the same operator on the retained account with exact deterministic IDs, two-PUT/six-GET/ten-minute ARM bounds and independent readback. Preserve existing project/custom grants, use no broader inventory or mutation replay, and retest the same saved scores with the explicit preview header under a separate bounded publication-only journal. Record actual success/failure without rescoring or claiming minimum RBAC; identify the experimental account assignments for exact-ID Terraform/azd adoption before formal acceptance.
- [x] 6.3c Execute only the user-approved design 4h native account POST comparison: one definition-only POST on each exact account using one verified token, identical payload and the downstream legacy API version. Bound to two POSTs/six owned GETs/ten minutes, retain intent/IDs and compare real HTTP/readback outcomes without replay, run creation, inference, grants or deletion. Do not equate definition creation with successful score upload.
- [x] 6.4 Execute the two-case real DeepEval pilot once before deletion testing under the explicit design 4e exception, after fresh prices, deployment readiness and scoped preflight, using the existing grants and a fresh source-bound native-Python approval/journal. Preserve the approved shared deadline, USD 1 estimated admission ceiling, 12 cumulative attempts and all byte/token/spacing limits. Publish its validated original scores without further judge calls. Retrieve every actual Foundry result page and independently match case IDs, scores, metric origin, explanations and source/configuration lineage before 6.3 begins. Open the returned Evaluations report and verify actual case-level visibility separately; record measured usage/cost exclusions and any expected poor-answer score without turning it into an execution error or rerunning until pass. Failed or uncertain upload does not authorize the conditional Project Manager grant.
- [x] 6.5 Within the defined RG/database/project-app scope, verify final application image/configuration, workload identities/grants, retained account/model/version/capacity/endpoint, schedules/history and independently obtained stored-record fingerprints against the original in-scope before-baselines. Confirm no production-content upload, new model/capacity, unapproved in-scope access changes, unintended logs/caches or orphan probe assets; close owned local clients/helpers and record any retained exact recovery target. State the omitted wider checks without claiming inherited/effective-access preservation. Missing Foundry UI/API parity or in-scope preservation proof leaves acceptance unchecked.

Latest 6.3 completion evidence, 2026-10-30: after API/UI confirmation, the fresh
native metadata probe verified the exact constant score `0.375` with zero
execution errors, then deleted only its own run and evaluation and independently
verified both absent. Two creates, two deletes and 14 reads fit one shared
ten-minute window, with no judging or grant changes. Foundry's asynchronous
`deleted: false` plus operation-location acknowledgement required bounded
exact-target polling; it did not authorize replaying deletes or accepting a
numeric placeholder. Earlier acknowledgement failures and separate approved
recovery windows remain preserved, and all their disposable probe assets are
API-absent. Backup/artifact erasure and historical catalog absence are not claimed.
The cleanup/source and actual-SDK lifecycle gate passed 130 focused tests,
strict types, lint and formatting. Progress is 20/26; Terraform reconciliation,
broader experiment cleanup, final preservation and delivery CI remain pending.

Latest 6.4 completion evidence, 2026-10-30: the updated main publisher verified
both original scores and full lineage through the API under a separate approved
publication-only window. The user then confirmed the matching completed report,
`p01 = 1.0`, `p02 = 0.0` and visible original explanations/provenance in Foundry.
This is user-reported UI verification, recorded separately from immutable API
and scoring receipts. The overview's 50% is consistent with the diagnostic
scores, not an execution failure or calibrated agent-quality claim.
Progress is 19/26; task 6.3 still requires a fresh disposable lifecycle test,
and preservation, infrastructure reconciliation and delivery CI remain open.

Actual 6.4 sample-first evidence, 2026-10-29: fresh prices and scoped readiness
passed, including independent readback of the existing project-scoped Foundry
User assignment. Complete execution history exceeded the old 256-KiB local
control-response cap; a bounded 1-MiB cap preserves full-history checks, covered
by 120 passing context/scoring/publication tests, strict types and lint.
The source-bound real pilot scored `p01=1.0` and `p02=0.0` once using eight
judge calls, 3,051 input tokens and 404 output tokens, with complete usage and
estimated chat cost USD 0.004516875. Publication created its evaluation and run
but raised `publication_service_error`. Read-only reconciliation found exactly
one owned run; exact run readback reported `failed`, zero output rows and
`UserError` naming missing `Microsoft.CognitiveServices/accounts/OpenAI/evals/write`.
The complete output page was empty. Original results/accounting and exact
remote references are retained privately. No scoring/create replay, deadline
renewal, deletion test or additional grant occurred. Successful upload and
API/UI parity remain unverified, so 6.4 stays open and the conditional Project
Manager grant is not triggered. This newer evidence supersedes earlier
zero-paid-call status, not the historical receipts themselves.

Actual 6.3a evidence, 2026-10-29: 245 focused platform tests, strict types/lint
and 16 evaluation-layer Terraform mock runs pass. The owning preview admitted
exactly one project/operator Project Manager assignment addition and zero
other changes/destroys. The successful azd apply passed its ordinary local
preprovision check; independent exact-assignment readback passed. An earlier
wrapper-only pre-hook failure had no apply intent and is retained, not relabelled.
The separately approved publication-only retry used a fresh ten-minute window
and distinct ownership while preserving the original scoring approval, deadline,
two scores, source and eight-call accounting. Its actual-SDK network-denied
regression passes. The live retry created a distinct evaluation/run, but exact
readback still reported `failed`, zero evaluated rows and `UserError` with inner
`PermissionDenied` for `Microsoft.CognitiveServices/accounts/OpenAI/evals/write`.
No judge/create replay, deletion test or broader grant occurred. Task 6.3a is
complete for the role transition and attempted retry only; successful upload,
API/UI parity, lifecycle/deletion and overall delivery remain unchecked.

Subsequent user-approved explicit preview-header test, 2026-10-29: offline
inspection confirmed the SDK's `allow_preview=True` does not add
`Foundry-Features: Evaluations=V1Preview` to native OpenAI evaluation requests.
Four actual-SDK offline regressions pass for explicit header delivery, score
preservation, read-only recovery and nested grading-error rejection. The live
private test preserved both project-scoped grants and the same two scored rows;
every admitted request carried the header. Two create slots and seven GETs in
one fresh ten-minute publication-only envelope yielded one exact matching run
in `failed` state, `UserError` / `PermissionDenied`, with zero evaluated rows.
Its exact missing action remains unestablished. No inference, role/scope change,
delete or mutation replay occurred, and no production-source header fix is
claimed from this experiment. Header alone did not pass API/report acceptance;
task 6.4 and the overall 16/24 status remain unchanged.

Actual 6.3b evidence, 2026-10-29: two focused offline regressions pass for exact
account-only grants and native saved-score publication with the preview header.
Two account-scoped role PUTs and two independent exact-assignment GETs passed
for the existing human operator, retaining project/custom grants. These are
explicitly approved controlled ARM diagnostic grants, not Terraform-owned
resources; their exact private IDs/receipts require owning-layer adoption before
formal acceptance. The immediate distinct publication-only retest used six GETs
and two create slots, with the explicit header on every admitted request, but
still reported `failed`, `UserError` / `PermissionDenied` and zero evaluated
rows. A token check independently confirmed the same operator, tenant and
expected AI audience. No inference, deletion or mutation replay occurred.
Propagation and the service-side cause remain unproven. Task 6.3b is complete
for this diagnostic only; task 6.4/API/UI acceptance remains unchecked.

Subsequent user-approved fresh-token retry, 2026-10-29: five offline regressions
pass for genuine MSAL force-refresh, cached/foreign-token rejection and exact
fresh-token SDK use. Both account grants were read back again. The live token
came from the identity provider, differed from the cached value and had a newer
issuance time, with the same operator/tenant and expected AI audience. Every
admitted request used it and the preview header. Two create slots and seven
GETs still yielded a failed run with `UserError` / `PermissionDenied` and zero
evaluated rows. No token was retained in experiment artifacts, no scoring or
grant was repeated, and no deletion occurred. Exact private references and
token-free proof are preserved; overall progress remains 17/25 with 6.4 blocked.

Actual 6.3c evidence, 2026-10-29 at 22:41:20 UTC: four offline regressions pass
for byte-identical payloads, a single token, explicit denied/unknown outcomes
and prevention of POST replay. Both exact accounts returned HTTP 201 to the
same minimal native `POST /openai/evals?api-version=2025-04-01-preview`.
Both independent exact-definition GETs returned HTTP 200 and verified ownership,
name, grader and custom type. Two POSTs/two GETs, zero runs/model calls/grants/
deletes; exact private cleanup references remain retained. Current native
operator create permission and the dated operation are demonstrated for this
payload. This does not identify Foundry's internal caller, publish scores or
prove that a newly attempted project-mediated run would still fail. Task 6.3c
is complete for the A/B diagnostic; overall progress is 18/26 and 6.4 remains open.

## 7. Source-bound publication and honest status

Pre-reconciliation checkpoint, 2026-10-30: exact Terraform/azd adoption
and independent seven-resource readback passed. A separate exact two-destroy
plan removed only the unused project-identity telemetry grants; readback
verified five retained resources and both assignments absent. Fifteen of the
16 allowlisted failed evaluation/run pairs are API-absent, with protected
reports still present. One timed-out DELETE remains unresolved and was never
replayed. The native A/B definition is removed; exact historical probe/catalog
reads and their version correction are recorded in the runbook.
Workload/model/app-registration preservation matches, and the application
preview has 32 no-ops. A newly explicit, separate one-use READ ONLY authorization
permitted exactly one existing migration-job execution, without replaying the
original consumed exception. Read-only recovery of that same successful
execution verified all 2,116 accepted baseline records unchanged among 2,139
current records: zero missing, zero changed and 23 additions. Job configuration
and identity remained unchanged, with zero database writes or model calls.
The failed previous-day restore-timestamp guess remains preserved. The actual
original timestamp was then recovered from the original server/RG-scoped tool
request/result; changing only that field reconstructs the historical PostgreSQL
boundary SHA-256 exactly, without changing old evidence.
An explicitly approved fresh retry removed the final failed evaluation/run
pair with two DELETE attempts and 47 reads. Independent GETs now verify all
16 allowlisted pairs absent and all four protected reports present; original
expired journals and cumulative counters remain retained.
Final scoped metadata readback used 41 reads and preserved workloads, models,
directory, production principals, original grants and the five exactly approved
Terraform-owned grant additions. It initially remained blocked on one new account endpoint
descriptor and the evaluation storage's inherited Defender-managed Event Grid
system topic/subscription. Storage-scoped Defender settings and Microsoft's
resource contract establish the scanning dependency; neither scanning nor its
resources were changed. The user subsequently approved the exact audited
reconciliation and clarified that policy-managed Defender additions are outside
application ownership and must not expand this delivery. Apply only
[design 4j](design.md#4j-final-audited-preservation-reconciliation), retaining
the blocked snapshot, baseline and actual component verification times. Verify
the exact account reconstruction, approved resource/grant deltas, complete
record evidence and bounded execution-history chronology before closing 6.5;
do not silently normalize hashes or directly manage security side resources.
The final local primary gate passed with 290 evaluator tests, 1,510 application
tests and 67 explicit local-PostgreSQL skips, plus types/lint/build/OpenSpec and
Terraform checks (19 evaluation-layer tests). Task 6.5 and delivery publication
remain open; progress stays 20/26.

Latest user-approved quick project-mediated retry after successful native
definition creation still failed: fresh token verified, preview header on all
requests, two create slots/seven GETs, `UserError` / `PermissionDenied`, zero
evaluated rows. The tested runner was reused with a new attempt cursor, leaving
old journals/deadlines unchanged. No judging, grants or cleanup occurred.
This reproduces the full project-flow failure but does not isolate the internal
principal or full-payload translation. Progress remains 18/26; 6.4 stays open.

- [x] 7.1 Update the evaluation runbook with actual compatibility, source/configuration, owning preview/apply, API/report visibility, retention, privacy, budget and preservation evidence; update only directly owning ADR/PRD links. Publish the verified implementation and wait for exact-commit primary CI, preserving unrelated customization edits. Keep Step 2.3/P2-C06 incomplete and distinguish the evaluator source from the unchanged agent image provenance.
- [x] 7.2 Publish a separate measured evidence/status receipt after implementation CI passes, including exact report references kept private where required, actual counts, incomplete-usage reservations, cleanup and evidence limitations. Wait for that receipt's exact-SHA CI before completing delivery acceptance; no hypothetical or failed verification may become a passed task.
- [x] 7.3 After the evidence/status CI passes, mark only this foundation delivery's completed gates and publish its completion ledger with final exact-head CI. Verify all foundation tasks have evidence while the frozen baseline/calibration, candidate comparison and online-monitoring slices remain pending; do not synchronize or archive this change automatically.

## Workflow follow-up

- Review the completed foundation evidence before synchronizing/archiving this
  change, then verify the published contract and updated documentation links.
- Propose the next small Step 2.3 slice for frozen questions, calibrated judges
  and the Foundry-visible quality baseline; design private online monitoring
  and paid automation separately without assuming production-content consent.
