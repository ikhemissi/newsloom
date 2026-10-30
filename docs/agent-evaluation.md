# Agent evaluation

## Status and scope

This is the active [evaluation foundation](../openspec/changes/agent-evaluation-foundation/proposal.md),
not the frozen quality baseline or completed
[P2-C06](prd-2-capabilities.md#p2-c06-repeatable-agent-quality-and-azure-acceptance).
The [task ledger](../openspec/changes/agent-evaluation-foundation/tasks.md) owns
acceptance status. Research is already delivered; its measured evidence belongs
to the [agent runbook](agent.md).

On 2026-10-30 a separately approved publication-only diagnostic achieved
[exact two-case API parity](#recorded-score-wire-format-diagnosis-and-first-api-parity)
without rescoring. The successful diagnostic used integer JSON representations
of the original boundary scores, a minimal replay grader and strict output
wrapper handling. That diagnostic alone did not establish fractional support.
A subsequent
[fractional publication regression](#fractional-publication-regression)
verified canonical-string score encoding in two nine-case runs.
At that diagnostic stage, UI, lifecycle/deletion, infrastructure adoption and
overall delivery acceptance remained incomplete. The
[main-publisher integration](#main-publisher-canonical-score-bridge) is now
implemented and locally verified. A fresh publication-only upload through that
updated publisher also verified the original two cases through the Azure API.
The user has since [confirmed case-level UI visibility](#user-confirmed-foundry-ui-acceptance).
The subsequent [disposable lifecycle proof](#post-upload-disposable-lifecycle-proof)
also passed, and the
[Terraform reconciliation](#terraform-reconciliation-of-climanual-experiments)
is complete. All 2,116 accepted baseline records retain their exact fingerprints;
23 additional records were observed. All 16 allowlisted failed experiments are
now API-absent, with all four protected reports still present. The PostgreSQL
boundary difference has been exactly reconstructed from historical tool
evidence as a rolling restore-date change, without overriding its original hash.
Final scoped readback found two further metadata/resource differences. The
explicitly approved
[audited final reconciliation](#final-audited-preservation-acceptance) now closes
preservation without rewriting that blocked snapshot or changing Defender.
The active ledger is 23/26; source-bound implementation, separate evidence/status
and completion publication with exact-SHA CI remain open.

Verified locally: the separately locked evaluation project resolves on Python
3.15.1, real DeepEval and Projects SDK imports and mocked wire execution succeed
with network admission blocked, and import-time privacy checks pass. The application lock and all six
production dependency graphs remain unchanged; isolated agent startup and six
application package builds pass. The current isolated check passes 290 tests, strict
types, lint and formatting, including the complete bounded scoring pipeline
with real DeepEval and the native OpenAI SDK over scripted transports.
The native SDK publication pipeline and ambiguous-outcome recovery also pass
against scripted transports, as do exact-owned cleanup and fresh-process
privacy canaries. The Azure foundation, actual service/sandbox
execution, API/report visibility and paid acceptance are not established by
those tests.

The evaluation project and four grant resources were provisioned on 2026-10-29;
their independent scoped readback subsequently passed as recorded
[below](#corrected-readback-and-lifecycle-blocker). No new model has been created.
The [subsequent real sample-first attempt](#real-sample-first-scoring-and-upload-attempt)
scored both cases, but its Foundry run failed before producing output rows.
The [explicitly approved Project Manager addition and publication retry](#verified-project-manager-and-failed-upload-retry)
are now applied/read back; the new run still failed the same write permission
with zero evaluated rows and no rescoring.
The subsequent [account-scope diagnostic](#account-scope-role-test-and-immediate-retest)
verified both built-in roles on the retained account, but its immediate
saved-score retest still failed authorization. Those experimental account
assignments are now managed by the
[exact-ID Terraform reconciliation](#terraform-reconciliation-of-climanual-experiments);
the remaining preservation and delivery gates still apply.
The approved account prerequisite
update's original failed readback remains retained. Audited reconciliation
passed on 2026-10-29 within the reduced verification scope, before the project
apply. The metadata-only probe reached the native evaluator catalog but was
denied with `401 PermissionDenied`. The separately approved
[project-scoped Foundry User assignment](#project-scoped-foundry-user-transition)
is now applied and independently verified. Its bounded catalog reads returned
two `401 PermissionDenied` responses followed by `404 UserError`, not a
successful catalog listing. A freshly approved
[actual evaluator-registration POST](#actual-publication-retry) after that
grant still returned `401 PermissionDenied`. At that historical stage,
lifecycle/deletion and paid acceptance remained blocked; no other role or scope
expansion had been attempted.
The user approved replacing catalog-first publication with native inline Python
graders. The implementation now uses two create slots and protocol-bound
approvals/journals; at that stage native lifecycle and paid/API/UI acceptance
were unverified. Its first native evaluation-create response failed strict
definition verification before an evaluation reference was accepted. No run,
deletion or model call followed; see the [native attempt](#native-python-live-attempt).
Historical catalog outcomes are not reinterpreted or removed.

On 2026-10-28 the user approved **foundation provisioning only**: refresh and
apply the two owning account/project/grant plans, then independently verify
their deployed state. This does not authorize paid inference, evaluation runs,
content uploads, new model deployments, production redeployment or the
metadata-only lifecycle mutation probe. Actual deployment evidence is recorded
separately below; approval alone is not a successful deployment.

The user subsequently approved the existing finite synthetic-pilot envelope,
including the preliminary metadata-only lifecycle probe, paid judging and
publication, subject to the preservation/authorization/deletion gates. This
adds no authority for production content, new models/capacity or broader roles.
The judge remains the existing GPT-5.4-mini after the comparison below.

## Owning infrastructure boundary

The [application root](../infra/main.tf) configures project management and a
system-assigned identity directly on the retained AIServices account. These
are lasting prerequisites, independent of whether the evaluation layer is
enabled. The account's `prevent_destroy`, disabled local authentication,
subdomain, model definitions and production workload grants remain configured.
Both owning roots pin AzureRM exactly to 5.10.0. Native azd preview initialization
reselected 5.11.0 under the application's previous `~> 5.10` constraint despite
its lock file; that unapproved preview was rejected. The exact constraint
prevents that implicit upgrade.
[Application outputs](../infra/outputs.tf) expose the resulting identity and
project-management state for independent readback.

The separate [evaluation root](../infra/agent-evaluation/) is registered in
[azd](../azure.yaml), depends only on `application`, and uses the existing
AzureRM 5.10.0 provider with Entra-authenticated state at
`newsloom/<environment>-agent-evaluation.tfstate`. It creates no model, account,
application, diagnostics setting or standalone execution identity. The optional
data-resource extension below also pins AzAPI 2.13.0 within this layer only.
Its disabled default has no resources or identity-context reads.
The base foundation resource boundary is:

- One child project with its own system-assigned identity and destruction guard.
- Two custom data-only role definitions, with no management actions, keys,
  connection secrets, wildcard data permissions or inherited-role substitutions.
- Two assignments to the exact selected human operator: chat completions on
  the retained account, and the evaluation operations below on this project.
  Neither new managed identity nor any production workload receives a grant.
- An optional, separately approved Foundry User assignment to that same
  operator on this project only. The original two roles/grants are retained;
  its input defaults to empty and its output is separate from the original
  custom-grant inventory.
- An optional, separately approved Foundry Project Manager assignment to that
  same operator on the existing project only, retaining the User/custom grants
  and exposing a separate assignment output. Its private input is
  `AGENT_EVALUATION_FOUNDRY_PROJECT_MANAGER_ROLE_ID`; the default remains empty
  and its value is checked against the documented role's public fingerprint.
  The user's explicit post-upload-failure approval supersedes the earlier
  deletion-dependent condition for this one transition; apply/readback and
  retry acceptance remain separate evidence.

The user selected account-scoped chat-only operator access. This is not
deployment-level IAM isolation: it authorizes future chat-capable deployments
in the account too. The fixed judge transport and approval still admit only
the selected deployment/model snapshot. The broader built-in Foundry User
role was excluded from the initial foundation. After the catalog denial, the
user explicitly approved the project-scoped operator-only addition described
under [the permission transition](#project-scoped-foundry-user-transition).

The candidate project role enumerates the registered provider data actions
`Microsoft.CognitiveServices/accounts/AIServices/evaluations/read`,
`Microsoft.CognitiveServices/accounts/AIServices/evaluations/write`,
`Microsoft.CognitiveServices/accounts/AIServices/evaluations/delete`,
`Microsoft.CognitiveServices/accounts/OpenAI/evals/read` and
`Microsoft.CognitiveServices/accounts/OpenAI/evals/write`. Native registration
proves that these operation names exist, not that every catalog/run/delete
route authorizes against this set. Exact catalog/lifecycle mapping, native
project scoping and actual report access remain unverified. A permission
failure must stop for review, never add another role or account-wide evaluation
authority as an implicit fallback. See the official
[evaluation permissions](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluation-permissions)
and [custom-role guidance](https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry#create-custom-roles-for-projects).

### Metadata-only preparation

The [platform preparer](../services/platform/src/newsloom_platform/agent_evaluation.py)
is exposed as `newsloom-platform prepare-agent-evaluation-layer`; azd invokes
it for this layer. Disabled preparation initializes only missing private
evaluation inputs and preserves existing operator/output values. Enabled
preparation checks the retained account ID/name/endpoint, selected CLI
subscription/tenant/human operator, local-auth denial, account identity and
the existing chat model/version/SKU/capacity/no-upgrade contract. Its four CLI
operations are local selected-account context, an ARM credential acquisition,
and two in-RG metadata reads. Operator binding uses tenant/object/expiry claims
from the trusted CLI credential, not an unrelated directory-user lookup.
Only the verified evaluation operator and tenant inputs, and a missing empty
Foundry User opt-in input, are written back to the private azd environment.
The optional `AGENT_EVALUATION_FOUNDRY_USER_ROLE_ID` must match the fingerprint
of Microsoft's documented built-in role; it is never discovered through a
global role inventory.

Preparation can report `account_prerequisites_ready=0` while reviewing the
staged parent change. That permits preview preparation, not provisioning,
inference or a claim that the project prerequisites already exist. A changed
previously bound operator/tenant, foreign account, model drift or unexpected
identity fails before any environment updates. It never builds images,
creates registrations, assigns roles, invokes a judge or imports evaluation
dependencies into the application environment.

Focused preparation/regression checks:

```bash
uv run --locked pytest tests/test_agent_evaluation_foundation.py tests/test_agent_control.py tests/test_agent_identity.py tests/test_platform_control.py
terraform -chdir=infra/agent-evaluation init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/agent-evaluation validate
terraform -chdir=infra/agent-evaluation test
terraform -chdir=infra test
```

Verified locally: 183 focused platform regressions, including all 42 new
preparation/boundary tests, pass, together with 12 evaluation-layer and three
application-root mock runs. Strict types cover 133 source files; repository lint,
formatting, platform package build and CLI help also pass. The application lock
remains unchanged.

The [foundation verifier](../services/platform/src/newsloom_platform/evaluation_verification.py)
adds saved-native-plan review and independent deployed-readback guards. Its
124 tests cover exact inventories, replacement/foreign-scope rejection,
source and provider binding, private evidence, paginated metadata, drift and
staged-parent readback. The combined focused platform suite passes 307 tests;
strict types cover 135 files. These are local tests, not fresh Azure previews,
working catalog authorization or deployment acceptance. The primary check
discovers these tests and includes the new layer's locked initialization,
validation and Terraform tests.

### Native preview and preservation verification

`newsloom-platform verify-agent-evaluation --manifest <private-file>` has three
strict modes: `baseline`, `plan` and `readback`. None provisions, grants access,
executes a workload or calls a model. Azure metadata uses at most 100 bounded
CLI invocations within 600 seconds, with a 30-second per-invocation timeout,
ten pages per ARM inventory and 4,096 rows per inventory. CLI-internal HTTP
requests/retries are not claimed as separately counted requests. Directory
and role-definition reads share that envelope.

All evaluation checks use the user-approved
[verification boundary](../openspec/changes/agent-evaluation-foundation/design.md#verification-scope):
the selected Newsloom RG and its resources, the configured Newsloom database
there, and the exact MCP API/client and agent API/client registrations with
their federation/consent configuration. Requests and pagination are guarded
before dispatch. RBAC is queried at the RG, retaining only assignments scoped
to it or its resources; the verifier never lists subscription-wide assignments
or follows principal grants into other RGs. It reads only the evaluation-owned
custom definitions restricted to that RG, through RG-scoped requests, not global
built-in definitions. Subscription quota/catalog inventories and unrelated
directory/database lookups are excluded.

Receipts bind `newsloom-rg-verification-v1`, including the exact RG, database and
four app IDs, and explicitly name omitted checks. Unscoped receipts are not
current proof. This does not claim unchanged inherited grants or complete
effective access. Preparation and paid-pilot admission use CLI credential claims
instead of directory-user reads; paid-pilot ARM reads also enforce the RG.
Unavailable in-scope proof stops verification rather than widening this boundary.

Keep manifests, binary plans, independent data receipts and outputs directly
inside the selected environment's ignored `evaluation-verification` directory.
The directory must be owned by the operator and mode `0700`; inputs must be
regular, nonsymlinked, operator-owned `0600` files, at most 32 MiB. Outputs are
exclusive, fsynced `0600` files: use a new name, never overwrite a review.

After the full local gate, prepare only the reviewed private inputs:

```bash
umask 077
install -d -m 700 .azure/dev/evaluation-verification
azd env set AGENT_EVALUATION_ENABLED true
uv run --locked newsloom-platform prepare-agent-evaluation-layer
```

This changes retained local inputs only, not Azure resources. Obtain a fresh
independent stored-record receipt through the existing authorized MCP read
identity verification path, not through article-returning tools or research
generation. The verifier consumes that trusted operator-supplied receipt; it
does not manufacture SQL evidence or establish its origin from a boolean flag.
The strict receipt fields are:

- `verified_utc`: UTC verification time, at most 15 minutes old when consumed.
- `outcome="success"`, `probe="independent_stored_record"` and
  `mcp_read_identity_verified=true`, from the independent probe.
- A positive integer `news_count` and SHA-256 `news_metadata_fingerprint`,
  `recent_id_sha256` and `recent_url_sha256`.
- Integer `writes_performed=0` and `model_calls=0`; no additional fields or content.

Create one baseline manifest for each layer before either preview. For example:

```json
{
  "mode": "baseline",
  "layer": "application",
  "output": ".azure/dev/evaluation-verification/application-before.json",
  "stored_record": ".azure/dev/evaluation-verification/stored-before.json"
}
```

Use `layer="agent-evaluation"` and a distinct output for the evaluation baseline.
Run each manifest through the command below. Baselines bind the current
source, retained environment and exact signed-in human operator; they expire
after one hour. Capture them after long local checks, not before.

```bash
uv run --locked newsloom-platform verify-agent-evaluation \
  --manifest .azure/dev/evaluation-verification/application-baseline-manifest.json
```

Preview only the two owning layers, preserving existing azd state. Do not use
`--debug`, reconfigure/migrate a backend, or run an unqualified deployment.
Capture preview output privately: Terraform output can contain deployment
configuration. The retained azd cache uses these binary plan locations:

```bash
azd provision application --preview \
  > .azure/dev/evaluation-verification/application-preview.log 2>&1
install -m 600 .azure/dev/infra/main.tfplan \
  .azure/dev/evaluation-verification/application.tfplan
azd provision agent-evaluation --preview \
  > .azure/dev/evaluation-verification/evaluation-preview.log 2>&1
install -m 600 .azure/dev/infra/agent-evaluation/main.tfplan \
  .azure/dev/evaluation-verification/evaluation.tfplan
```

Only copy a plan after its preview succeeds. Review it with a new manifest:

```json
{
  "mode": "plan",
  "layer": "application",
  "output": ".azure/dev/evaluation-verification/application-review.json",
  "baseline": ".azure/dev/evaluation-verification/application-before.json",
  "plan": ".azure/dev/evaluation-verification/application.tfplan"
}
```

Repeat with the evaluation layer and its own paths. The verifier calls
`terraform show -json` with the owning root's locally initialized provider.
It checks the binary's embedded Terraform source and provider lock byte for
byte against that root, including the selected AzureRM 5.10.0, plus native
variables, time, prior/planned state, action and unknown-value boundaries.
JSON substituted for a binary plan, source drift, state drift, replacement,
unrelated changes and unbound computed grants fail. The private review
contains exact operator/scope/operation inventory and binary/source hashes.
Inspect it before seeking task 6.1 approval; a review is not approval.

Staged evaluation preview is allowed before the parent prerequisites exist;
`account_prerequisites_ready=0` explicitly prevents interpreting that preview
as deployed readiness. After approval, verify the application update first.
For readback, change the owning review manifest to `mode="readback"`, select a
new output, and add `review` pointing to its exact successful plan review plus
`stored_record` pointing to a newly obtained independent after-receipt.
Retain the same `baseline` and binary `plan`.

Evaluation readback from a staged baseline additionally requires
`parent_readback` pointing to the successful application readback. It verifies
the parent transition against the original baseline, then compares evaluation
changes against that independently verified parent snapshot. This preserves
the originally reviewed evaluation binary instead of silently regenerating
an approved plan after the parent update.

Readback uses ARM/Graph metadata, not Terraform outputs alone: account
key-auth/identity/endpoints, all three models, six workload templates/images/
schedules, five workload identities, the retained Phase 1 acceptance identity,
directory registrations/federation/consent,
resource inventory and exact native role permissions are preserved. PostgreSQL
Entra-only authentication, server/network/storage settings, administrators and
firewall rules are independently inventoried too. Project
identity/tenant/native endpoint maps and outputs must agree. Any unexpected
assignment to either new identity, existing workloads, or any principal in the
retained resource-group/account/project scopes fails. Assignment coverage is
the selected RG and descendant scopes only; inherited grants, assignments
elsewhere and global built-in definitions are explicitly excluded.

Job execution histories are retained privately as reconciliation evidence;
normal executions need not remain byte-identical. An unexplained stored-data
count/fingerprint change still fails, even when a scheduled job completed.
The failed receipt retains the after-snapshot and safe category. Reconcile
the independent data evidence and scheduled history before acceptance; do
not erase the original baseline, assume unchanged data, or invent an override.
No live preview/readback success is established by the local tests above.

### Complete local integration gate

The PostgreSQL-enabled `bash scripts/check.sh` passes: 1,496 application tests,
218 isolated evaluation tests and 83 Terraform mock runs. The only skipped test
is the intentionally excluded live-publisher integration test; local database
tests ran against an owned PostgreSQL 18/pgvector container, which was stopped
and removed afterward. Types, lint, formatting, identifier checks, strict
OpenSpec validation and documentation links/command syntax pass. DeepEval emits
608 upstream deprecation warnings; they are not test failures or suppressed
privacy failures.

The 124 verifier tests distinguish the five named production workload identities
from the retained Phase 1 acceptance identity. All resource-group identities and
their grants remain in preservation evidence; an extra retained identity cannot
substitute for a missing production workload identity.
Native serialization regressions also cover azd's canonical raw `"true"` input
before Terraform's boolean conversion, the provider's computed-only project
`default` field, and its explicit `null` representation of empty optional
`not_data_actions`. Other missing/invalid permission fields and noncanonical
enablement values still fail.

All six Python packages build successfully. Each original production dependency
graph matches its pre-evaluation baseline, and actual isolated installations of
all six packages contain neither DeepEval nor the Projects SDK. The application
lock SHA-256 remains
`6cab3f29a6220f1e3c92585df919ccda964752eb7ee94790d78fddb3648a1aed`.

The tested evaluator source SHA-256 is
`426557a0683907a9350b509e00120d3434c5cb93761e3e6b8392a343365c250d`.
The [source binding](../tools/agent-evaluation/agent_evaluation/inputs.py)
includes the evaluator manifest/lock/code, authored fixture, application
manifest and isolated-check script. This is evaluator provenance, not a claim
that this checkout built the accepted research image. No application container
image was built or deployed. These local results do not complete native Azure
preflight, deployment, actual Foundry API/UI acceptance or exact-source CI.

The scope correction and reconciliation pass 256 focused platform regressions and 25 isolated
context tests within these totals. Forbidden requests are rejected before
dispatch, including foreign RGs, global role definitions, unrelated apps and
other databases. Historical wider-scope evidence is explicitly projected, not
reused as current proof. These local tests start no migration verification
execution, provisioning or evaluation; live reconciliation is recorded below.

### Stopping and rollback

Stop evaluation execution first and reconcile exact owned assets with the
cleanup procedure below. Retain the accepted report for its approved window.
Remove evaluation grants/project only through separately reviewed owning
Terraform after ownership, retention and dependency checks. The project's
`prevent_destroy` intentionally blocks using `AGENT_EVALUATION_ENABLED=false`
as an accidental project-deletion shortcut; retirement requires an explicit
reviewed change. Never delete or recreate the account, remove its required
identity, or disable project management to undo this slice.

Do not run an unqualified all-layer deployment: existing application image
hooks are not evaluation setup. This slice does not rebuild or deploy the
research agent, and its changed checkout is not the source of the accepted
agent image. The original owning native previews passed source-bound review.
The failed preservation gate has since been reconciled as recorded below;
fresh evaluation-layer review and deployed acceptance remain pending.

### Applied parent and blocked preservation readback

The user-approved application plan was applied through retained azd with an
operator-private Terraform guard. Because azd 1.36 regenerates its plan during
provisioning, the guard compares the regenerated native JSON with the reviewed
binary, excluding only the plan timestamp, and applies the exact reviewed
binary with state locking enabled. The applied binary SHA-256 is
`63ad82f72c03f9e57146d342f590ba8b866c51bffe1c184936a1cd00e0027081`;
the verified source remains
`2dc861f4cd283b3bbdf3491fd15af296b465d7139d6b84aba1b970c804fa9153`.
Account project management and its required system-assigned identity are now
enabled and must remain enabled.

Independent readback failed `evaluation_verification_preservation_drift`.
The original before-baseline and failed after-receipt are retained, unchanged.
Read-only diagnosis established:

- The account additionally reports
  `properties.armFeatures = ["Microsoft.CognitiveServices/CostControls"]`.
  An independently retained raw before-account matches the original account
  fingerprint, and the live raw after-account matches the failed receipt.
  No other account invariant, including endpoints/local-auth configuration,
  differs after excluding the two explicitly approved prerequisite settings.
- Several inherited built-in role definitions return different `createdOn`/
  `updatedOn` metadata. Their permissions, scopes and all assignments are
  unchanged; the original verifier compared entire definition payloads.
- The stored-news count grew from 2,106 to 2,108 while scheduled jobs remained
  enabled. This is not proof that the original records were unchanged.
  A read-only attempt to reconstruct the original subset using `created_at`
  was denied by the MCP identity's existing column privileges. That denial
  was retained explicitly; MCP access was not expanded.

At that point the parent deployment was not accepted as preservation-verified. No project,
new evaluation roles/assignments, lifecycle artifacts or paid evaluation calls
were created afterward. The local evaluation enablement flag was restored to
false and the owned local PostgreSQL helper was stopped and removed. An
explicit, tested reconciliation proof is required before proceeding;
neither new baselines nor metadata normalization may conceal the failure.

### Audited preservation reconciliation

The approved [reconciliation contract](../openspec/changes/agent-evaluation-foundation/design.md#4a-evidence-bound-reconciliation-after-failed-readback)
is implemented by the platform's
[reconciler](../services/platform/src/newsloom_platform/evaluation_reconciliation.py)
and [fixed record probe](../services/platform/src/newsloom_platform/evaluation_record_probe.py).
This is not an override or a second application deployment. The original source
preimage and all original review/apply/failure evidence are preserved in private,
hash-bound archives before verifier edits. The explicit source transition permits
only the reconciler, probe, verifier, CLI, platform preparer and isolated
evaluation-context implementation/regression changes needed for the approved
reconciliation and scope restriction. All other source, owning Terraform and
provider-lock bytes must still match.

Use the existing private evidence directory and a strict manifest:

```bash
uv run --locked newsloom-platform reconcile-agent-evaluation \
  --manifest /absolute/private/reconciliation-manifest.json
```

The manifest requires `action`, `output`, `preservation`, `source_archive`,
`evidence_archive`, `baseline`, `review`, `plan`, `approval`, `intent`,
`completion`, `failure`, `account_before` and `account_after`. `action: verify`
also requires the completed `probe` execution receipt; `action: execute-records`
forbids it. All paths use the verifier's owner-only, ignored, nonsymlinked evidence
rules. Outputs are exclusive and never replace the failed readback.
An optional `state_repair` links the separately approved state/output-only
recovery: exactly two computed account-identity outputs, 32 managed-resource
no-ops and only the observed empty identity-list representation difference.
It binds exact native source/binary, independently checked ARM identity values,
the apply intent, backend locking and before/after state backups with unchanged
lineage. It does not relax ordinary plan drift checks or permit cloud resource
changes, account-update replay, state migration or reconfiguration.
Raw backups remain unchanged; comparison canonicalizes Terraform's unordered
check-result/object inventories by their unique addresses, retaining every
status and payload field and rejecting duplicate addresses.
The approved recovery succeeded with state serial 17 to 18, both identity
outputs independently matched, and zero Azure resource mutations. The linked
receipt retains that operation's original source separately from the later
scope-enforcement source; neither the recovery nor its unchanged native plan is
replayed.

The narrowly approved metadata comparison binds both raw account preimages,
allows only the exact CostControls addition, and projects the original evidence
onto the explicitly reduced verification boundary. The former ten-definition
built-in timestamp rule is superseded, not expanded: no current global-definition
or inherited-grant check is performed. Original wider-scope receipts and their
failure remain unchanged and linked by digest. RG/resource assignments and
evaluation-owned RG-restricted custom permissions, exclusions, scopes and
conditions remain exact; so do in-scope identity, local-auth, model, runtime and
database checks. A reduced-scope success cannot stand for wider preservation.

The one authorized migration-identity fallback uses the exact existing manual
job, identity, digest-pinned image and environment. It overrides only that
execution's command/arguments, not the saved job or schedule. An fsynced,
environment-wide execution intent prevents replay, including after an ambiguous
start. It never invokes migration startup. PostgreSQL verifies READ ONLY and
REPEATABLE READ before news reads, with 60-second statements and a 540-second
transaction bound. Program timeout, bounded CLI calls, and an exact-execution
stop reserve keep the operation inside the approved 600-second envelope.
An uncertain start consumes the one execution; it cannot be retried.

The probe deterministically selects rows at the original stored-record receipt's
cutoff and at the failed receipt's cutoff. Both original counts, aggregate hashes
and recent ID/URL hashes must match exactly. It returns every current metadata
fingerprint and every row's historical membership, not production text or raw
record identities. Reads fail beyond 4,096 rows or 512 KiB; the independent byte
cap can reject fewer rows. Chunked compressed output has complete sequence and
digest checks. Count growth alone never passes.

The versioned `news-metadata-v1` evidence contains SHA-256 ID/metadata pairs for
the same complete metadata-column set used by the original probe. A subsequent
MCP-identity read can produce those pairs without `created_at` privileges.
Comparisons reject changed/missing/duplicate original pairs and explicitly
identify all added pairs. Future baselines/readbacks must name the reconciliation
receipt and retain its original failed-evidence lineage. Historical proof does
not expire merely because it is old; each newly admitted data read must be fresh.

Real PostgreSQL tests verify exact historical reconstruction, denied writes even
under the local administrator, refusal of unenforced read-only mode, and full
MCP fingerprints while its hidden-column query remains denied.

On 2026-10-29 the source-bound live reconciliation passed. Both historical
aggregates, counts and recent ID/URL hashes reconstructed exactly: all 2,106
original records are unchanged, with two additions at the failed readback and
seven later additions. Complete `news-metadata-v1` evidence covers all 2,115
records. The sole approved execution used the unchanged migration job/image/
identity with READ ONLY SQL; its saved job remained unchanged. No migrations,
database/resource writes, new grants, image changes or model calls occurred.

The execution reached `Succeeded`, but CLI replica lookup timed out. The
failed retrieval receipt remains immutable. Read-only recovery used the same
execution's hash-marker lines from the independently matched Newsloom RG log
workspace, within the original execution deadline and 512-KiB evidence bound.
No execution was restarted. The recovered receipt and distinct reconciliation
receipt retain the original failure, source/scope transition and state-repair
lineage. Current in-scope authority/runtime/model/database checks passed with
38 metadata reads. This proves only the stated reduced scope, not inherited or
complete effective access.

## Project provisioning and blocked readback

On 2026-10-29 the approved evaluation-only azd apply completed with five
resources added, zero changed and zero destroyed: one child project, two
custom data-only roles and two operator assignments. Backend locking and the
exact reviewed binary were retained. No parent update or migration verification
execution was replayed.

The first attempt stopped before apply because Terraform reordered identical
`relevant_attributes` dependency entries. A bounded comparison confirmed that
only that ordering and the plan timestamp differed. The private apply guard
was corrected to compare those entries without order while preserving their
full contents and multiplicity; changed resources, changed dependency entries
and duplicate additions still fail. The reviewed binary and covered source
remained unchanged. A distinct retry log records the successful apply.

Fresh independent MCP-identity evidence then covered 2,116 stored records.
Readback stopped before completing the overall preservation comparison:
Azure added `associatedProjects` containing exactly the approved child project
and `defaultProject` naming that same project to the retained account.
One exact-account read confirmed that every other compared account property
was unchanged, including the already reconciled CostControls marker.
The checker reported `evaluation_reconciliation_unreviewed_feature`, although
the feature list itself did not change.

The user subsequently approved only that exact absent-to-owned-project
bookkeeping transition and its source/evidence-bound correction. Original
failed receipts remain immutable; no general account-property exception or
broader verification was authorized.

### Corrected readback and lifecycle blocker

The distinct corrected readback passed on 2026-10-29, binding the original
source, baseline, reviewed/applied binary, successful apply, failed readback
and exact account preimages without a new baseline or resource reapply.
It independently verified the project identity/native endpoints, exact
operator assignments/custom-role permissions, retained account/model/runtime
configuration, project app configuration and complete MCP-identity fingerprints
for 2,116 records. The readback used 41 metadata reads and zero resource
mutations/model calls. Its claim remains limited to the defined
RG/database/project-app scope, not inherited or complete effective access.

Two native serialization corrections also preserve exact identity/authority:
accept the leaf or exact parent-qualified child-project name, and reuse the
existing permission normalizer for the provider's `not_data_actions: null`
empty-set representation. Foreign parents, extra paths, other null permission
fields and changed/extra permissions still fail.
The 241 focused reconciliation/verifier regressions pass. The final primary
gate passes with 1,461 application tests, 67 skips, 218 evaluator tests and
83 Terraform mock runs, plus strict types, lint, formatting and OpenSpec
14/14. This run did not enable the temporary PostgreSQL integration database;
the earlier PostgreSQL-enabled evidence remains separate.
Verifier source:
`515d65019484ee01ab6f5209be82456704ad639f68a4fa5c52cb596612d5c989`.

The approved one-row metadata probe initially stopped during credential
acquisition, before any publication dispatch. The exact installed SDK then
obtained valid AI/Cognitive Services tokens using the same selected CLI
identity. Only never-dispatched operations were resumed, using the original
approval, journal and remaining deadline rather than a new envelope.

The first catalog-create attempt returned `401 PermissionDenied`. Three
bounded GETs targeted only that exact owned evaluator name; they also returned
`PermissionDenied`, including the service reason
`Principal does not have access to API/Operation.` Token audience, tenant and
operator matched the approved context. The service did not identify a missing
data action. No create was replayed, no evaluation/run create was attempted,
and zero paid judge calls were made.

The private journal retains the attempted catalog stage, unknown remote
version and recovery references. The denied reads cannot prove catalog
absence or successful cleanup. Actual catalog authorization, lifecycle/deletion
and report acceptance remained unchecked at that failure. The separately
approved Foundry User transition below is the only subsequent grant; no other
role/scope expansion, reset of the expired probe deadline or paid judging may
bypass the lifecycle gate.

### Project-scoped Foundry User transition

The user approved one additive Foundry User assignment for the selected human
operator on the existing evaluation project. This role is broader than the
custom evaluation role; neither custom role/assignment nor the account-scoped
chat grant is removed or expanded. No production workload or managed identity
receives it, and there is no account-, RG- or subscription-scoped assignment.

The pinned AzureRM assignment resource unconditionally retrieves its role
definition after reading the assignment. The user explicitly approved only
those exact Foundry User definition GETs during creation/readback and future
refresh, rather than adding AzAPI. This is the sole provider-required
out-of-RG metadata exception, not permission for role inventories, unrelated
definitions or wider preservation checks.

Set the optional role ID in the existing private azd environment only after
approval, using the identity in Microsoft's
[public built-in role reference](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/ai-machine-learning).
The Terraform variable and platform preparer both check its exact fingerprint.
The separate `AGENT_EVALUATION_FOUNDRY_USER_ASSIGNMENT_BASE64` output records
the assignment ID, principal/type, role definition and project scope; it is not
proof that catalog access works.

Use the [role-delta verifier](../services/platform/src/newsloom_platform/evaluation_role.py)
through `newsloom-platform verify-agent-evaluation-role --manifest <private-file>`.
Its strict manifest uses `mode`, `foundation`, `foundation_sha256`, `plan` and
`output`. `mode="readback"` also requires `review` and `apply_receipt`.
All files belong in the existing private evaluation-evidence directory.
The foundation path/digest identify the immutable successful historical
readback, not a recreated baseline. The saved plan must add exactly one
assignment, leave all five retained resources unchanged, and add only the
corresponding output. Review/readback bind current source and binary digests
while retaining the historical foundation source separately.
The user also accepted the disclosed refresh-only `null`-to-`[]` representation
of project `identity_ids`, both custom roles' empty `not_data_actions` and the
matching custom-grant output. The role verifier admits only those exact
state/output differences; all retained resources must remain no-ops and any
other drift still fails.

Run local checks before the evaluation-only azd preview. Apply only that exact
reviewed role plan with state locking; do not repeat application prerequisites,
the completed project apply, state recovery or migration verification.
Independently read back the exact assignment and match its private output.
The completed apply receipt records `completed_utc`, `azd_exit_code`,
`source_sha256`, `plan_sha256` and `review_sha256`.

Then record a fresh authorization-only envelope: at most four GETs against the
original exact-owned evaluator name, 30-second request timeouts and one
ten-minute deadline, including explicit propagation-wait reads. No hidden
context reads, retries, wider discovery, artifact mutations or model calls are
permitted. Preserve the expired original lifecycle approval/journal and unknown
catalog version. Even successful authorization does not establish deletion
or lifecycle acceptance; exact-owned recovery or a fresh lifecycle probe needs
separate approval before judging/publication.

#### Verified assignment and observed catalog result

On 2026-10-29, local validation passed 237 focused platform tests, strict types,
lint and the evaluation layer's 14 mocked Terraform runs. The successful azd
provision also passed its primary-check hook; temporary PostgreSQL integration
was not enabled. The exact reviewed role-only binary was applied with locking:
one addition, zero changes and zero destroys. The first attempt failed in the
local preprovision hook because the private plan guard rejected a formatting
check, before any apply intent or resource mutation. Its log was preserved;
the corrected guard permitted check-only formatting and the existing mock tests
without changing the reviewed plan.

Independent readback at `2026-10-29T18:30:17Z` used one exact-assignment GET and
matched the selected operator, principal type `User`, approved built-in role,
project scope and private output, with no unexpected conditions. Both custom
roles/assignments remained resource no-ops; only the previously disclosed
empty-set state/output representations accompanied the addition. The private
review, apply and readback receipts bind evaluator source
`befb73c9c6cc84652dd9d4b7d6a398fe8e189ecd7edb1cdc7218ce7e7bc7ef3b`
to the immutable historical foundation evidence. This verifies the exact role
transition, not a rerun of database or wider preservation checks.

The fresh authorization-only test made three exact-owned GETs between
`2026-10-29T18:30:54Z` and `2026-10-29T18:32:26Z`, within its ten-minute,
four-request ceiling. The first two returned `401 PermissionDenied`; the third
returned `404 UserError`, at which point the test stopped. No complete `200`
listing was observed, so the recorded outcome remains blocked rather than
successful catalog authorization or proof of the original evaluator's absence.
There were zero artifact mutations, uploads or model calls. The original
expired lifecycle approval, pending catalog-create intent and unknown remote
version remain unchanged. Tasks 6.2a and 6.2b record the completed assignment
and diagnostic test only; lifecycle/deletion, paid judging and report acceptance
remain pending. Further exact-owned recovery/lifecycle execution needs a fresh,
explicitly approved envelope, not a replay of the original probe.

#### Actual publication retry

The user explicitly instructed trying the upload again on 2026-10-29. A fresh
metadata-only lifecycle journal linked the original expired probe and verified
Foundry User assignment without modifying or replaying either. It authorized
one disposable evaluator, evaluation definition and constant-score run, followed
by exact-owned cleanup, within a new recorded ten-minute deadline. It did not
authorize another role, infrastructure change, production data or a larger paid
budget.

An isolated helper launch failed before any journal or request. The subsequent
SDK credential acquisition failed before publication dispatch; its journal
confirmed zero mutations, reads and remote references. A focused runtime check
verified that the same CLI identity obtained both required audiences with an
explicit 30-second process timeout. Only those never-dispatched operations were
resumed inside the same fresh approval/deadline, preserving the failed state and
a separate recovery receipt.

At `2026-10-29T18:53:23Z`, the native Projects SDK's actual evaluator-registration
POST returned `401 PermissionDenied`, despite the independently verified
project-scoped Foundry User assignment. The diagnostic APIM request reference
is retained only in the private failure receipt. The new private journal retains one
catalog-create intent, pending outcome and unknown remote version. No create
was replayed, no evaluation/run create followed, and no actual two-case scores
were generated or uploaded. The original uncertain probe remains a separate
retained recovery target; neither absence nor cleanup is claimed for either.
The paid envelope remains wholly unused. Lifecycle task 6.3 and subsequent
paid/report acceptance remain unchecked.

#### Verified native Python replay reference

The suggested
[agentgateway reference](https://github.com/ikhemissi/foundry-agent-with-agentgateway-gateway/tree/49bc29052039cd1a93c5780e89b7157237d3488f)
was initially assessed only from its repository. Its
[README](https://github.com/ikhemissi/foundry-agent-with-agentgateway-gateway/blob/49bc29052039cd1a93c5780e89b7157237d3488f/README.md#L906-L913)
and local runner describe protected JSONL results without automatic upload.
That is not proof that its live Foundry project lacks a separate publication
workflow; the initial broader conclusion was incorrect.

The user supplied exact live evaluation-list and custom-rubric links and could
not sign in through the integrated browser. Existing Azure CLI authentication
successfully read those artifacts instead, without browser credentials or
changing the selected environment. This was an explicit, reference-only scope
addition for the supplied project, not an expansion of Newsloom preservation
verification or permission to inspect other resources.

Four GETs, all successful, read the exact rubric version, one complete evaluation
list page, one named native-Python replay evaluation's run list, and its complete
output page. The live project contains seven evaluation definitions, including
recorded-score replay definitions with `testing_criteria.type="python"` and
metadata `grader_protocol="native-python"`. Their inline criterion fields are
`type`, `name`, `source` and `pass_threshold` plus a returned identifier; this
path does not reference a registered catalog evaluator. The separately linked
custom evaluator exists at version 1 with definition type `rubric`.

The inspected native-Python replay run completed with 16 output rows, seven
metric names, 15 passed cases, one failed case and zero execution errors.
Both returned pages were complete. This verifies a real reference score-replay
publication, not just a local file or an empty definition. It does not establish
score parity or acceptance for Newsloom. No reference artifact was modified,
no role or wider inventory was read, and no model call occurred during research.
Private receipts retain the exact references and response fingerprints without
committing deployment identifiers, rubric text or generated responses.

This supplies a concrete alternative to Newsloom's blocked catalog registration:
native inline Python graders in the evaluation definition. The user explicitly
approved that switch; the publisher and cleanup now distinguish this protocol
from historical catalog journals. Existing unknown catalog intents remain
retained and must not be replayed or silently treated as removed. The existing
paid limits, imported-score provenance and actual API/UI acceptance still apply.

## Locked local setup

Follow the [repository setup](../README.md#local-development) for the application.
The non-packaged [evaluation project](../tools/agent-evaluation/pyproject.toml)
has its own lock and environment and is explicitly excluded from the application
workspace. It is not a seventh runtime package or a production service.

```bash
uv sync --directory tools/agent-evaluation --locked
bash scripts/check-agent-evaluation.sh
```

The [primary check](../scripts/check.sh) invokes both application and evaluation
checks in separate processes/environments. The evaluation check runs locked
lint, format, strict types and offline tests, and rejects application-lock
changes. No Azure credentials or model calls are needed.

For focused evaluation tests:

```bash
uv run --directory tools/agent-evaluation --locked pytest tests/test_compatibility.py tests/test_metric_wire.py tests/test_foundry_wire.py
```

Do not use the root `uv run` for evaluator imports, merge the environments, or
add evaluation dependencies to service manifests. Root `uv build --all-packages`
continues to build the six application packages only.

## Compatibility and privacy evidence

| Surface | Verified version / result |
| --- | --- |
| Python | 3.15.1 |
| DeepEval | 4.3.2, real asynchronous faithfulness measurement with mocked chat |
| Foundry Projects SDK | 2.9.0, native async Entra bridge and mocked evaluation wire calls |
| Evaluation OpenAI SDK | 3.39.0 |
| Evaluation HTTP clients | HTTPX 0.28.1 and HTTPX2 2.16.0 |
| OpenTelemetry API | 1.45.1, now an explicit dependency at its existing locked version |
| Click | Application 8.5.0 unchanged; evaluation-only 8.3.3 |
| Checking tools | Ruff 0.17.1, mypy 2.4.0, pytest 9.1.1, pytest-asyncio 1.4.0 |

DeepEval requires `click>=8,<8.4`. Development-only dependencies in a shared uv
lock still influence production resolution: the rejected initial probe changed
the agent/MCP Click versions. That probe was fully restored before creating the
approved separate project. The six before/after production graphs and unchanged
application-lock check are independent of whether evaluation libraries happen
to be installed in the developer environment.

The [privacy bootstrap](../tools/agent-evaluation/agent_evaluation/policy.py)
sets supported DeepEval telemetry, dotenv, legacy-keyfile, read-only filesystem,
cache, tracing and update-check opt-outs before evaluator initialization.
Provider key defaults are removed from the evaluation process; subsequent key
injection or flag changes fail explicitly. Application-environment execution
and `PYTHONPATH`/`PYTHONHOME` overrides are rejected rather than combining import
paths. The automatic DeepEval pytest plugin is disabled before collection, so
it cannot initialize the library first. Error suppression and missing-parameter
skipping are explicitly disabled.

The actual import probe injects a credential canary and contrary telemetry
flags, denies socket connections/DNS, verifies the real no-op telemetry backend
and checks a fresh home directory for unexpected files. DeepEval emits a fixed
read-only notice on import; the probe explicitly allowlists that notice rather
than ignoring arbitrary output. The tests reject unexpected socket/DNS attempts,
including swallowed attempts.

The [runtime privacy tests](../tools/agent-evaluation/tests/test_runtime_privacy.py)
also force cached DeepEval credential/cache/telemetry/tracing settings, SDK
trace/meter/log providers and logging drift. Runtime admission rejects those
changes rather than trusting environment opt-outs alone. Proxy/no-op provider
shapes are verified against the pinned API; an active SDK provider is not
silently replaced or accepted.

The [fresh-process canaries](../tools/agent-evaluation/tests/test_privacy.py)
exercise actual judging, native SDK publication and cleanup in success,
provider-failure and cancellation scenarios, with contrary environment flags,
debug logging, credential/error canaries and a synthetic explanation canary.
They audit socket/DNS attempts and filesystem writes, including directory-FD
relative operations, then inventory a fresh home/cache directory. Only explicit
private manifests, journals, locks and intentional synthetic result artifacts
are allowed; credentials and provider errors enter none of them. The harness
allows the native SDK's read-only `uname -p` metadata lookup and `/dev/null`,
not arbitrary subprocesses or external result synchronization.

These canaries exposed a failure-path checkpoint race between concurrent metric
siblings. Budget checkpoints are now serialized, and cancellation waits for
an already dispatched local journal write to finish before the final failure
checkpoint. Tests verify the retained unknown-use reservation and halted
admission, with no overlapping temporary-file writes or masked provider failure.
CLI timeouts from the native catalog transport and cancellation produce fixed,
content-free failure categories.

### Actual-library wire contract

The [metric tests](../tools/agent-evaluation/tests/test_metric_wire.py) run the
real public asynchronous/schema adapter and native OpenAI chat client against
an HTTPX2 mock transport. Each ordinary nonempty faithfulness measurement makes
four structured requests: truths, claims, verdicts and reason. Truth and claim
extraction can run concurrently; the shared admission controller serializes
dispatch and parsing, so a failed sibling halts queued requests before dispatch.
Scripted supported and unsupported answers
produce scores `1.0` and `0.0` respectively, preserving their synthetic reasons.
Those scores demonstrate library behavior, not judge calibration or agent
quality. Invalid schema responses fail explicitly.

The [Foundry wire tests](../tools/agent-evaluation/tests/test_foundry_wire.py)
exercise `AIProjectClient.get_openai_client()` with the real SDK's native inline
Python criterion (`type`, `name`, `source`, `pass_threshold`), without a catalog
or model reference. The observed paths are the project's `/openai/v1/evals`,
`/evals/{eval}/runs` and `/evals/{eval}/runs/{run}/output_items`. Inline
precomputed input uses `type=jsonl` with a `file_content` source containing
`{"item": row}` entries. Readback follows both mocked output pages rather than
accepting the first page. Native result items and metrics use execution status
`completed`, including an intentionally failed quality case; the separate
`passed` field carries the diagnostic quality outcome. This matches the saved
live reference. Publication rejects catalog dispatch, definition drift, item
errors and invalid terminal counts before accepting scores. Historical catalog
serialization remains covered only for explicitly separate legacy recovery.
Newsloom's real native sandbox execution remains unverified.

Native project authentication requests `https://ai.azure.com/.default`;
the fixed Azure chat client requests
`https://cognitiveservices.azure.com/.default`. Injected provider keys do not
replace the explicit Entra credential. A native project `401` and chat `429`
each issue exactly one request with SDK retries disabled. All responses are
locally scripted: no real Azure evaluation, paid request or report is produced.

Strict typing has one narrow exemption for DeepEval's untyped
`DeepEvalBaseLLM.__init_subclass__` hook on the adapter class; adapter methods
and request/result interfaces remain typed. DeepEval emits Python 3.15
deprecation warnings for `asyncio.iscoroutinefunction` and a `return` inside
`finally`. They remain visible; this does not establish Python 3.16 support.

## Bounded synthetic scoring

### Judge selection checked in Azure

On 2026-10-28, the account model catalog listed GPT-6 Luna `2026-09-22` for
France Central DataZoneStandard, with regional allocation 0/100. The official
Azure Retail Prices API quoted Luna's standard Data Zone short-context input
and output at USD 0.12/0.60 per million tokens, versus mini's 0.825/4.95.
Luna also has separate long-context and cache-write meters. Both model
documents support Chat Completions, structured outputs and
`reasoning_effort=none`; Luna's 1,050,000-token context would require changing
the current conservative 400,000-token reservation and validating its pricing
tiers before a switch. See the official [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)
and [mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini) specifications.

Those facts do not establish which model is a more accurate faithfulness
judge. The user selected the already-deployed, tested mini model for this
small interoperability pilot; Luna remains a candidate for the separately
calibrated quality baseline. No additional model was deployed or authorized.

The [frozen fixture](../config/agent-evaluation-pilot.json) contains exactly two
precomputed answers to an invented archive-opening question, with case IDs
`p01` and `p02`. Its byte-level digest and case ordering are checked before
execution. Answers are not generated by the deployed research agent; no MCP,
production news or conversation input is accepted.

Offline validation prints only counts and provenance fingerprints:

```bash
uv run --directory tools/agent-evaluation --locked python -m agent_evaluation validate
```

The operator-only `score` command requires an explicitly approved private
manifest, its exact SHA-256, and a new absolute output-directory path. It is
implemented but must not be used for paid work before the execution gate:

```bash
uv run --directory tools/agent-evaluation --locked python -m agent_evaluation score \
  --manifest /absolute/private/approval.json \
  --approved-sha256 "$APPROVED_SHA256" \
  --output /absolute/private/new-pilot-directory
```

The strict manifest binds the evaluator source, fixture, retained environment
and selected operator, a one-day-or-shorter approval validity, and freshly
verified input/output prices. Unknown fields, stale approvals and changed
digests fail explicitly. Approval input must be a nonsymlinked regular file no
larger than 16 KiB. Read-only context checks use the retained `dev` environment
and explicit signed-in-user Azure CLI credential, not an ambient secret.
Before each dispatch, model/version/SKU/capacity are rechecked and active,
unknown or incompletely listed enrichment executions block admission.
Read-only control responses are capped at 1 MiB so complete execution histories
larger than 256 KiB remain inspectable without truncation. Histories beyond that
bound still fail explicitly; pagination and active/unknown execution checks are
unchanged. Judge and publication body limits are separate and unchanged.
The runner also excludes the 70-second windows around half-hour schedule
boundaries; it does not change schedules or increase capacity.

The [shared controller](../tools/agent-evaluation/agent_evaluation/budget.py)
implements the [proposed finite envelope](../openspec/changes/agent-evaluation-foundation/design.md#5-finite-accounting-before-the-first-paid-request).
Each admitted request reserves the full 400,000-token model context as a
conservative input bound, plus 1,024 output tokens. This deliberately exceeds
the [documented model's](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
272,000-token maximum input; it is not an optimistic bytes-to-token estimate.
The [official Azure Retail Prices API](https://prices.azure.com/api/retail/prices)
was checked on 2026-10-28: France Central consumption meters
`5.4 mini Inp Dz` and `5.4 mini Opt Dz` quote USD 0.825 and 4.95 per million
tokens respectively. Batch, cached-input, Global and priority-processing meters
were not substituted. At these rates, each reservation is USD 0.3350688.
This quote is not execution approval or an account-specific billing guarantee;
refresh it before approval. Only reliable, strictly validated
usage releases the unused portion. Single-flight calls settle between attempts,
so eight ordinary scripted calls fit the proposed USD 1 envelope.

Missing usage remains explicitly unknown with its full reservation retained.
Failures, cancellation, model drift, malformed usage and sibling parsing errors
never reset admission history or trigger retries/fallbacks. Usage-derived costs
are explicitly labelled estimates; neither the admission ceiling nor these
receipts are an Azure billing kill switch or an infrastructure-cost cap.
Byte limits cover serialized JSON request and response bodies, not TLS traffic
or HTTP headers. The original 30-minute UTC deadline is retained for subsequent
publication rather than granting publication another inference window.

The [runner](../tools/agent-evaluation/agent_evaluation/runner.py) claims each
approval once in the ignored `.azure/agent-evaluation/` registry. A restarted
scoring invocation cannot reuse it with another output directory. Claims
remain consumed even if subsequent setup fails; recovery must inspect existing
records, not silently restart inference. The new output directory is private
(`0700`), with `0600` exact approval bytes, atomically replaced/fsynced budget
checkpoints, partial scores and final results. Directory entries are fsynced
as well. Interrupted runs do not acquire a success-shaped final result.
Only intentional synthetic result artifacts contain explanations; CLI failures
project fixed categories rather than raw exceptions or argument values.

The [boundary tests](../tools/agent-evaluation/tests/test_budget.py) exercise the
actual 12-attempt and 512-KiB cumulative ceilings, exact/one-over byte and cost
limits, spacing, deadlines and retained cancellation reservations.
[Transport tests](../tools/agent-evaluation/tests/test_bounded_judge.py) cover
native throttling, redirects, snapshot drift, strict usage and queued failures.
The [runner tests](../tools/agent-evaluation/tests/test_runner.py) execute both
real metric measurements and all eight native SDK calls against scripted
responses, preserving the approved bytes, budget and final source/fixture
lineage. This is interoperability evidence, not a real judge-quality result,
calibrated threshold or deployed-agent benchmark.

## Foundry publication and recovery

The [publisher](../tools/agent-evaluation/agent_evaluation/publication.py) accepts
only the existing private scoring journal and its exact approval fingerprint.
It validates both cases, the original source/fixture/metric/configuration/context
lineage, historical approval validity, token/cost accounting and the unchanged
UTC deadline before contacting Foundry. Publication does not invoke the research
agent or repeat DeepEval inference. Unknown judge usage and its estimated
reservation remain present in the published receipt.

After the owning execution approval, use the same locked environment:

```bash
uv run --directory tools/agent-evaluation --locked python -m agent_evaluation publish \
  --directory /absolute/private/existing-pilot-directory \
  --approved-sha256 "$APPROVED_SHA256"
```

The execution manifest now explicitly requires these fixed publication limits,
in addition to the scoring approval fields:

| Field | Value |
| --- | --- |
| `schema_version` | 2 |
| `publication_protocol` | `native-python` |
| `publication_mutation_limit` | 2 |
| `publication_read_limit` | 60 |
| `publication_request_timeout_s` | 30 |
| `publication_poll_spacing_s` | 5 |

The two mutations are one evaluation definition with the reviewed inline Python
grader and one run containing the explicit two-row inline dataset (`file_content`).
There is no separately registered storage-backed dataset, Blob credential or
new storage grant. Inline inputs do not establish that the service needs no
result-storage configuration; storage failures require diagnosis within the
existing project, not an automatic connection or role addition.
Reads include evaluation/run reconciliation, polling
and every output page; their count is durable and never renewed by recovery.
Publication transport bodies are capped at 64 KiB/request and 1 MiB/response.
These publication body caps are separate from the judge's cumulative byte
envelope. All work remains inside the scoring run's original 30-minute deadline,
with no provider retries, redirects, model fallback or additional judge calls.

The [standalone code evaluator](../tools/agent-evaluation/agent_evaluation/grader.py)
returns the provided finite numeric score unchanged and raises for invalid
inputs. Its display/metric label is `imported_deepeval_faithfulness`, not a native
Foundry judge. A `0.5` display threshold is diagnostic only; the deliberately poor
answer can be visibly failed without being an execution failure.
Publication includes no deployment/model reference and makes no inference call.
The existing approved deployment is verified for local DeepEval scoring only.

The wire schema declares `score` as a string. Each strictly validated local
float is encoded using `repr(score)` so Foundry's numeric-column conversions
cannot change its value or precision. The standalone grader parses that text,
checks finiteness through its bounded range check and returns a float. Its
runtime signature has no annotations or imports; a function type comment
preserves local strict typing without requiring sandbox annotation evaluation.
Original result files remain numeric and are never rewritten for this encoding.
Every publication request includes the explicit evaluation-preview header.

Raw output pages are validated before the permissive SDK response models can
coerce values. Case IDs, exact scores (including fractional values), synthetic
explanations and complete row lineage must match the original rows. Missing or
duplicate cases, stale rows, boolean/nonfinite/range errors, definition drift,
sandbox execution errors and incomplete/failed runs cannot become valid zero
scores or a successful publication. Both flat rows and the observed
`datasource_item.item` wrapper are supported. Score strings must exactly match
their canonical float representation before conversion; arbitrary coercion,
rounding and approximate comparisons are not accepted. Null-only service-error
placeholders are ignored, but real service errors and nested item/metric sample
errors still fail explicitly.

Each mutation's intent is fsynced before dispatch. The private
`publication-state.json` retains its attempted stages, unknown outcome, owned
references, consumed reads, schema version and explicit `native-python` protocol,
and latest verification state. Catalog-era approvals and journals fail validation
without being rewritten, migrated or assigned a new deadline. An exclusive local
lock prevents concurrent publishers for one journal.
Reinvoking `publish` defaults to read-only recovery: it reconciles exact owned
evaluation/run metadata and can finish readback for an already submitted
run, but cannot repeat a create request.

If reconciliation establishes that later metadata operations were **never
attempted**, the operator can explicitly add `--continue-unsubmitted`.
Only those still-unused operations may then run, within the original two
mutation slots, remaining reads and deadline. An already attempted operation is
never replayed, even with that flag. Unknown ownership, multiple matching assets
or an exhausted original envelope remains a failure requiring review; neither
continuation nor read-only recovery restarts inference.

On successful API parity, `publication.json` stores the private returned
`report_url`, exact remote references, verification time and unchanged judge
accounting. Open that returned URL to inspect both cases, scores, synthetic
explanations and lineage in the actual Evaluations report. Keep these deployment
references out of committed files and diagnostic output. The CLI emits only a
safe outcome/count summary. `ui_verified` stays `false`: API readback does not
establish UI acceptance, and the actual report must still be independently
verified during the approved live acceptance task.

The [publication tests](../tools/agent-evaluation/tests/test_publication.py)
exercise the actual Projects/OpenAI SDKs and local evaluator code over scripted
HTTP transports. They cover both ambiguous mutation stages, read-only
recovery and explicit unsubmitted continuation, full pagination, persistent
60-read polling exhaustion, deadline preservation, fractional scores, malformed
rows, failed runs, definition drift and retained unknown judge reservations.
They do not establish service-side sandbox behavior, deletion, retention, actual
Foundry visibility or deployed-agent quality.

## Retention and deletion feasibility

The proposed pilot-artifact window is 30 days, with explicit operator-owned
cleanup, not automatic service expiry. Exact-target cleanup and privacy
canaries are implemented and verified locally. The real metadata-only probe stopped at catalog authorization, before
evaluation/run creation. Deletion and observed service lifecycle remain pending in the
[task ledger](../openspec/changes/agent-evaluation-foundation/tasks.md).
Publication recovery alone is not a cleanup mechanism.

The current official contracts establish these candidate operations:

- [Delete an evaluation run](https://learn.microsoft.com/en-us/azure/foundry/reference/rest/evals-delete-eval-run)
  removes that run and its associated results. Its response can contain
  `run_id` and `deleted`; the action is irreversible.
- [Delete an evaluation](https://learn.microsoft.com/en-us/azure/foundry/reference/rest/evals-delete-eval)
  removes the evaluation and associated data, not just its definition.
  The response identifies `eval_id` and whether it was deleted.
- [Delete an evaluator version](https://learn.microsoft.com/en-us/python/api/azure-ai-projects/azure.ai.projects.aio.operations.evaluatorsoperations?view=azure-python)
  returns 204 whether that exact version existed or not; `get_version`
  returns 404 when it is absent.

The pinned native SDK exposes all three asynchronous delete/read operations.
That is local interface/documentation evidence, not proof of actual regional
service behavior. A successful response alone does not establish prior
ownership, observed absence, underlying storage removal or backup erasure.
No automatic TTL, hard-erasure deadline or backup-retention guarantee has been
established. Guessed documentation URLs returning 404 are not evidence that
the service lacks deletion.

The [cleanup command](../tools/agent-evaluation/agent_evaluation/cleanup.py) binds
fresh cleanup approval to the existing registry-owned historical journal and
exact publication-state bytes. It does not require the old scoring source or
expired inference approval to become current again. The inline pilot has no
separately registered dataset or uploaded
Blob to delete. Project/grant retirement belongs to a separately reviewed owning
Terraform operation; it must not replace the retained account or disable its
lasting identity/project-management settings.

### Operator-owned exact-target cleanup

Do not execute against Azure before the owning execution approval. Prepare a
bounded private JSON manifest using the strict `CleanupApproval` schema in the
[implementation](../tools/agent-evaluation/agent_evaluation/cleanup.py):

| Fields | Required meaning |
| --- | --- |
| `schema_version`, `execution_approved` | `2`, and the separately recorded execution decision |
| `publication_protocol` | `native-python`; only explicit historical recovery uses `catalog-v1` |
| `source_sha256`, `context_sha256` | Current cleanup source and selected operator/environment fingerprints |
| `historical_approval_sha256` | Exact original producer approval bytes and registry entry |
| `publication_state_sha256` | Exact historical publication-state file bytes |
| `project_id`, `project_endpoint` | Selected private azd outputs, checked independently on execution |
| `origin` | `imported_deepeval_faithfulness`, or the separately owned `newsloom_metadata_probe` namespace |
| `catalog_version`, `evaluation_id`, `run_id` | Native: null catalog, exact evaluation, run may be null only if unattempted. Legacy: exact catalog version and known attempted-stage references |
| `approved_at`, `expires_at` | Timezone-aware timestamps; approval valid for at most one day |
| `read_limit`, `mutation_limit` | Exactly `60` reads; native `2` deletes, explicit legacy `3`; cumulative across re-entry |
| `request_timeout_s`, `deadline_s` | Exactly `30`, `600`; deadline starts at approval, not restart |

The evaluation name (and catalog name only in legacy mode) is derived from the historical approval fingerprint, not a
wildcard or freely supplied name. Known references must match the historical
record. Unknown create outcomes require exact references resolved through an
approved bounded read-only review before preparing this cleanup manifest;
the command does not guess IDs, repeat creates or substitute a similarly named
asset. Keep all identifiers and the manifest outside committed files.

Start with read-only ownership verification:

```bash
uv run --directory tools/agent-evaluation --locked python -m agent_evaluation cleanup \
  --directory /absolute/private/existing-pilot-directory \
  --manifest /absolute/private/cleanup-approval.json \
  --approved-sha256 "$CLEANUP_APPROVED_SHA256"
```

Only the explicit additional `--delete` flag permits deletion under the same
approval and remaining envelope. No inference is performed. Successful synthetic
API reports are retained for 30 days after their recorded verification time;
a missing accepted receipt cannot silently bypass that window. Failed partial
publications can be cleaned without pretending they were accepted reports.

Before any native deletion, exact GETs verify evaluation/run metadata ownership,
including the `native-python` protocol marker, names and parent references.
Runs must be terminal. A complete run inventory rejects foreign runs; no global
evaluation or catalog inventory is needed. Native deletion proceeds through the
owned run, then its empty evaluation. Explicit legacy recovery additionally
verifies the exact catalog version and inventories dependent evaluations before
deleting that version. A fresh schema-2 `catalog-v1` cleanup approval is required
for an old catalog journal; neither its old approval nor journal is migrated.
No project, model, grant, shared dataset or
foreign artifact is deleted. Use an exclusive operator maintenance window:
the journal lock coordinates this tooling, not unrelated remote writers.

The same private lock excludes concurrent publication and cleanup. Each
ownership check, read count and pre-dispatch delete intent is persisted in
`cleanup-state.json`. A delete is never replayed. A timeout/cancellation retains
its unknown outcome; a later default read-only invocation can verify absence
only when prior ownership and that exact attempted delete were recorded.
If the asset remains present, the result stays unconfirmed. Completing only
never-attempted remaining deletions requires `--delete` again within the same
deadline and limits. Exhaustion, stale approval or foreign state stops for
review, not a reset of the journal or budget.

Native delete acknowledgements are checked before SDK coercion, then followed
by exact GET/404 readback. A bare 204, a coerced `deleted=1`, or a pre-existing
missing asset is not deletion proof. `cleanup.json` records a timestamped
`owned_verified` or `api_absence_verified` receipt with counts and
`backup_erasure_verified=false`. Check the latest state as well: a historical
receipt does not make a subsequent failed revalidation successful. These
[local native-SDK tests](../tools/agent-evaluation/tests/test_cleanup.py) establish
tool behavior over controlled transports, not actual provider deletion or
underlying backup erasure.

### Native Python local gate

On 2026-10-29, after the approved protocol switch, `bash scripts/check.sh`
passed with 240 isolated evaluation tests, 1,494 application tests and 67 skips,
strict types over 27 evaluation and 140 application files, lint/formatting,
14 OpenSpec checks and 85 Terraform mock runs. This run did not enable temporary
PostgreSQL integration. Application manifests/lock and infrastructure were not
changed by this protocol implementation.

The fresh one-row lifecycle helper also passed an offline actual-SDK test with
network denied: two creates, two exact-owned deletes, nine GETs total and one
shared ten-minute deadline, including cleanup. It does not reuse either failed
catalog journal. This is orchestration evidence only; real native lifecycle,
paid scoring and report visibility still require the owning live tasks.
After the live schema-representation correction, the evaluator gate was rerun:
243 tests, strict types, lint and formatting pass; the application lock remains
unchanged. The earlier full primary result is retained, not relabelled as a
post-correction application or cloud run.

### Native Python live attempt

The fresh metadata-only attempt started on 2026-10-29 at 19:48:16 UTC under
one ten-minute deadline. It recorded one evaluation-create intent and received
a successful HTTP response, but the exact definition check raised
`native_probe_definition_drift`. No evaluation ID was accepted, no run was
submitted and zero project GETs, deletes or model calls followed.

The private journal preserves the pending intent, exact owned name and approval.
Under a separately approved six-GET/one-delete recovery envelope, two GETs proved
ownership and diagnosed the mismatch: Foundry preserved the exact submitted
schema under `data_source_config.schema.item`, returning `item_schema={}`.
The source/name/type/threshold matched. The publisher now validates that exact
canonical representation as well as an exact echoed `item_schema`, rejecting
conflicting schemas or added sample data.

Cleanup used two more GETs to reverify the owned evaluation and its empty run
inventory, then attempted its deletion once. The response could not establish
the expected deletion acknowledgement. A fifth GET, for absence verification,
returned HTTP 400 reporting missing
`Microsoft.CognitiveServices/accounts/OpenAI/evals/write` for an upstream
`POST /openai/evals/{eval-id}` operation. This does not establish the necessary
grant scope or justify broadening Foundry User. No deletion was replayed and
absence remains unproven.

The original probe and separate recovery receipts remain retained. Further
authorization investigation or another probe needs a fresh decision, not a reset
of either envelope. At that point lifecycle acceptance and the paid pilot remained blocked;
both older catalog attempts remain unchanged and unknown. No run, paid model
call, role change or infrastructure mutation occurred during recovery.

### Real sample-first scoring and upload attempt

The user explicitly approved uploading the existing two-case synthetic pilot
before deletion testing, superseding only the deletion-first sequencing under
[design 4e](../openspec/changes/agent-evaluation-foundation/design.md#4e-approved-sample-first-sequencing-and-conditional-permission-escalation).
Foundry Project Manager is conditional on successful upload followed by failed
post-upload deletion, not on the historical cleanup failure.

On 2026-10-29, fresh public France Central DataZone consumption prices remained
USD 0.825/4.95 per million input/output tokens. Scoped readiness independently
verified the existing project-scoped Foundry User assignment and unchanged
judge deployment. Complete enrichment-execution history had grown to 287,520
bytes, exceeding the local control reader's former 256-KiB cap. Raising only
that bounded metadata-response cap to 1 MiB preserves complete-history,
pagination, active-job and schedule-window checks. The corrected context,
scoring and publication regressions pass 120 tests, strict types and lint;
the earlier pre-correction full evaluator gate passed 243 tests.

A fresh schema-2 native-Python approval at 20:17:20 UTC bound evaluator source
SHA-256 `9901718728c0f81eef05a3839ce1d95fbd9b6c178b4e1fbf4c8a97a9e552ddbc`,
the original two fixtures and unchanged shared limits. Real DeepEval scoring
completed once:

| Case | Faithfulness |
| --- | --- |
| `p01` | 1.0 |
| `p02` | 0.0 |

Eight judge calls used 3,051 observed input tokens and 404 output tokens, with
complete usage and no unknown reservations. Estimated chat cost was
USD 0.004516875, excluding project/storage/compute and not an Azure billing
guarantee. The intentionally unsupported answer's zero is a quality outcome,
not an execution error. No rescoring or production-content access occurred.

The native publisher created the evaluation definition and attempted its run.
Its run response raised `publication_service_error`. Read-only reconciliation
within the original deadline and read allowance found exactly one owned run
and retained its exact ID without replaying either create. Exact run readback
reported `failed`, zero total/passed/failed output rows, and `UserError` naming
missing `Microsoft.CognitiveServices/accounts/OpenAI/evals/write`. Complete
output-item readback returned an empty page with `has_more=false`.

The evaluation/run exist, but imported-score parity and UI acceptance failed;
submission is not a successful score upload. The private scoring journal retains
both original scores, synthetic explanations, accounting and recovery references.
The error does not establish which additional role or scope would authorize
the upstream operation: project-scoped Foundry User and the custom role already
containing that action were present. No deletion test, Project Manager grant,
new infrastructure, deadline renewal or additional model call followed.
At that point task 6.4 and lifecycle/report acceptance remained unchecked pending
a permission decision consistent with the user's conditional escalation rule.

### Verified Project Manager and failed upload retry

The user subsequently explicitly instructed adding Foundry Project Manager and
retrying the saved evaluations before further workflow hardening. They separately
approved the pinned provider's exact built-in definition GETs. This superseded
the earlier deletion-dependent escalation condition for this one transition,
without authorizing account-, RG- or subscription-scoped access.

The owning Terraform/azd preparation, optional input/output and exact role
transition verifier now support the documented Project Manager role, fingerprint
validated without a committed GUID literal. The one-assignment plan preserves
Foundry User, both custom roles/assignments and production resources. Local
role/preparation/verification checks pass 245 tests, strict types and lint;
all 16 owning Terraform mock runs pass. The ordinary preprovision check also
passed during the successful apply. An initial attempt was stopped before
any apply intent by a private execution-wrapper omission of Terraform's `test`
command; its failed receipt is retained, and correcting only that wrapper
permitted the same reviewed plan to proceed.

Actual apply/readback completed on 2026-10-29: one Project Manager assignment
addition for the same selected human operator at the existing evaluation-project
scope, zero other resource changes or destroys. Independent exact-assignment
readback passed. The source-bound role transition receipt identifies source
SHA-256 `023dd8903e7477d0cbeb5451bf24e31e816310cf6cc1787fa17c5970659066ff`;
no account/project prerequisite apply or migration verification was replayed.

Under the user's renewed upload instruction, a separate publication-only retry
started at 20:55:34 UTC with its own ten-minute deadline, two create slots,
60 reads, 30-second requests and five-second polling. Its approval explicitly
forbids inference and binds the exact original scores, approval, failed state,
producer source and verified role receipt. The expired original scoring
approval/deadline remain immutable; this did not renew judging authority.
An actual-SDK, network-denied test verifies original-score/usage preservation,
distinct retry ownership, the separate publication window and exactly two
creates with no model or evaluator-catalog request.

The retry created a distinct evaluation/run using the original `1.0` and `0.0`
scores, not new judging. Its run response raised `publication_service_error`.
Read-only reconciliation found exactly one retry-owned run and retained its
ID without another create. Exact run readback reported `failed`, zero total,
passed and failed rows, `UserError`, and inner `PermissionDenied` naming
`Microsoft.CognitiveServices/accounts/OpenAI/evals/write`.

Thus Project Manager assignment succeeded, but at this retry it did not resolve
the upload authorization failure. Scope requirements, service-side identity
and propagation behavior are not established by that error. Do not silently
add account-wide access or claim score/API/UI acceptance. Original and retry
journals, the failed report reference and safe diagnostics remain private.
Cumulative paid judging remains eight calls and USD 0.004516875 estimated chat;
the retry added zero judge calls. No deletion test or broader grant followed.

### Explicit preview-header test

The user's supplied working reference explicitly sends
`Foundry-Features: Evaluations=V1Preview`. An offline check of our actual SDK and
transport confirmed that `allow_preview=True` alone does not add this header
to `get_openai_client()` evaluation requests; its token audience is already
`https://ai.azure.com/.default`.

The user approved testing the explicit header with the same retained scores
and no additional role changes or judging. A private experimental transport,
not a production-source change or renewed scoring approval, added the header
on every evaluation request. Four actual-SDK, network-denied regressions verify
header delivery, original-score preservation, read-only recovery without POST
replay, and rejection of nested item/grader `sample.error` results.

The live publication-only test began on 2026-10-29 at 21:23:25 UTC with a fresh
ten-minute deadline, two create slots, 60 reads, 30-second requests and
five-second polling. Exact live assignment reads confirmed both existing
project-scoped User and Project Manager grants before submission. All admitted
SDK/transport requests carried the explicit preview header.

The evaluation was created, but the run response raised
`publication_service_error`. Immediate reconciliation found no matching run;
a subsequent read-only check within the same envelope found exactly one with
the expected name, origin and distinct retry marker. Exact run readback reported
`failed`, `UserError` with inner `PermissionDenied`, and zero evaluated rows.
Seven GETs were consumed in total; neither create was replayed. The final error
did not establish an exact missing action, so do not substitute the action named
by an earlier run.

The explicit header alone therefore did not establish successful upload or
score parity. The original two scores, eight-call usage and estimated chat cost
remain unchanged. No model call, role change, broader scope, deletion test or
UI acceptance occurred. The private journal retains the failed report reference,
safe diagnostics and source-bound approval. The reference's account-scoped
grants remain a relevant difference, not proof of the required role or scope.
Task 6.4 remains unchecked.

### Account-scope role test and immediate retest

The user next explicitly requested both Foundry User and Foundry Project Manager
on the retained account and a retest. This expands the same human operator's
authority across that account, not to the RG, subscription or any new workload
identity. Existing project bindings and custom grants were deliberately retained
during the additive test; no assignment or evaluation was deleted.

Two actual-SDK/network-denied regressions verify the exact account-only role
operations, no mutation replay, unchanged scores and explicit preview header.
On 2026-10-29 at 21:37:07 UTC, a separate source-bound ARM diagnostic approval
allowed at most two PUTs, six exact-assignment GETs, 30-second requests and
ten minutes. Both PUTs and both independent GETs passed, confirming the exact
documented roles, retained account, selected operator, principal type `User`
and absence of unexpected assignment conditions.

This was the explicitly requested diagnostic before further workflow hardening,
not an owning Terraform apply. Exact deterministic assignment IDs, intent and
readback receipts are retained privately. The account grants are persistent but
not yet Terraform-owned: adopt these exact IDs into the owning evaluation layer
before formal delivery acceptance. Do not silently recreate them or imply
that existing project-only Terraform outputs represent the account grants.

A separate publication-only retest started at 21:37:24 UTC with two create
slots, 60 reads, 30-second requests, five-second polling and ten minutes.
It reused the original two scores, explanations, source and eight-call
accounting; every admitted evaluation request carried
`Foundry-Features: Evaluations=V1Preview`.
After read-only reconciliation, the exact new run reported `failed`,
`UserError` with inner `PermissionDenied`, and zero evaluated rows. Six
publication GETs were consumed, without create replay or additional judging.
The exact missing action was not established by this error.

A separate token-binding check confirmed that the evaluation credential's
operator and tenant match the account-grant recipient and that its audience is
`https://ai.azure.com`. No token or raw claims were logged or retained.
The immediate failed test does not rule out RBAC propagation delay or establish
the required service-side identity/permission; account assignment readback alone
is not upload acceptance. The failed report reference and diagnostic receipts
remain private. No further grant, upload, deletion or paid call followed.

### Forced fresh-token retest

The user subsequently requested another saved-score upload with a fresh Entra
token and a definitive outcome. The installed CLI has no public force-refresh
flag, so its selected-user MSAL credential was invoked with
`acquire_token(..., force_refresh=True)` through the CLI's own Python runtime,
preserving normal CLI cache and identity handling. Tokens crossed only a
captured in-memory subprocess pipe; experiment artifacts and logs contain
neither access nor refresh tokens.

Five offline regressions pass for forced refresh, rejection of cached/wrong-user
tokens, exact fresh-token use on SDK requests, and score preservation.
The live refresh returned `token_source=identity_provider`, a different access
token and an advanced issuance time. Operator, tenant and AI audience matched.
Both account-scoped role assignments were independently read back again.
Every admitted publication request used that exact new token and the explicit
evaluation-preview header.

The distinct ten-minute publication-only retry consumed two create slots and
seven GETs, including read-only reconciliation. The exact new run still
reported `failed`, `UserError` with inner `PermissionDenied`, and zero evaluated
rows. Refreshing the token did not establish upload success. No rescoring,
role change, deletion or mutation replay occurred; original eight-call usage
and estimated chat cost remain unchanged. The private journal retains the
token-free refresh proof, run/report reference and failure receipt. Task 6.4
and API/UI acceptance remain unchecked.

### Native account-definition POST comparison

The user approved a definition-only A/B test against the proven successful
reference account and Newsloom. Four offline regressions verify identical
request bytes, one shared verified bearer token, explicit failure/unknown
outcomes and rejection of mutation replay.

On 2026-10-29 at 22:41:20 UTC, both accounts accepted the same minimal custom
schema and native Python grader on the exact downstream route
`POST /openai/evals?api-version=2025-04-01-preview`. Each returned HTTP 201
and a new evaluation ID. Independent GETs of those exact IDs returned HTTP 200
and verified the expected name, ownership metadata, grader and custom type.

| Target | POST | Exact definition GET |
| --- | --- | --- |
| Successful reference account | 201 | 200, verified |
| Newsloom account | 201 | 200, verified |

The test consumed two POSTs and two GETs, with no run creation, dataset content,
model invocation, role change or deletion. Exact new-definition references,
payload fingerprint and approval remain private for later authorized cleanup;
no existing reference asset was modified.

This proves current operator authorization for this minimal native definition
creation on both accounts and establishes that the dated API route supports
the operation. It does not publish scores, prove run/API/UI parity, or identify
the principal used by Foundry's earlier failed internal POST. The earlier 401
was not reproduced by these direct calls. A current project-mediated retry
would distinguish a still-failing handoff from effects of elapsed propagation
time or newly initialized native evaluation state; none is assumed resolved.

### Quick project-mediated retest after native comparison

Latest quick project-mediated retest after the native POST comparison: the user
requested reusing the tested runner and deferring proper cleanup. A distinct
attempt cursor/approval retained the original scores and old journals. A verified
new identity-provider token and the preview header were used on every admitted
request. Two create slots and seven GETs again produced a failed run with
`UserError` / `PermissionDenied` and zero evaluated rows. No judging, role change
or deletion occurred. Direct native creation works, but this full project flow
still fails; the downstream principal and cause remain unidentified. The direct
A/B used a minimal schema/grader while this retry used the full saved-score
payload, so route/context and payload translation are not yet isolated.

### Recorded-score wire-format diagnosis and first API parity

The user approved investigation of data-format differences on 2026-10-30 after
another publisher completed evaluations in the same project. Read-only
comparison verified the same CLI operator, tenant, OAuth client, AI token
audience, project routes, JSON content type and explicit evaluation-preview
header. The retained failed definition matched the submitted schema and grader.
The successful comparison run contained 16 cases, 112 grader results and zero
execution errors.

Four bounded variants still failed with `UserError / UserErrorInner`: canonical
`query`/`response` aliases, a simplified wire schema, their combination, and
nested recorded scores. All retained the original pilot fields and values.
Artifact/native-result inspection then exposed a concrete difference:
floating-point scores appeared as strings in the failed native inputs.
Integer scores remained integers in the successful comparison; its fractional
configuration values also appeared as strings. The observed conversion boundary
is evidence, not proof of the service's internal implementation.

A fifth, separately journaled experiment changed only the JSON representation
of the existing scores from `1.0`/`0.0` to exactly equal integers `1`/`0`,
relative to the already failed minimal-grader baseline. It preserved the
original schema, all input/provenance fields, metric name and `0.5` threshold.
The strict local score model and immutable original results remained floats.
The diagnostic rejects fractional values rather than rounding or truncating
them; this experiment does not establish a general fractional-score solution.
Four focused format tests and three integer-wire tests passed locally.

The new Foundry run completed with exact API readback of `p01 = 1.0` and
`p02 = 0.0`, their original explanations and all lineage fields: one diagnostic
quality pass, one diagnostic quality failure and zero execution errors.
The successful publication consumed two creates and 11 reads, with no judging,
role changes or deletions. Original eight-call scoring usage and its estimated
USD `0.004516875` chat cost remained unchanged. Private authorization, cursor,
`publication.json` and conclusion receipts retain the exact references and
source/result fingerprints; no historical approval or scoring deadline was
rewritten.

The diagnostic publisher also unwraps the observed
`datasource_item.item` response before strict row validation. The main
publisher still expects a flat row and its production integration remains
pending, as do the preview-header integration, fractional-score handling and
separate producer/publisher source binding. Keep the successful scored report
under its manual retention window. Actual UI inspection, disposable deletion,
final preservation and source-bound delivery CI remain required; task 6.4 and
overall foundation acceptance are not complete.

### Fractional publication regression

The user subsequently selected publication-only synthetic regression tests,
not new DeepEval measurements. Nine clearly labelled synthetic cases cover
`0`, `0.1`, `0.125`, `0.375`, `0.49999999999999994`, `0.5`,
`0.5000000000000001`, `0.875` and `1`. The authored query/response placeholders
and score fixtures contain no production content. Their metric origin is
explicitly synthetic, not imported DeepEval or an agent-quality claim.

The initial numeric-column run completed without execution errors but failed
strict value preservation: `0.49999999999999994` returned as
`0.49999999999999906`, and `0.5000000000000001` returned as `0.5`.
Those mismatches remain failures; no tolerance, rounding or changed expected
score was used to accept them.

A separate bounded experiment declared the score column as a string and sent
each original float's canonical round-trip representation. Its native Python
grader explicitly parses that value, rejects boolean/nonfinite/out-of-range
values and returns the numeric score. Verification compares the input's exact
decimal representation, returned numeric score, threshold decision, case set
and all fixture/origin/query/response lineage. It unwraps the observed
`datasource_item.item` response and checks original ownership markers while
allowing service-added run metadata.

Both replays verified all nine cases exactly, including both near-threshold
values. Each run reported four expected threshold passes, five expected
threshold failures, zero execution errors and zero skipped cases.
The successful string-format experiment used three creates and 21 reads;
29 focused local tests passed. No model calls, grants, infrastructure changes
or deletions occurred. The earlier failed numeric-format report and its local
verification-failure history remain retained separately.

Private receipts retain both report links, exact fixture/schema/grader/source
fingerprints and case-level comparisons. This demonstrates fractional-score
publication for the tested fixtures, not a new quality measurement, UI
acceptance or completion of main-publisher integration. The immutable original
DeepEval scoring results and deadline remain unchanged.

### Main-publisher canonical score bridge

The main publisher now integrates the string score wire schema and canonical
encoding, standalone replay parsing, explicit preview header, strict wrapped-row
readback and nested-error checks demonstrated by the diagnostics above.
Null-only service error trees no longer make an otherwise queued run fail.
Local results, exact metric/threshold checks, accounting, ownership,
publication deadlines and durable mutation/recovery limits remain unchanged.

The complete isolated evaluator suite passes 278 tests, plus strict typing,
lint and formatting. The actual-SDK tests verify both wrapped pagination and
legacy flat responses, canonical score strings and the near-threshold values
from the Azure regression, malformed/changed encodings, placeholder errors,
nested grading failures, recovery, cleanup and fresh-process privacy canaries.

On 2026-10-30 the user subsequently approved uploading through the updated main
publisher. A fresh publication-only admission bound the immutable original
producer approval/results/failed-state fingerprints to the current publisher
source, without modifying original scores, approvals, accounting or deadlines.
The operation exercised the main `Publisher.execute` and `validate_item`
unchanged; its private wrapper supplied fresh credentials and the separate
publication admission/deadline, not alternative serialization or validation.
It verified both original cases, scores, explanations and full lineage through
the Azure API, with zero execution errors, two creates, eight reads and no new
model calls, grants, deletions or deployment. The current publisher source
fingerprint is
`60314944471643480c05773da68285b4d60dfa31ad4c0fd46c2655fb453a5f65`;
the private authorization, cursor and `publication.json` retain exact report
references and the distinct historical producer fingerprint.

The focused main-publisher and publication-admission check passed 95 tests
before dispatch. Historical diagnostics retain their original code
fingerprints. Ordinary source-bound execution approval checks remain unchanged:
do not edit an old producer source digest, scores or deadline to make it current.
This publication-only wrapper is not a new general historical-replay CLI.
The subsequent user-confirmed UI inspection below completes task 6.4.
Source-bound delivery CI and the remaining owning acceptance tasks are still
pending; API/UI parity does not complete the entire foundation.

### User-confirmed Foundry UI acceptance

On 2026-10-30 the user opened the exact report returned by the updated main
publisher and reported `Completed`, `Inline data`, 50% overall and 50% for
`imported_deepeval_faithfulness`, a displayed creation time of
`30/10/2026, 12:55:40` and a displayed duration of `26.92s`.
In a separate case-level confirmation, the user verified `p01 = 1.0`,
`p02 = 0.0` and visible original explanations/provenance.

The aggregate is consistent with the two diagnostic scores and one case
meeting the `0.5` threshold; the poor-answer result is not an execution error.
This is user-reported verification in the actual Foundry UI, not an automated
browser check. A separate private UI-confirmation receipt links the exact run
to its API cursor and publication authorization. Original scoring and API
receipts, including their historical `ui_verified: false`, remain unchanged.

Together with exact API parity and the original measured scoring/accounting,
this completes task 6.4 and brings the active checklist to 19/26.
Disposable lifecycle/deletion, final preservation, experimental infrastructure
reconciliation and source-bound delivery publication remain unverified.
The successful pilot report keeps its manual retention protection; recording
UI acceptance does not authorize deleting it or imply Phase 2 quality acceptance.

### Post-upload disposable lifecycle proof

After confirming the pilot's API/UI parity, the user approved automatic
continuation and exact-owned experiment cleanup. The disposable native probe
verified one opaque case with score `0.375`, then verified its own run and
evaluation absent after deletion. The successful fresh proof used two creates,
two deletes and 14 reads under one shared ten-minute deadline, with no model
calls, grants or changes to successful scored reports.

Foundry returned an asynchronous DELETE acknowledgement with `deleted: false`
and an operation `location`, even though the requested run identifier matched.
The cleaner now distinguishes that pending state from a contradictory response:
it polls only the already approved exact resource until `404`, bounded by the
original deadline and cumulative 60-read allowance. It does not follow arbitrary
operation URLs, repeat a DELETE, accept a boolean-like integer or claim absence
from an acknowledgement alone. Optional acknowledgement fields may be absent or
null, but populated identifiers must match. Native cleanup requests include the
explicit evaluation-preview header.

Private cleanup state retains content-free acknowledgement shape/reference
evidence. Earlier failed probes and their original windows remain failures;
separately approved recoveries carried prior attempts/read counts and deleted
only remaining exact-owned empty evaluations. Independent readback verified all
those disposable assets absent without replaying their run deletions. A final
new lifecycle probe supplied the single-window success evidence above rather
than relabelling a recovered failure.

The focused cleanup, publication and actual-SDK lifecycle gate passed 130 tests,
strict types, lint and formatting. Task 6.3 is complete, bringing the active
checklist to 20/26. This proves logical API deletion only, not service backup or
artifact erasure, automatic expiry, removal of historical unknown catalog
versions or completion of wider experiment cleanup. Terraform adoption of
CLI/manual resources and permissions, final preservation and delivery CI remain
pending.

### Terraform reconciliation of CLI/manual experiments

The user requested automatic cleanup and proper Terraform deployment after the
CLI/manual experiments. The owning layer now has an opt-in `data_resources`
configuration and exact-ID import blocks in
[data-resources.tf](../infra/agent-evaluation/data-resources.tf), with private
inputs expanded by the existing azd preparation hook. AzureRM stays at 5.10.0;
AzAPI 2.13.0 is pinned only in this layer. ARM-only storage/role management avoids
account-key reads and unrelated operator blob-data grants.

The first reviewed/applied azd plan imported seven existing objects: the
evaluation storage account, the exact working project connection, the current
project storage grant, both existing account-scoped human-operator built-ins,
and two temporary project-identity telemetry grants. It replaced or deleted
nothing. The connection's provider-state reconciliation preserved its
`ProjectManagedIdentity` authentication, endpoint, default-storage flag,
workspace-identity setting, user-sharing list and exact metadata. Independent
readback matched all seven bindings. The original CLI storage assignment had
already been replaced during manual reconnection; Terraform adopted the current
verified assignment rather than replaying the removed one.

The latest AzAPI embedded schema omits the verified connection auth type.
Only that resource disables embedded validation; fixed configuration and exact
live postconditions enforce the auth type, category, endpoint, default flag,
sharing flag and storage resource ID. Service-reported private endpoint status
is not managed as desired configuration. Storage and connection destruction
guards remain enabled. This follows the narrow AzAPI exception in ADR 8.

No Application Insights connection exists. A separately reviewed follow-up plan
removed only the two unused diagnostic grants from the project identity, not the
Application Insights resource or any production identity. Guarded azd apply and
independent readback verified five retained data-foundation resources and `404`
for both removed assignments. Existing account/operator roles are retained as
explicitly approved, not advertised as minimum necessary permissions.

The full primary local gate passed, including 288 isolated evaluator tests,
1,510 application tests (67 skipped), strict types, lint, formatting and OpenSpec
validation; the evaluation Terraform layer passed 19 mocked runs. Private native
plan/source archives, state backups, guarded apply intents/completions and
readback receipts retain exact references and source fingerprints. The
regenerated plan is compared with the reviewed plan before applying its exact
binary through azd with state locking. Do not recreate the azd environment,
initialize empty remote state or infer wider preservation from these imports.

The data inputs initialize to disabled/empty local defaults. Retained deployments
use `AGENT_EVALUATION_DATA_RESOURCES_ENABLED` and the explicit import flag,
the exact storage/connection/grant names, role IDs and diagnostic-retention
setting in their ignored azd environment. No tenant, subscription or principal
identifiers belong in committed variable files. Failed experiment cleanup,
final preservation and source-bound delivery CI remain separate gates.

### Experiment cleanup and remaining preservation blockers

The user approved automatic cleanup of the earlier Newsloom experiments.
Immutable private journals supplied an exact allowlist of 16 failed evaluation
attempts, including the numeric-precision regression. Verified scored reports
and the reference project were explicitly excluded. Exact definition/run IDs,
names, ownership metadata, terminal status and child-run inventory were checked
before deletion; successful acknowledgements never substituted for `404`
readback.

The initial cleanup left fifteen allowlisted evaluation/run pairs API-absent. One run DELETE
timed out, and exact-resource GETs continued returning the owned failed run
through its original 15-minute window. No DELETE was repeated. A separately
bounded continuation excluded all previously attempted evaluations and carried
cumulative reads/mutation attempts forward while cleaning untouched targets.
The final numeric-regression deletion's negative acknowledgement remained a
failure in its original receipt; separate read-only reconciliation verified
both its run and definition absent. All four protected evaluation definitions
were independently verified still present.

The user then explicitly authorized one fresh, bounded retry of that exact
stalled run and its parent. A distinct one-use authorization retained the
expired journals and carried their cumulative counters forward. Two new
DELETE attempts and 47 new GETs succeeded without transport errors; the
cumulative attempted-delete count is 33 and the recorded maintenance-read
count is 257. Independent exact-target GETs verified all 16 allowlisted
evaluation/run pairs absent and all four protected definitions present.
No other mutation, reference-project access or model call occurred.

The owned Newsloom native definition-only A/B asset was also deleted after
source/name/metadata/criterion and empty-run checks, then independently verified
absent. No reference-project asset was modified. The historical native probe's
exact project ID returned `404` without replaying its old DELETE. The two
historical catalog-parent checks returned `404` on the installed Projects SDK's
actual `v1` API. Earlier checks using another API version are retained as
non-authoritative, not substituted for those corrected exact-target reads.
These are API observations, not proof of backup/artifact erasure.

Post-adoption preservation metadata matched historical workload, model and
app-registration fingerprints. The read-only application preview reported
32 managed resources, zero changes and no PostgreSQL provider drift.
The broader PostgreSQL boundary fingerprint nevertheless differed; its current
metadata preimage, including rolling backup restore-date metadata, was captured
privately for investigation rather than accepted through a hash override.
The user explicitly authorized one additional READ ONLY verification using the
existing migration identity. A separate one-use authorization and private
evidence directory preserved the original consumed fallback and all historical
receipts. Exactly one execution of the unchanged, digest-pinned migration job
ran the fixed read-only collector through an execution-only override; the job
configuration and identity remained unchanged. Replica lookup timed out after
the execution succeeded. Read-only recovery obtained that same execution's
hash-only evidence from Log Analytics within the original ten-minute envelope;
no second job was started.

All 2,116 accepted baseline record identifiers and metadata fingerprints matched
exactly against 2,139 current records: zero missing, zero changed and 23 additions.
PostgreSQL-enforced READ ONLY/REPEATABLE READ evidence reported zero writes and
zero model calls. This proves record preservation, not PostgreSQL configuration
equivalence. An offline reconstruction changing only the restore timestamp to
the previous day did not reproduce the historical boundary hash; it is not
accepted as the explanation or a baseline override. That failed reconstruction remains preserved separately. The actual original
PostgreSQL backup timestamp was subsequently recovered from a successful
2026-10-22 tool result and its exact server/RG-scoped request. Replacing only
`backup.earliestRestoreDate` in the captured current preimage with that observed
historical value reproduces the accepted historical SHA-256 exactly. Every
other preimage field is unchanged. The source event/request and both
preimages are hash-bound in a new private reconciliation receipt; no old
receipt, baseline or database setting was changed. This proves the boundary
hash difference is solely that rolling service metadata field. Final scoped
readback remains a separate gate.

The subsequent 41-read scoped snapshot verified unchanged workloads, models,
directory registrations, production principals and original grants. Its five
additional grants match the exact Terraform-owned project/account operator
roles and storage assignment. Two checks still block final acceptance:

- The account advertises one additional `fal.ai Inference API` endpoint on its
  existing `cognitiveservices.azure.com` account hostname. Removing only that
  descriptor reconstructs the historical account hash exactly. No endpoint was
  followed, no model was added and no inference/runtime setting was changed.
- The evaluation storage has an additional Event Grid system topic and one
  webhook subscription to the regional `storageav.azure.com` service. A
  storage-scoped read confirms Defender for Storage, on-upload malware scanning
  and sensitive-data discovery enabled, with subscription settings inherited.
  Microsoft's [malware-scanning resource contract](https://learn.microsoft.com/en-us/azure/defender-for-cloud/introduction-malware-scanning#resources-deployed-by-malware-scanning)
  documents the required, automatically created topic. It is not a failed
  evaluation asset: deleting or directly managing it could interrupt scanning.
  No subscription-level settings or identities were queried or changed.

The failed final snapshot is preserved, not reclassified as passed. Accepting
these exact service-metadata/service-managed differences requires an explicit
audited planning decision; no broad endpoint/resource exclusion or baseline
override has been applied.

The final primary local gate passed with 290 evaluator tests and 1,510
application tests; 67 application tests requiring an explicit local PostgreSQL
18/pgvector instance were skipped, not passed. Strict types, lint, formatting,
OpenSpec validation, package builds and Terraform validation/mock tests passed,
including all 19 evaluation-layer Terraform tests. This is local evidence, not
exact-commit CI or completion acceptance.

At this checkpoint the checklist remained 20/26. The subsequent approved
reconciliation below closes preservation; the cleanup checkpoint alone did not
establish delivery CI or complete-delivery acceptance.

## Final audited preservation acceptance

On 2026-10-30 the user approved the exact observed metadata reconciliation and
clarified that policy-managed Defender resources are outside application
ownership, not additional evaluation requirements or experiments to adopt.
The working evaluation storage remains necessary and is retained; no Defender
resource, setting or subscription policy was changed.

The distinct private `final-audited-preservation-v1.json` receipt has SHA-256
`b978e02b17ed8780b882f8b51ad4d4b8181db93b4a8f3d160d425ceace6b1740`.
It binds evaluator/platform/infrastructure source SHA-256
`b262668680dafa5149a1ca9ebfac2543dc011e1e33ca8f6a7eea1d33953ec51d`,
the original admitted baseline, unchanged failed final snapshot, actual account
and database preimages, exact Terraform adoption/removal readbacks, cleanup and
API/user-attested UI/lifecycle evidence. The reconciliation made zero cloud
requests, new job starts, resource mutations or model calls.

Measured component times remain explicit: metadata was observed at
16:05:17 UTC; the separate one-use record proof was verified at 15:24:46 UTC.
This receipt reconciles those observations; it does not pretend to recollect
them, renew an expired authorization or replace the before-baseline.

- Removing only the observed `fal.ai Inference API` descriptor, whose value
  equals the existing account's HTTPS `cognitiveservices.azure.com` root,
  reconstructs the original account fingerprint exactly. No endpoint was
  followed and no general endpoint exception was introduced.
- Substituting only the actual historical `/backup/earliestRestoreDate`,
  bound to the original scoped tool request/result, exactly reconstructs the
  original database-boundary fingerprint. The failed guessed-date reconstruction
  and original hash remain unchanged.
- The observed scanning topic/subscription is classified by its exact owned
  storage source, regional Microsoft scanning destination and inherited
  storage-scoped settings. It is excluded from direct application IaC ownership
  and orphan-experiment cleanup, not silently deleted or imported.
- Original resources, custom roles, projects, workload image/configuration/
  schedule fingerprints, models, production principals and grants match.
  The only authority additions are the five explicitly approved,
  Terraform-owned operator/storage assignments; this is not minimum-RBAC proof.
- All 2,116 original row fingerprints match the independently collected
  2,139-row evidence: zero missing, zero changed, 23 additions. The one authorized
  READ ONLY execution and its existing job configuration/identity remain bound.
- Common executions in all four job histories are unchanged. Each scheduled
  ingestion/enrichment list retains 100 entries, adds 61 scheduled executions
  and ages out 61 older entries preceding the oldest returned execution.
  Acceptance history is unchanged; migration history adds exactly the separately
  authorized successful verification execution. No indefinite history-retention
  or deletion claim follows from these bounded service lists.
- All 16 allowlisted failed evaluation/run pairs are API-absent; four protected
  evaluations remain present. The owned native diagnostic/probe reconciliation
  and corrected `v1` catalog-parent reads remain separate, immutable evidence.

The offline acceptance check passed one positive and six negative cases,
rejecting an unapproved endpoint, extra resource, missing custom roles, altered
original record, foreign scanning destination and extra manual execution.
No owned local helper/client remains running. Tasks 1.2, 6.1 and 6.5 are closed;
the three exact-source publication gates remain pending.

This is only the defined RG/database/project-app preservation claim.
Subscription-wide inventories, inherited/management-group grants, global
built-in definitions outside the explicit provider exceptions, quota/catalog
inventories and unrelated directory/database objects were not rechecked.
API absence is not backup/artifact erasure, and the UI evidence remains a
separate user attestation rather than an automated browser inspection.

## Read-only foundation preflight

The 2026-10-28 read-only baseline verified 19 resources, six workloads and
three retained model deployments, including workload/directory, image/config,
grant and schedule preservation. France Central and the retained
`gpt-5.4-mini` snapshot `2026-03-17`, DataZoneStandard capacity 10, were confirmed.
Regional allocation was 110/1000; allocation is not deployment throughput.

Native inventory found an AIServices account with local auth disabled,
project management disabled, no account identity and zero projects.
An account-scoped inherited-role query found one operator assignment, but its
effective data actions were empty: management authority does not establish
project publication or inference access. An independent count/hash-only probe
through the existing MCP identity observed 2,101 stored rows without writes or
model calls. These are transient baselines, not a promise that scheduled
ingestion leaves the record count fixed.

Refreshed native inventory verifies the registered project API `2026-03-01`,
France Central project availability, all six candidate data-operation names and
the unchanged 110/1000 regional allocation. Neither project creation support nor
operation registration proves that the regional catalog, run and deletion
routes authorize against the selected five-operation project role.

Both final saved native plans pass the source/context-bound verifier:

| Owning layer | Managed resources | Reviewed changes |
| --- | --- | --- |
| Application | 32 | One in-place account identity/project-management update; 31 no-ops |
| Agent evaluation | 5 | One project, two data-only custom roles and two operator assignments |

There are no replacements, new models/capacity, production workload changes or
grants to either new managed identity. The private reviews bind source SHA-256
`2dc861f4cd283b3bbdf3491fd15af296b465d7139d6b84aba1b970c804fa9153`,
each exact binary and its own independent preservation baseline.
Each baseline verification used 82 Azure CLI metadata invocations; each plan
review used two. The latest independent MCP count/hash-only receipt observed
2,104 stored rows at 16:37 UTC with zero writes/model calls. This refreshed
before-baseline does not assert equality with the earlier 2,101-row receipt:
scheduled ingestion remained enabled, original receipts remain retained, and
later acceptance still requires explicit reconciliation of any data drift.

Native preview exposed an unapproved provider upgrade and three serialization
differences; the final pinned plans and regression tests cover their fixes.
Rejected attempts remain private evidence, not successful acceptance.
The evaluation enablement flag was restored to false and the owned local
PostgreSQL helper was stopped and removed. No account setting, grant, model or
stored record was changed by these verification commands.

Task 1.2 remains open for exact catalog/lifecycle authorization and observed
regional deletion/retention feasibility. Those facts require the separately
approved metadata-only service probe; no broader-role fallback is authorized.
The quoted token rates, proposed manual 30-day window and documented delete
interfaces do not prove actual service deletion or backup erasure. Refresh
baselines, plans and prices before execution approval if their evidence is stale.

## Provenance and remaining acceptance

The workspace exclusion and README are agent build inputs even though runtime
dependencies are unchanged. The new evaluator checkout must not be presented as
the source that built the already accepted production agent image. Later
evaluation receipts must bind the tool manifest/lock, source, fixtures and
configuration separately from that accepted image/source.

The two-answer runner, imported-score publication/recovery bridge, exact-target
cleanup and privacy safeguards are verified locally and by the specifically
recorded Azure acceptance above. The
[design](../openspec/changes/agent-evaluation-foundation/design.md) still governs
new execution: completed evidence does not renew inference, publication, cleanup
or migration-job approvals. Preserve the 30-day manual report-retention window
and exact-target ownership checks. Do not upload production news or conversations,
enable content tracing, or use Confident AI credentials. Implementation and
separate measured-status publication need their own exact-SHA CI; synthetic
pilot success is not a frozen or calibrated agent-quality baseline.
