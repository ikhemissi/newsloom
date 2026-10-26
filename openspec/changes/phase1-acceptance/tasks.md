# Tasks

All 18 tasks have verified local/operator Azure, actual federated workflow,
negative-drill, quality/native-user provenance and implementation/status CI
evidence. Follow [the design](design.md) and
[acceptance contract](specs/phase1-acceptance/spec.md). This checklist is the
approved scope; the evidence below records actual results rather than inferring
tests or Azure permissions from configuration.
The user approved isolated resources and the narrow workflow bootstrap exception;
the approved lean policy keeps the repository private and uses manual dispatch
with exact main-branch OIDC trust, not required environment reviewers. Every
cloud apply still needs its owning native preview reviewed.

## 1. Confined data and real cross-stage harness

- [x] 1.1 Add the test-only typed configuration, four frozen authored RSS/Atom cases and strict per-stage report contract. Verify exact two-benign/two-hostile labels, complete feed fields, stable opaque identities/fingerprints, case/stage completeness and rejection of production/foreign/ambiguous targets without cloud calls. Document the fixed case expectations and distinguish the supplied document transport from public-feed retrieval and the existing quality studies.
- [x] 1.2 Add explicit operator preparation/recovery helpers and separate versioned acceptance bootstrap for one exact database and dedicated principal, without widening production configuration or replaying hard-coded production database/principal initialization. Test real local PostgreSQL table/vector setup, manifest/ownership checks, replay, protected-target refusal and exact cleanup/absence, including failed setup and wrong-owner cases. Document ownership handoff, no global CREATEDB/CREATEROLE/admin membership and operator-only rescue.
- [x] 1.3 Implement the test-only harness using actual ingestion parser/staging/scanner, enrichment worker/providers/repositories and MCP query implementations. Add focused tests for disposition persistence, four duplicate replay identities, atomic publication, independent stored-field/filter/score parity, hostile exclusion and explicit model/schema failures; mocks stay local and never enter the Azure execution path. Document the exact final queue/quarantine/news counts and inherited model/policy contracts.
- [x] 1.4 Add test-only committed-claim observation, distinct overlapping workers, specific-process termination and natural-lease recovery, plus bounded finally/cancellation cleanup and allowlisted reporting. Verify orchestration, real SQL invariants and rollback locally, with deterministic controller timing tests rather than reduced Azure lease limits. Canary-test subprocess/HTTP/SQL/export failures; prove incomplete reports and cleanup failures cannot pass. Document safe failure/cancel drills and exact recovery commands without production runtime fault flags.

## 2. Owning infrastructure and manual federation

- [x] 2.1 Add the nonroot immutable test image/build hashing and disabled-by-default owning azd/Terraform layer for one dedicated identity/federated credential, one manual test job and only the specified inference/registry/telemetry/job-control grants. Verify harness/fixture/schema/prompt hashing, isolated image startup, finite resources/budgets, no schedule/ingress, exact repository/main subject and exchange audience, rejection of environment/foreign-ref subjects, opt-in defaults, absence of privileged production grants and unchanged production resources with focused helper/mocked-provider tests. Document reviewed enable/disable/rollback and metered costs.
- [x] 2.2 Add the self-contained manual main-only GitHub workflow/controller and report validator, repository-level variable setup, explicit dispatch approval, exact-run inputs/scenario enum, concurrency and cleanup recovery without a GitHub environment dependency. Test wrong-event/ref/subject/target/image, missing settings/report, stale execution, malformed metrics, upstream/timeout failures and cancellation without Azure credentials; pin verified action versions and keep the existing offline CI unchanged. Document private configuration, trusted-main limitations, log API requirements, scrubbed artifact retention and the explicit bootstrap-commit exception; the bootstrap must not depend on uncommitted service/harness code.

- [x] 2.3 Correct only the dedicated credential's subject to the approved immutable owner/repository IDs and exact main ref in the design. Verify actual read-only GitHub ID/default-policy metadata, implement the binding and exact-subject tests rejecting legacy names, foreign IDs, environments and other refs, and update related runbook/operator configuration. Run focused local checks and review the owning native azd preview before applying through retained state; any identity/job/grant/image change outside that credential requires renewed review. Keep issuer/audience/authority unchanged, add no parallel credential or GitHub policy fallback, preserve the failed first dispatch and verified operator cleanup, and use a fresh prepared database for subsequent real OIDC acceptance.

- [x] 2.4 Replace the failed streaming assumption with the design's Entra-authenticated, bounded exact-execution Log Analytics queries, one mandatory conditional Log Analytics Data Reader assignment on the existing workspace and removal of the unused job-logstream data grant. Update private-input/helper/workflow/runbook surfaces consistently. Test exact table/job/environment conditions, fail-closed missing/invalid conditions, no dev-token/exec/wildcard/unconditional-reader fallback, execution/run/report binding, finite post-terminal polling, stale/duplicate/oversized responses and failure-category/privacy preservation. Run focused local/type checks and any required image/package checks. Review owning native previews, including any required helper/image refresh; obtain separate deployment approval before applying only those reviewed changes through retained state. Verify an isolated corrective bootstrap snapshot, publish only the necessary locally tested launcher/input delta under the narrow bootstrap exception, and verify exact-SHA offline CI before new dispatch. Preserve the original bootstrap and both failed workflows; this correction alone does not complete actual identity/processing/drill gates.

- [x] 2.5 Implement the approved design's shared, non-resettable workflow deadline and revised evidence allowances across workflow inputs, private execution state, main/cleanup phases, exact-stop waiting and API calls/sleeps. Preserve the existing workflow/job ceilings and natural lease; bind the original deadline to exact run/workflow/target identity and never reset or extend it. Add fixed privacy-safe timeout/JSON/input categories and bounded retries only for recognized read-only status/query timeouts, preserving original and cleanup failures separately and refusing automatic replay of uncertain start/stop mutations. Test exact boundaries, slow calls, stale/future/foreign/reset deadlines, setup/main budget consumption, exhausted cleanup time, measured delayed checkpoint/report/cleanup cases, retry exhaustion, malformed-evidence refusal and diagnostic canaries. Keep this correction launcher/workflow/tests/direct-documentation only: no grant, resource, image, model, workspace-policy or production change. Verify an isolated corrective bootstrap, publish only the necessary locally tested launcher delta under the existing narrow exception, and verify exact-SHA offline CI before any fresh dispatch. Preserve all three failed workflows and their cleanup evidence; neither this task nor a late operator report completes actual acceptance/drill gates.

## 3. Complete local readiness

- [x] 3.1 Run the focused configuration/SQL/harness/claim/cleanup/privacy/workflow/infrastructure tests, then `bash scripts/check.sh` against explicitly disposable PostgreSQL and `uv build --all-packages`. Verify strict types, provider/dependency locks, production ingestion/enrichment/MCP regressions, package/image-only startup, document links and identifier safety; retain measured outcomes and stop the disposable database. No normal test may call a publisher, Azure or a real model.

## 4. Reviewed Azure and actual federated execution

- [x] 4.1 Verify the private Free-plan setup supports repository variables, manual dispatch and exact main-branch OIDC without environment-review features; refresh narrow job/replica/log API actions, PostgreSQL Entra ownership/maintenance-connection feasibility, existing model availability/retirement/quota, compute/storage/log/model rates and private shared-resource/data/schedule baselines. Review the owning identity/job/grant and migration-helper previews; stop on permission/capacity/scope incompatibility instead of adding broad roles, changing repository visibility, firewall exceptions or new models.
- [x] 4.2 Apply only the reviewed acceptance additions and explicit preparation helper update through existing azd state. Prepare a uniquely named probe/run database through the migration authority; under the actual dedicated identity verify sandbox reads/writes, ownership-based exact cleanup and catalog absence, production connection/role denials, needed inference and narrow job/query access without inherited admin privileges. Verify the mandatory conditional assignment/readback, absence of overlapping broader log reads, permitted own-job records and denial of foreign-job/other-table data even without client filters; development-token permission remains absent. Compare production baselines and keep this task incomplete if required isolation, bounded log delivery or cleanup cannot be proven.
- [x] 4.3 Use the explicitly approved bootstrap exception to commit/push only the locally tested manual workflow/controller/report contract and its tests needed for GitHub registration. Verify offline CI for that exact bootstrap SHA, record the narrow exception and reviewed job/image contract, and leave real workflow/phase acceptance unchecked. Do not publish unrelated unverified implementation or automatically trigger Azure from the bootstrap push.
- [x] 4.4 Prepare a fresh exact run database and explicitly dispatch the latest deadline-corrected trusted main-branch workflow after its exact-SHA bootstrap CI, using real branch-bound OIDC and repository-level settings. Verify all four scanner dispositions, duplicate replay, overlapping distinct claims, actual worker loss and attempt-two natural recovery, two valid news/vector rows, zero hostile publication/unfinished work, independent MCP-query parity, content-free complete evidence and exact database removal. Prove checkpoint/report/cleanup delivery under the conditional identity within the applicable phase and original shared deadlines, including after terminal status, with measured remaining-time and delivery evidence. Retain actual workflow/source/image/config/fixture fingerprints and private operator references; never substitute a successful job exit or operator query for missing stage/cleanup evidence.
- [x] 4.5 Exercise separate prepared-run failure-after-ingestion and controlled cancellation drills. Verify the intended failed/cancelled status, original safe failure category, exact execution stop and bounded same-identity cleanup recovery with independently absent databases and no production changes. Missing cleanup or inaccessible logs must leave acceptance blocked; recovery must not erase the original failure, and no drill may masquerade as the successful integration run.

## 5. Phase evidence and persistent delivery

- [x] 5.1 Assemble the phase acceptance matrix from this real federated integration/cleanup, current local regressions, delivered scanner calibration/holdouts, enrichment quality/hostile study, separate filtered/unfiltered retrieval study, actual production-role denials and warning-free native user evidence. Verify source/model/policy/prompt/taxonomy/fixture provenance and unchanged production identities/schedules/data invariants; rerun the owning study on drift. Document retained dead-letter history and distinguish all reused versus newly measured results.
- [x] 5.2 After local, operator Azure and actual workflow gates pass, commit/push the remaining verified implementation with the required trailer and verify the complete primary CI for its exact SHA. Preserve bootstrap and failed/drill workflow evidence without amending verified commits or claiming a documentation-only HEAD was deployed.
- [x] 5.3 Update the owning acceptance runbook, PRD-1/capability/ADR status and this change's evidence with actual limits/results, tested immutable references and unchanged production behavior. Check local links, safe committed content and exact-head CI for separate evidence/status commits before marking Step 1.6 or Phase 1 complete. Leave any unverified prerequisite/task open and stop before Phase 2 work.

## Workflow follow-up

- Present final phase evidence for review before archival or Phase 2 planning.
- Archive this change and the completed enrichment/MCP changes only when
  explicitly requested through their respective workflows.
- Retain the dedicated manual test resources only as reviewed; no schedule is
  enabled, and every disposable run database must be removed independently.

## Acceptance evidence

### Local implementation progress, 2026-10-25

- Frozen four-case contracts, typed exact-run settings/manifests and strict
  complete-stage reports passed 19 focused contract tests. Invalid/protected
  targets, extra database overrides, stale IDs, malformed counts and incomplete/
  duplicate evidence are rejected. The runbook distinguishes supplied feed
  documents from public retrieval and this smoke from quality evaluations.
- Real disposable PostgreSQL tests verified isolated setup/replay, unchanged
  production migration checksums/data, an actual denied production connection,
  natural database-owner cleanup and absence, wrong-owner/manifest/schema-drift
  refusal and exact cleanup after failed application setup. Local Entra mapping
  functions are stand-ins, not proof of real Azure ownership permissions.
- A combined selection of contracts/lifecycle/operator/harness and existing
  ingestion/enrichment regressions passed **66 tests**. Real parser, queue
  replay, enrichment repository and query SQL were exercised with local-only
  fake inference; failure/cancellation cleanup and bounded child-output canaries
  passed. An explicit fixture guard prohibits cloud-token requests.
- The additive resource schema validated and **four mocked-provider tests**
  passed. Disabled defaults create nothing; manual budgets, exact proposed
  federation, immutable images and no broad grants are checked.
  Ruff and strict mypy passed for 93 source files. The complete primary gate,
  image/package checks, actual Azure and real OIDC workflows remain unverified.
- The repository is private and the user confirmed a personal GitHub Free plan.
  GitHub documents required environment reviewers on Free/Pro/Team only for
  public repositories. At that checkpoint the environment approval gate
  required a revised decision before live federation/configuration; the approved
  resolution is recorded below.
  No repository visibility, environment, Azure resource or grant was changed.
- Implementation remains uncommitted, unrelated user customization migrations
  are preserved, and the owned disposable database was stopped while that
  approval-policy decision was pending.

### Approved lean workflow policy, 2026-10-25

- The user chose to retain the private personal-Free repository and approved
  explicit manual dispatch as the approval gate. The plan now uses exact
  `repo:ikhemissi/newsloom:ref:refs/heads/main` federation and repository-level
  variables instead of a required-reviewer GitHub environment.
- The exact GitHub issuer/exchange audience, no-PR/no-schedule rule, trusted-main
  checks, isolated test authority, preview approvals and narrow bootstrap
  exception are unchanged. This is not workflow-filename isolation, paid branch
  protection or two-person review; repository/main writers remain trusted.
- Proposal, spec, design and pending tasks were reconciled with per-artifact
  user approval. The two completed local tasks remain complete; no new task is
  accepted from this planning revision.
- This revision changes planning artifacts only. Existing uncommitted workflow/
  Terraform code still needs the branch-trust/repository-variable delta carried
  into implementation and tested before any live federation/configuration.
  No repository visibility, Azure grant or GitHub setting was changed.

### Lean implementation and complete local gate, 2026-10-25

- The revised exact main-branch trust is implemented in Terraform and the
  manual workflow/controller; no GitHub environment dependency remains.
  Tests reject wrong events/refs/repos/targets/images/identities, environment
  subjects, malformed or stale reports, boolean counters/versions/timings,
  incomplete case/stage evidence and unverified cleanup.
- The report now retains every opaque case's measured disposition, safe reason,
  numeric score and threshold. A success requires all four exact cases and
  expected dispositions; failed runs retain partial measured cases without
  source text or prompts. Wrong scanner outcomes fail before enrichment.
- Local tests exercised the real parser/storage/replay/enrichment/query SQL with
  explicit local-only fake inference. Deterministic fake snapshots tested
  recovery orchestration while real owned child processes were terminated;
  real SQL lease invariants are separate tests. These are not claimed as
  actual Azure process-loss or model acceptance evidence.
- `bash scripts/check.sh` passed with disposable PostgreSQL 18/pgvector:
  **574 Python tests passed**, one opt-in publisher test skipped, **95 source
  files** passed strict types, all lint/lock/feed/identifier/OpenSpec gates
  passed, **eight Terraform roots** validated and **35 mocked-provider tests**
  passed. All five package wheels/sdists built.
- The final isolated no-dev test image imported all real services and packaged
  fixture/schema assets as UID 65532, displayed its CLI and failed closed on
  missing configuration without network/credentials. The owned database was
  stopped after the final gate.
- Current read-only preflights proved repository-variable API access on the
  private repo, supported exact job/log operations and post-completion log
  retrieval with the tested preview client. Existing model deployments are
  Succeeded and quota/cost snapshots were retained privately, without changing
  capacity. A read-only production snapshot showed 1,895 completed/news,
  72 pending, three retryable failed and four dead-letter rows, with 23 retained
  rejections and zero vector/completion/duplicate/published-rejection integrity
  failures. This is a concurrent snapshot, not a required zero-backlog gate.
- Actual new identity/job/ownership permissions, the reviewed native previews,
  real corpus outcomes and federated workflow/drills remain unchecked.

### Native preview and lifecycle preflight, 2026-10-25

- The first ACR build (`ddu`) failed while retrieving the public Python base
  image because Docker Hub did not return headers within the network timeout.
  One identical retry succeeded; no source, registry credentials or permission
  fallback was used to make the build pass. Both workload/helper images now
  have immutable digests for input revision
  `04a1ea7654a9b491b0949968be7e32984419cd9fe03b5fba955753d91d99e02f`.
- Native `azd provision phase1-acceptance --preview` succeeded with exactly
  **nine additions, zero changes and zero destroys**: one identity, one exact
  branch-bound credential, two custom definitions, four scoped assignments
  and one manual job. Its control actions are restricted to the owning job;
  inference, registry pull and telemetry grants use the existing resources.
- The separate migration-helper preview succeeded with **zero additions,
  one in-place image change and zero destroys**. Native initialization exposed
  an incidental provider upgrade, so this owning helper root now pins the
  already-tested AzureRM 5.10.0. Validation, all three helper mocked tests and
  the refreshed native preview passed at that version.
- The existing account's actual regional model catalog was refreshed:
  embedding version 1 is GenerallyAvailable with inference deprecation
  2028-02-09; GPT mini version 2026-03-17 is GenerallyAvailable with inference
  deprecation 2027-09-21; Decision version 1 remains Preview with inference
  deprecation 2027-02-04. No deployment, SKU or allocated capacity was changed.
- PostgreSQL 18 documents database ownership transfer with the operator's
  CREATEDB and ability to SET ROLE, not a global CREATEDB grant to the new
  owner. Actual Azure handoff, maintenance access and dedicated-identity
  denials/cleanup still require task 4.2 proof.
- Reviewed previews, quota/cost metadata and private baselines are retained.
  No acceptance resources, SQL principal/database or GitHub variables have
  been created. Task 4.1 remains open pending operator review/approval;
  no actual model or federated acceptance is claimed.

### Approved reviewed deployment, 2026-10-25

- The operator explicitly approved the reviewed deployment and bounded live
  verification: nine acceptance additions, the separate in-place helper image
  update, exact disposable databases, minimal workflow bootstrap/CI, repository
  variables, one operator probe, one federated acceptance and two negative drills.
  Task 4.1 is complete. Task 4.2 and later gates still require actual results.
- The helper apply completed through the retained azd state with zero additions,
  one image change and zero destroys. The acceptance apply is in progress.
  No broader authority, production schedule/model changes or repository
  publication is approved; an isolation/cleanup incompatibility blocks delivery.

### Actual isolated operator acceptance, 2026-10-25

- The first acceptance apply created seven resources but Azure rejected
  `Microsoft.App/jobs/logstream/action` in management actions. Refreshed provider
  metadata explicitly classifies it as a data action. The correction moves only
  that same approved permission into `data_actions`; scope is still the single
  acceptance job. Six exact-set mocked tests, validation and native preview
  passed. The remaining two-resource apply succeeded without replacing or
  changing the seven retained resources. All nine approved resources now exist.
- Exact role readback shows five job management actions and one log data action.
  The dedicated identity has exactly four assignments and the exact approved
  branch-bound federated subject. Its actual OIDC job/log use is still pending,
  not inferred from these operator-authorized readbacks.
- Explicit preparation succeeded through the retained migration identity.
  Actual test-identity execution `accept-newsloom-dev-lm9fixv` produced a valid
  success report with all four cases and eight stages. It proved one production
  connection denial and four privileged/production role denials.
- The frozen scanner results were two benign accepts and two hostile rejections,
  with unchanged threshold 0.5478523630419381. RSS/Atom benign scores were
  0.0052201700503869035 and 0.0035936245875180495; hostile scores were
  0.9995694428301198 and 0.9992903292992772. No labels, corpus, policy, prompts,
  deployments or threshold were adjusted after inference.
- Replay measured four duplicates and zero staged rows. Actual overlapping
  workers claimed distinct identities; one owned process was lost. Recovery
  took 300.12 seconds after the concurrency stage and completed the same claim
  on attempt two, producing exactly two news rows with zero unfinished work,
  duplicate publication or published rejections. Five query checks and two
  valid vectors passed.
- Exact owner cleanup verified database absence; a separate migration-authority
  cleanup invocation independently confirmed absence. Safe authenticated
  telemetry export and final report delivery succeeded. Private reports retain
  the exact run and immutable fingerprints; no fixture/generated content is
  evidence.
- A subsequent read-only production snapshot showed 1,965 completed/news, one
  pending, zero processing/failed, nine retained dead letters and the same
  23 retained rejections. All vector/completion/duplicate/published-rejection
  integrity failures remained zero. Normal scheduled processing continued;
  changed backlog counts are not described as static data or erased history.
- This is an operator-started workload run, not GitHub federation acceptance.
  Task 4.2 remains open for actual narrow same-identity job/log proof. The
  isolated six-file bootstrap verification command was denied tool approval
  before execution; it was not retried by another route. No bootstrap commit,
  GitHub variables or federated workflow run has been published/configured.

### Independently verified workflow bootstrap, 2026-10-25

- The approval failure was traced to working-directory validation before any
  confirmation prompt. After the operator created the empty temporary directory,
  separate population and verification commands succeeded with normal approvals.
- An isolated snapshot of the committed base plus only the six bootstrap files
  passed 57 focused tests, strict types for 83 source files, Ruff lint and
  formatting. It contains no pending harness/platform/infrastructure changes.
- The real staged tree exactly matched that tested snapshot before committing.
  Bootstrap `b4993522499fca11d5e8f05b203a9afa612a27bf` includes only the manual
  workflow, standalone controller, shared contract, frozen corpus and two test
  files. Hooks passed; unrelated customization migrations remain uncommitted.
- The complete primary [CI run](https://github.com/ikhemissi/newsloom/actions/runs/40231259821)
  passed for that exact SHA. GitHub registered the manual-only workflow as active;
  the push did not dispatch Azure acceptance. Task 4.3 is complete under the
  explicitly approved narrow bootstrap exception, not normal product acceptance.
- Local source, fixture and schema fingerprints still match the reviewed
  immutable job image. Real OIDC job/log proof, federated stage acceptance and
  negative drills remain pending; no phase-readiness claim follows from bootstrap.

### First actual OIDC dispatch blocked before execution, 2026-10-25

- All nine reviewed repository variables were added with conflict checks and
  verified readback. A fresh exact database was prepared; no consumed run was
  reused. Actual manual [workflow 40231520257](https://github.com/ikhemissi/newsloom/actions/runs/40231520257)
  used the tested bootstrap SHA and failed at Azure login with AADSTS700213.
- GitHub issued an immutable-ID-qualified owner/repository subject, but the
  approved credential trusts the legacy name-only subject. Repository API
  readback confirms the default OIDC policy is in use; no GitHub customization
  caused the mismatch. GitHub's [official announcement](https://github.blog/changelog/2026-04-23-immutable-subject-claims-for-github-actions-oidc-tokens/)
  documents this default for repositories created after 2026-07-15.
  Microsoft's [migration guidance](https://learn.microsoft.com/en-us/entra/workload-id/workload-identities-github-immutable-subjects)
  confirms exact matching of the new subject is required.
- No acceptance job, fixture processing or inference started. The automatic
  cleanup step could not authenticate and correctly reported
  `phase1_cleanup_needs_operator`; its retained receipt has no report and
  `cleanup_verified=false`. This failed dispatch is not acceptance or a drill.
- Explicit operator rescue removed the exact unused prepared database and
  verified absence through `migrate-newsloom-dev-p316cvp`. It does not turn
  the failed workflow or its automatic cleanup into success.
- No credential, trust or permission was changed after the failure. Tasks 4.2,
  4.4 and 4.5 remain open pending an explicit decision to revise the exact
  subject, coherent plan/tests and a reviewed native infrastructure preview.

### Approved immutable-subject correction, 2026-10-25

- The operator approved trusting the exact ID-qualified main subject reported
  by GitHub, without changing issuer/audience, identity, job scope or grants.
  Each existing planning artifact's specific revision was separately confirmed.
- Proposal, spec and design now require immutable owner/repository binding and
  explicitly reject legacy or foreign IDs. The design owns the exact subject
  and verified official sources. GitHub's current default policy is retained;
  no extra credential or parallel legacy trust is permitted.
- Pending corrective task 2.3 covers implementation, negative tests, local gates
  and native preview/apply of only the existing credential. The nine completed
  tasks remain historical measured evidence, not proof of this new correction.
  Real identity/job/log, federated acceptance, negative drills and final
  phase/delivery gates remain open.
- This revision updates planning only. No implementation or live trust change
  has been made by the update workflow, and the failed run remains failed.

### Verified credential-only correction, 2026-10-25

- Task 2.3 is complete. Terraform validation and all nine acceptance mocked
  tests passed, including legacy-name, foreign-owner-ID, foreign-repository-ID,
  environment and other-ref rejection. OpenSpec validation passed all nine
  items; formatting and committed-identifier checks passed.
- Read-only GitHub metadata reconfirmed the approved immutable IDs and unchanged
  default OIDC policy. The native owning azd preview showed exactly zero
  additions, one in-place credential subject change and zero destroys.
  The approved apply reported the same counts through the existing state.
- Live readback proves exactly one credential with the approved immutable
  main subject and unchanged issuer/audience. No legacy credential was retained
  or added. Identity, job, grants and image were unchanged; local source still
  matches the reviewed immutable image input revision.
- A new exact database was successfully prepared through the migration helper
  for subsequent federation verification. The original failed dispatch and
  operator-rescue evidence remain intact. This correction is not itself proof
  of actual OIDC job/log authorization, federated processing or negative drills.

### Federated retry blocked at log access, 2026-10-25

- Actual [workflow 40232658401](https://github.com/ikhemissi/newsloom/actions/runs/40232658401)
  used the same verified bootstrap SHA and a fresh prepared database. OIDC
  login and installation of the pinned log client succeeded. The integration
  and cleanup steps failed with `phase1_azure_command_failed`; the retained
  receipt correctly has no stage report and `cleanup_verified=false`.
- Exact operator readback found main execution `accept-newsloom-dev-j4e3kle`
  stopped and cleanup execution `accept-newsloom-dev-4n1clqu` succeeded.
  Reading only that cleanup execution as operator proved the dedicated workload
  emitted its matching `phase1_cleanup` event with `absent=1`. A separate
  migration-authority cleanup independently verified absence. This does not
  turn the inaccessible workflow evidence into passing automatic cleanup.
- Inspection of the actual pinned Container Apps extension shows its job-log
  command first POSTs to the owning job's `getAuthToken` endpoint. Refreshed
  provider metadata exposes `Microsoft.App/jobs/getauthtoken/action` as a
  separate management action, absent from the approved five management
  actions. The provider describes this as a development-API token for logs,
  exec or port forwarding; it is not the existing logstream data action.
  The launcher suppresses raw CLI errors, so the exact failing subrequest is
  not proven by its generic category alone.
- No token permission, broader role, alternative logging authority or workflow
  change has been added. Tasks 4.2, 4.4 and 4.5 remain blocked on an explicitly
  reviewed log-authorization decision and actual same-identity evidence.
  All failed attempts and cleanup references remain preserved.

### Read-only log-only investigation and approved planning revision, 2026-10-25

- The operator selected investigation without permission changes, then approved
  a planning-only revision and each of the four specific artifact revisions.
  Proposal, spec, design and tasks now describe conditional query-based evidence,
  not development-token access. No permission, workflow/controller, image,
  workspace policy or table was changed by this planning revision.
- Both the actual pinned and inspected upstream CLI use the separate
  development-token endpoint. A fresh operator ARM bearer token received 401
  from the exact known log endpoint/replica. No new execution was started.
  This rules out that tested substitution, not every undocumented possibility.
- An operator query selected only the exact cleanup event and returned metadata,
  not its raw log text. Its resource association is the shared environment,
  so job-resource-context access alone would not expose the record. Actual
  `ContainerAppConsoleLogs` metadata has string `JobName`, `EnvironmentName`,
  `ContainerGroupName` and `_ResourceId` columns; the event's job binding
  matched the acceptance job and its cleanup count was one absent database.
- Microsoft's documented [granular RBAC](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/granular-rbac-log-analytics)
  supports restrictive table and row conditions enforced independently of
  client queries. Actual built-in Log Analytics Data Reader readback confirms
  the two metadata/query actions and single data-read action in the design.
  Without its mandatory condition the data grant would be unrestricted;
  no such assignment was created.
- New task 2.4 is pending. All ten completed historical tasks are preserved;
  progress is 10/17. Actual conditional-role enforcement, inherited-grant
  isolation, delivery timing, corrected bootstrap CI, fresh federated
  acceptance and both negative drills remain unverified. Native preview
  review and separate deployment approval are required before any new grant.

### Conditional query implementation and unapplied previews, 2026-10-25

- Implemented the fixed Entra-authenticated console query, mandatory
  table/job/environment role condition, streaming-data-grant removal,
  private workspace/environment bindings, exact execution metadata validation
  and bounded post-terminal report/cleanup polling. Tests cover malformed,
  partial, foreign, duplicate, stale and oversized evidence, private error
  canaries, configuration conflicts and original failure preservation.
- An actual read-only query caught an incorrect metadata assumption:
  `EnvironmentName` is the first label of the existing environment's
  `defaultDomain`, not its ARM resource name. Read-only Azure metadata proved
  that binding. Terraform now reads it from the exact owning environment;
  the operator helper resolves the same private repository setting, without
  granting environment-read permission to the test identity. The corrected
  controller then read the retained exact cleanup event, verifying one matching
  event with `absent=1`. This used operator authentication, started no execution,
  performed no inference and does not prove dedicated-identity authorization.
- The complete primary gate passed against task-owned loopback-only disposable
  PostgreSQL 18/pgvector: **605 Python tests passed, one deliberate publisher
  skip**, strict mypy for **95 source files**, lint/format/lock/feed/identifier
  checks, all eight Terraform roots and **41 mocked-provider tests**, including
  **12 acceptance tests**. OpenSpec passed 9/9 items and 22 local documentation
  links/anchors passed. The disposable database was stopped and its container
  absence verified.

- All five packages built as wheels and source distributions. Both refreshed
  nonroot images passed isolated startup/import checks without development
  dependencies or cloud networking. Both immutable ACR image builds succeeded
  for source revision
  `17d11d7a264222c161e90d3de2fb67a3e32effbbf2b9a9abb587d4cabaca0605`.
  Previous and prepared image references remain in ignored/private evidence;
  no job image has been deployed by these builds.
- Read-only preflight verified the existing workspace query binding, the
  exact built-in reader permissions, unchanged manual job/environment/image
  and zero current dedicated-principal workspace assignments, including
  inherited/group assignments. This is configuration preflight, not proof of
  server-enforced access under the federated identity.
- Native acceptance preview: **one addition, two in-place updates, zero
  destroys**. It adds the mandatory conditional workspace reader, removes
  the unused logstream data action/updates its role description, and updates
  only the acceptance image and its image-revision configuration binding.
  The separate migration preview has **zero additions, one in-place image
  update, zero destroys**. AzureRM remains 5.10.0. No identity, credential,
  production grant, model, schedule, workspace policy or table change is
  included.
- Read-only GitHub inventory retains the original nine variables. The reviewed
  follow-up needs two explicit image/revision updates and two new private log
  bindings, for eleven variables; no repository setting has been written.
  No preview has been applied, new grant created, corrective bootstrap
  published or new workflow dispatched. Task 2.4 remains unchecked and
  progress remains **10/17**, pending separate deployment approval and its
  remaining verified bootstrap requirements.

### Approved conditional correction and verified bootstrap, 2026-10-26

- The user approved the exact reviewed deployment/private-setting changes,
  requested an overnight pause, then explicitly resumed. Fresh native previews
  matched every approved managed before/after value; source revision, both ACR
  digests, private settings and published main were unchanged. Focused checks
  passed 97 tests and strict mypy for 95 source files.
- Applied through retained azd state: acceptance **one addition, two in-place
  updates, zero destroys**; migration helper **zero additions, one in-place
  update, zero destroys**. Its existing migration-verification hook succeeded.
  Actual readback verified the exact condition/version/scope/principal,
  reviewed image digests, unchanged immutable federation and five management
  actions, and zero job-control data actions. The only inherited/group-inclusive
  workspace assignment is the mandatory conditional reader. No development-token
  permission or broader fallback was added.
- A read-only probe on the existing manual job used the actual dedicated
  managed identity, with no database or inference operations. Its unfiltered
  console query returned **25 own rows and zero foreign rows**; an explicit
  foreign-job/environment query returned zero, and the system-table query
  returned HTTP 200 with zero rows. Operator queries independently found
  **4,503 foreign console rows and 1,226 system-table rows** in the same 24-hour
  window, establishing non-vacuous server-enforced denials. Operator reads
  collect the probe's safe result; the queries themselves used the dedicated
  identity. Federated processing/report/cleanup evidence remains a separate gate.
- Updated only the two explicitly reviewed image/revision repository variables;
  the conflict-checking helper added the two private workspace/environment
  bindings. All eleven variables read back correctly and the other seven
  original values stayed unchanged.
- The isolated published-base plus exactly three launcher/input files passed
  **83 focused tests**, strict mypy for **83 source files**, Ruff lint and
  formatting. Staged bytes matched that tested snapshot. Published corrective
  bootstrap `359a3ef20368c114ab11f7c9795ef57194aa988f`, preserving the original
  bootstrap and both failed workflows. Exact-SHA
  [offline CI 40289734217](https://github.com/ikhemissi/newsloom/actions/runs/40289734217)
  passed. Unrelated implementation and user-customization changes were not
  included. Task 2.4 is complete; progress is **11/17**.
- Prepared a fresh exact run through the verified migration helper and explicitly
  dispatched [workflow 40290745091](https://github.com/ikhemissi/newsloom/actions/runs/40290745091)
  at that CI-verified corrective SHA. Processing, bounded delivery and automatic
  cleanup are not yet claimed. Failure/cancellation drills and final acceptance
  remain open. The owned local PostgreSQL helper was stopped and its container
  absence verified.

### Corrected federated run blocked by evidence delivery, 2026-10-26

- [Workflow 40290745091](https://github.com/ikhemissi/newsloom/actions/runs/40290745091)
  completed with **failure** at the verified corrective bootstrap SHA. OIDC and
  the pinned control-client installation succeeded. The retained workflow
  receipt has `phase1_execution_report_missing`, no report and
  `cleanup_verified=false`; automatic cleanup separately recorded
  `phase1_launcher_input_or_api_error`. The generic cleanup category does not
  establish its underlying exception, and that cause remains unproven.
- Exact platform metadata binds main and cleanup executions to the fresh
  prepared run; both executions succeeded. A later operator-only readback
  validated the complete successful four-case/eight-stage report and every
  expected image/fixture/schema/model fingerprint. This is diagnostic evidence,
  not a replacement for the missing workflow report or passing acceptance.
- Exact ingestion timestamps measured **289 seconds** for the committed-claim
  checkpoint, **271 seconds** for the final report and **218 seconds** for the
  cleanup event. The main report was emitted at 08:19:59 UTC and ingested at
  08:24:30 UTC, after the main step failed at 08:24:09 UTC. The cleanup event was
  emitted at 08:24:42 UTC and ingested at 08:28:20 UTC, beyond the existing
  240-second cleanup allowance measured from 08:24:09 UTC. Across the main
  execution, the maximum observed ingestion delay was 304 seconds; that maximum
  is not the final report's measured delay.
- An exact later query through the same controller validated one matching
  cleanup event with `absent=1`. Separate migration-authority cleanup succeeded
  and independently verified database absence. Neither readback erases the
  original workflow/cleanup failure.
- Production ingestion/enrichment identities, templates, schedules and
  configurations match their retained baselines. The migration identity and
  configuration are unchanged apart from the approved helper image. The
  production MCP image reference is unchanged.
- No further workflow or negative drill was dispatched. No permission,
  execution budget, scanner setting, model or production data was changed to
  bypass this failure. Task 2.4 remains complete at **11/17** overall; tasks
  4.2, 4.4 and 4.5 remain open. Further implementation is paused for an explicit
  planning decision on evidence-delivery allowances and safe transport-error
  diagnostics, preserving the existing job/workflow ceilings unless separately
  approved.
- The exact subsequent production integrity readback passed: **1,966
  completed/news**, zero pending/processing/failed work, zero vector/completion/
  duplicate/published-rejection integrity failures, and the same **9 retained
  dead letters and 23 rejected records**. Scheduled production progress explains
  the one additional completed item; no test rows entered production.

### Approved timing and diagnostic planning revision, 2026-10-26

- The user selected a planning-only timing/diagnostics revision, then
  individually approved the proposal, spec, design and task-list edits. No
  implementation, deployment or new dispatch is authorized by these planning
  edits. The previous approved apply/bootstrap and failed workflow remain
  historical measured evidence.
- The revised design uses one non-resettable 28-minute controller envelope
  inside the unchanged 30-minute workflow, keeping the 1,200-second job ceiling
  and natural lease. Main remains capped at 1,260 seconds including all API/
  start time; cleanup receives at most 600 seconds including exact-stop/start/
  delivery, always clamped to the original remaining envelope. The separate
  short terminal-report cutoff is replaced, not the outer execution ceilings.
- Recognized read-only status/query timeouts may receive at most two retries;
  every command and wait consumes the same remaining budget. Malformed/foreign
  proof and generic nonzero CLI errors are not retried, and uncertain mutation
  requests are never automatically replayed. Fixed safe categories will improve
  future diagnostics without relabelling the historical generic cleanup error.
- Added pending task 2.5 and updated fresh-run task 4.4. All eleven completed
  tasks remain checked; progress is now **11/18**, reflecting added work rather
  than resetting delivered query authorization. Actual acceptance, both drills
  and phase completion remain open. Carry this delta into implementation only
  through a subsequent apply request; do not archive or begin Phase 2.

### Verified shared-deadline bootstrap correction, 2026-10-26

- Following the subsequent implementation approval, implemented task 2.5 only
  across the workflow, standalone launcher, focused tests and owning runbook.
  The first explicit workflow step establishes the fixed UTC 28-minute pair
  before checkout/auth/setup. Private state binds it to the run, scenario,
  workflow SHA, GitHub run ID/attempt, target, dedicated identity and fingerprints.
- Main includes template/start/API/evidence time inside 1,260 seconds from
  entry, with no separate terminal-report cutoff. Cleanup includes state/stop/
  startup/evidence time inside 600 seconds from entry, clamped to the original
  shared remainder. The 90-second exact-stop cap includes status and mutation
  time. Every command and sleep is clamped; request-body preparation cannot
  launch a command after expiry, and late successful responses cannot pass.
- Read-only status/query transport timeouts receive at most two retries and
  charged five-second waits. Other CLI/JSON/evidence failures are not retried.
  Pending start state blocks another mutation after an uncertain outcome;
  persisted exact stop requests are observed without replay. Fixed safe
  categories retain original and cleanup failures separately without raw
  errors or private values.
- Focused launcher/contracts selection passed **114 tests**. The primary
  `bash scripts/check.sh` gate passed **636 tests and one deliberate publisher
  skip**, strict mypy for **95 source files**, Ruff lint/format, isolated
  production-package imports, feed/identifier validation, **9/9 OpenSpec items**,
  all **eight Terraform roots** and **41 mocked Terraform tests**. Owning local
  documentation links/anchors passed. The owned disposable PostgreSQL helper
  was stopped and its container absence verified.
- A standalone snapshot of published base
  `359a3ef20368c114ab11f7c9795ef57194aa988f` plus only the three bootstrap files
  independently passed the same **114 focused tests**, strict mypy for **83
  files**, and Ruff lint/format. Staged files exactly matched that tested
  snapshot. Published only `.github/workflows/phase1-acceptance.yml`,
  `scripts/phase1_workflow.py` and `tests/test_phase1_workflow.py` as
  **`61c8d80d8d1adbcff508b6720123e8eee3c5945b`**, with the required co-author
  trailer and no amendment.
- Exact-SHA offline CI
  [40317540367](https://github.com/ikhemissi/newsloom/actions/runs/40317540367)
  passed. All eleven private repository variables read back unchanged. No
  resource, grant, image, model, workspace policy or production deployment
  changed. Unrelated customization changes and the remaining uncommitted
  acceptance implementation were not included in the bootstrap commit.
- All three failed workflows and their cleanup evidence remain historical
  failures. No fresh acceptance or negative drill was dispatched by this
  correction. Task 2.5 is complete, bringing progress to **12/18**; actual
  federated acceptance, both drills and phase completion remain open. The
  next cloud attempt requires a fresh prepared database, never reuse of a
  consumed run. Do not archive or begin Phase 2.

### Actual deadline-corrected federated acceptance, 2026-10-26

- Following explicit operator approval, read-only preflight verified the
  unchanged deployed source/images, all eleven repository variables,
  production job identities/templates/configuration/schedules, MCP image,
  model versions/capacities and exact conditional log assignment. The CLI
  versus REST model response differed only by omitted optional null fields,
  not model/capacity drift. No resource, grant or image was changed.
- The workspace audit still found exactly one inherited/group-inclusive
  assignment and no broader overlapping reader. The job-control role still
  exposes exactly the five reviewed management actions and zero data actions;
  no development-token/exec permission exists. The previously measured actual
  dedicated-identity no-filter/foreign-job/other-table denials remain valid
  under that unchanged assignment.
- Prepared a fresh exact database through the retained migration authority.
  Explicit main-branch OIDC workflow
  [40320123955](https://github.com/ikhemissi/newsloom/actions/runs/40320123955)
  passed at **`61c8d80d8d1adbcff508b6720123e8eee3c5945b`** after its exact-SHA
  offline CI. Strictly validated the workflow-owned artifact, not an operator
  replacement: four cases, all eight exact stage gates, matching run/scenario
  and fixture/schema/model/image fingerprints, overall success and verified
  automatic cleanup.
- Real results: one production connection denial and four role denials; four
  parsed/scanned items with two accepted and two rejected; four replay
  duplicates and zero staged rows; two distinct overlapping claims and one
  actually lost worker; attempt-two recovery with two completed records and
  zero unfinished work, duplicates or published rejections; five independent
  query checks, two news/vector rows; exact database absence. Natural recovery
  measured **300.016 seconds** without shortening the lease.
- The original UTC start/deadline pair was identical in all main/cleanup step
  environments and exactly **1,680 seconds** apart. Setup consumed **16.944
  seconds**, main's whole workflow step **563 seconds**, and cleanup **320
  seconds**. Cleanup finished with **780.056 seconds** of the original shared
  envelope remaining. Every relevant step passed before its applicable cap.
- Exact-execution diagnostic readback subsequently measured checkpoint/report/
  cleanup ingestion delays of **198.342/183.882/275.740 seconds**. The workflow
  itself collected the required proof successfully, including cleanup beyond
  the former 240-second allowance. Both exact ACA executions succeeded.
  Separate migration-authority cleanup also succeeded and independently
  verified the same database absent.
- Tasks 4.2 and 4.4 are complete, bringing progress to **14/18**. Both negative
  drills, the phase evidence matrix and persistent implementation/status
  delivery remain open. The three earlier failed workflows remain failures;
  this new successful run does not rewrite their outcomes.

### Verified negative drills and final production checks, 2026-10-26

- Prepared two additional, distinct exact databases; neither reused the normal
  acceptance run or any consumed historical run. Both manually dispatched
  workflows used bootstrap **`61c8d80d8d1adbcff508b6720123e8eee3c5945b`**, the
  same reviewed immutable image/configuration and the dedicated identity.
- Failure-after-ingestion workflow
  [40322828355](https://github.com/ikhemissi/newsloom/actions/runs/40322828355)
  remained **failed**, preserving `intentional_failure_after_ingestion`.
  Its workflow-owned receipt retained all four scored cases, the exact
  prepared/isolation/ingestion/cleanup stages, no cleanup failure and verified
  cleanup. Its main ACA execution failed intentionally; the separate cleanup
  execution succeeded. Main/cleanup steps took **148/439 seconds** and cleanup
  finished with **1,065.706 seconds** of the original shared envelope left.
  Report/cleanup ingestion delays were **107.457/406.208 seconds**.
- Cancel-after-claim workflow
  [40324687356](https://github.com/ikhemissi/newsloom/actions/runs/40324687356)
  remained **failed**, preserving `intentional_phase1_cancellation_drill`.
  The controller observed the real committed-claim checkpoint, stopped only
  the recorded execution, and ARM readback independently verified **Stopped**.
  Its separate same-identity cleanup execution succeeded. The receipt correctly
  retains `report=null`, no cleanup failure and verified cleanup; it does not
  invent a complete normal report. Main/cleanup steps took **224/368 seconds**,
  leaving **1,067.983 seconds** in the original shared envelope. Checkpoint/
  cleanup ingestion delays were **161.911/334.790 seconds**.
- Both drills reused exactly one unchanged 1,680-second UTC start/deadline pair
  across main and cleanup. All phase steps completed within their limits;
  the intentionally red status was never converted into normal acceptance.
  Separate migration-authority checks independently emitted one successful
  catalog-absence result for each of the three fresh databases. No test target,
  worker or local disposable PostgreSQL container remains running.
- Final read-only production snapshot: **1,968 completed/news**, zero pending/
  processing/failed work, invalid vectors, completion mismatches, completed
  records without news, URL/GUID duplicates or published rejections.
  The same **nine dead letters and 23 rejected records** remain retained.
  The two extra completed items since the earlier snapshot are ordinary
  scheduled production progress, not fixture writes.
- Final ARM readback verified unchanged production/acceptance identities,
  images, templates, configuration and schedules; unchanged MCP identity/
  image/configuration; unchanged model versions/capacities; the exact
  conditional workspace assignment without broader overlapping readers; and
  all eleven repository variables unchanged. The verified runtime source hash
  still matches **`17d11d7a264222c161e90d3de2fb67a3e32effbbf2b9a9abb587d4cabaca0605`**.
- Assembled the [phase matrix](../../../docs/phase1-acceptance.md#verified-phase-acceptance-matrix).
  Earlier scanner/enrichment/retrieval/native-user evidence is explicitly
  reused, not rerun or replaced by the tiny integration corpus. Business-code
  and frozen evaluation configuration comparison against MCP delivery found
  only the new acceptance fixture/contract; deployed production images,
  actual identities and model versions are unchanged.
- Repeated the full primary gate: **636 tests passed, one deliberate publisher
  skip**, strict types for **95 source files**, all eight Terraform roots and
  **41 mocked-provider tests**, plus lint/format/feed/identifier/OpenSpec and
  isolated-package checks. All five wheels/sdists built; the owned local
  PostgreSQL helper was stopped and absence verified.
- Tasks 4.5 and 5.1 are complete, bringing progress to **16/18**. Persistent
  implementation and final status delivery still require their own exact-SHA
  CI. No archive or Phase 2 work is authorized by these measured results.

### Verified implementation release CI, 2026-10-26

- After all local, operator, actual federated integration and negative-drill
  gates passed, published the remaining verified implementation as
  **`c9f55dba968496e0545e74f3870f87231dcce10b`** with the required Copilot
  co-author trailer. Exact staged bytes matched the locally/cloud-tested tree;
  its runtime source hash still matched the reviewed deployed image input.
- Published only 37 owning files. Unrelated prompt deletions and replacement
  OpenSpec skills were preserved and excluded. No verified commit was amended,
  failed/drill workflow deleted, resource redeployed or image retagged.
- [Exact-SHA primary CI 40327851772](https://github.com/ikhemissi/newsloom/actions/runs/40327851772)
  completed successfully. This is the full implementation gate, not the
  standalone bootstrap's narrower local selection.
- Task 5.2 is complete, bringing progress to **17/18**. The owning README,
  PRD/capability/ADR status and runbook updates have their own final status-CI
  gate before task 5.3 and overall Phase 1 completion may be recorded.
  Enrichment, MCP and acceptance remain unarchived; Phase 2 has not started.

### Phase 1 completion, 2026-10-26

- Separate evidence/status commit
  **`f0d9e8cb37eeb56ecf1bea13c396e2ab8ab02a40`** preserved the deployed runtime
  references, historical failures, reused quality/native-client provenance and
  explicit pending final status gate. Its
  [exact-SHA primary CI 40328538930](https://github.com/ikhemissi/newsloom/actions/runs/40328538930)
  passed before recording Step 1.6 and Phase 1 completion.
- The README, owning PRD/capability status, ADR-11 and acceptance runbook now
  link the measured phase matrix. The status commit's **112 local
  links/anchors**, identifier guard and **9/9 strict OpenSpec items** passed.
  Model-preview retirement remains an operational follow-up, not a hidden
  model replacement or Phase 2 readiness claim.
- No runtime image was rebuilt, retagged or deployed by these documentation
  commits. The three real workflow runs retain launcher revision `61c8d80`,
  reviewed image-input fingerprint `17d11d7a264222c161e90d3de2fb67a3e32effbbf2b9a9abb587d4cabaca0605`
  and their original success/intentional-failure outcomes. README status is an
  image-hash input; later documentation tree hashes are not claims of redeployment.
- All three disposable databases have independent absence evidence; local
  test helpers are stopped. Retained dedicated manual resources, shared azd
  state, production schedules and quarantine/dead-letter history remain intact.
- Final handoff requires this completion receipt's own exact-head CI. No
  verified commit is amended, no change is archived and no Phase 2 work begins.
- The final receipt revalidated **111 local links/anchors**, safe identifiers,
  whitespace and **9/9 strict OpenSpec items**. Task 5.3 is complete and overall
  progress is **18/18**; all tracked Phase 1 acceptance work is complete.
