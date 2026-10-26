# Phase 1 acceptance operations

Status: complete and verified, including implementation and separate status CI.
The [owning checklist](../openspec/changes/phase1-acceptance/tasks.md)
is authoritative for verified progress. The dedicated identity, isolated
operator run and independent cleanup are verified in Azure. Actual main-branch
OIDC acceptance now passes with four cases, all eight stage gates and automatic
cleanup; see the
[federated acceptance evidence](../openspec/changes/phase1-acceptance/tasks.md#actual-deadline-corrected-federated-acceptance-2026-10-26).
Both separate negative drills and their independent cleanup checks now pass
their intended gates while retaining failed workflow outcomes. The phase matrix and separate exact-commit implementation/status gates are
verified. Completed changes remain unarchived; Phase 2 has not started.
The conditional query boundary is proven under the dedicated identity.
The approved launcher-only timing correction is published with passing exact-SHA
offline CI; see the
[verified timing evidence](../openspec/changes/phase1-acceptance/tasks.md#verified-shared-deadline-bootstrap-correction-2026-10-26).
All three earlier failed workflows remain failures; late operator readbacks
never turn them into acceptance.

## Verified phase acceptance matrix

This matrix separates newly measured integration evidence from reused studies
whose production images, model versions and frozen business/evaluation inputs
remain unchanged. The four integration items are not a new quality benchmark.

| Gate | Measured result and provenance |
| --- | --- |
| Local correctness and hostile inputs | Current [primary gate](../scripts/check.sh): 636 Python tests passed, one opt-in live-publisher test deliberately skipped, strict types for 95 files, eight Terraform roots and 41 mocked-provider tests. All five wheels/sdists build. Hostile transport/parsing, SQL/concurrency and authentication/contract tests remain local; supplied integration feed documents do not prove public-publisher retrieval. |
| Scanner calibration and validation, reused | [Delivered scanner evidence](../openspec/changes/archive/2026-10-23-contextual-content-screening/tasks.md#acceptance-evidence): threshold selected from 16 calibration cases; 16 separate holdouts with zero candidate errors; eight legacy attacks rejected. The 23 selected review regressions are not unseen holdouts or a population estimate; their rejections fell from 22 to two. Policy/model/calibration binding remains unchanged. |
| Enrichment quality and hostile study, reused | [Delivered enrichment evidence](../openspec/changes/enrichment/tasks.md#acceptance-evidence): 20/20 valid, category-correct and content-valid quality cases; six hostile defences (five safe generations and one confirmed upstream block), zero overrides/errors, 25 vectors and all 26 case records. Frozen prompts/taxonomy/fixtures and deployed model versions remain unchanged. |
| Filtered/unfiltered retrieval, reused | [Real-model retrieval study](../openspec/changes/mcp-server/tasks.md#approved-service-deployment-and-real-retrieval-2026-10-24): ten unfiltered and ten filtered cases, each recall@5 1.00, no errors or filter violations, exact evaluation-schema cleanup. The serving image and frozen evaluation inputs remain unchanged. |
| Separate production-workload authority, reused | [Packaged and native MCP verification](../openspec/changes/mcp-server/tasks.md#warning-free-migrated-client-and-final-acceptance-2026-10-24) includes ten actual SQL denials, two model denials, signed wrong-resource 401 and three signed app-only 403 responses. The combined acceptance identity is not a substitute for these production-role boundaries. |
| Native Entra user access, reused | [Warning-free VS Code/Copilot acceptance](../openspec/changes/mcp-server/tasks.md#warning-free-migrated-client-and-final-acceptance-2026-10-24): actual browser sign-in and all four tools, metadata/semantic filtering and boundary parity. This was not an operator bearer-token probe. Actual MCP identity, serving image and configuration remain unchanged. |
| New federated Azure integration | [Workflow 40320123955](https://github.com/ikhemissi/newsloom/actions/runs/40320123955) passed all four cases/eight stages: two accepted/two rejected; four replay duplicates; two distinct claims/one worker loss; attempt-two natural recovery measured at 300.016 seconds; two news/vector rows, five query checks and exact cleanup. |
| New failure/cancellation recovery | [Failure drill 40322828355](https://github.com/ikhemissi/newsloom/actions/runs/40322828355) and [cancellation drill 40324687356](https://github.com/ikhemissi/newsloom/actions/runs/40324687356) intentionally remain red with original safe categories. Exact failed/stopped main executions and successful same-identity cleanup were independently checked. All three fresh databases are independently absent. |
| New final production safety | [Post-drill readback](../openspec/changes/phase1-acceptance/tasks.md#verified-negative-drills-and-final-production-checks-2026-10-26): 1,968 completed/news, zero structural/vector/completion/duplicate/published-rejection failures, nine retained dead letters and 23 rejected records. Production identities, images, schedules, models and conditional authorization remain unchanged. |
| Persistent delivery | Verified implementation `c9f55dba968496e0545e74f3870f87231dcce10b` has [passing exact-SHA primary CI](https://github.com/ikhemissi/newsloom/actions/runs/40327851772). Separate evidence/status commit `f0d9e8cb37eeb56ecf1bea13c396e2ab8ab02a40` has [passing exact-SHA CI](https://github.com/ikhemissi/newsloom/actions/runs/40328538930). The completion receipt also requires exact-head CI before handoff. |

The three new workflows use launcher revision
`61c8d80d8d1adbcff508b6720123e8eee3c5945b` and reviewed runtime image-input
fingerprint `17d11d7a264222c161e90d3de2fb67a3e32effbbf2b9a9abb587d4cabaca0605`.
Full immutable image references, prepared-run manifests and private operator
receipts remain outside committed evidence. Later documentation commits are
not claims that their HEAD was deployed.
Documentation-only updates, including README status, do not rebuild or redeploy
the reviewed runtime images.

## Frozen integration contract

The [authored corpus](../config/phase1-acceptance.json) contains exactly four
complete items: one benign and one hostile in each RSS/Atom feed. Labels and
content are frozen before real inference. One hostile case targets the processor
directly; the other places the attempted override in untrusted author metadata.
The expected real scanner outcomes are two accepted and two rejected. Model
errors, benign rejection or hostile acceptance fail; they are never relabelled.

Only test document transport is supplied by the harness. Parsing, durable
staging, calibrated screening, enrichment/embeddings and MCP queries reuse the
actual services. This does not measure public-feed network retrieval, model
quality, separate production-role isolation or delegated client sign-in anew.
Those retain their own acceptance evidence.

Each run uses an explicitly prepared `newsloom_phase1_<32-lowercase-hex-run-id>`
database, never production rows or a public tool schema parameter. A typed
manifest binds its owner and fixture/schema/model/image fingerprints.
Normal completion requires every exact stage count, including verified database
absence. Missing, malformed, stale or partial reports are failures.

The two accepted identities must yield exactly two completed/news rows and
valid vectors, without publishing either hostile identity. Replay must find all
four known identities and create none. A stopped worker must be reclaimed on
attempt two only after the normal lease expires.

All logs/reports remain content-free: safe stages/categories, opaque identities,
counts, timings and fingerprints only. No fixture text, generated summary,
query, vector array, personal token or credential is operator evidence.

## Explicit database preparation and rescue

After the reviewed identity/job setup and immutable image are available:

```bash
uv run --locked newsloom-platform prepare-phase1-acceptance
```

This retains the new `PHASE1_RUN_ID` privately before starting the existing
migration job with the explicit preparation command and validated test settings.
It creates only that derived database, verifies the separate principal mapping/
absence of production access, applies versioned acceptance/table setup, and
hands ownership only of that database to the dedicated test identity.
It never calls normal production migration startup for this target.

Preparation can be repeated only while the exact matching manifest has not been
started. A used run is not reset/reseeded. Production migration checksums and
principal grants are not edited. Partial setup removes only the database created
by that invocation; a failed cleanup stays a failure.

Recovery uses the retained exact run, not a guessed name or wildcard:

```bash
uv run --locked newsloom-platform cleanup-phase1-acceptance
```

This is operator-only rescue under the retained migration authority, not a
GitHub permission. Both ordinary test cleanup and rescue verify the manifest,
database owner and schema/fixture/model/image fingerprints before DROP from a
maintenance connection, then independently verify absence. Unexpected ownership
or drift blocks destructive cleanup for explicit investigation.
No force-drop or blanket connection termination is used.

## Opt-in resources and lean private workflow

The repository remains private on a personal GitHub Free plan. Manual dispatch
is the operator approval, not an unavailable required-reviewer environment.
The exact OIDC issuer is `https://token.actions.githubusercontent.com`, audience
`api://AzureADTokenExchange`, subject
`repo:ikhemissi@1769608/newsloom@1429962749:ref:refs/heads/main`.
GitHub's default subject for this repository includes immutable owner and
repository IDs. Name-only subjects, foreign IDs, other refs, forks, environment
subjects and wildcard trusts are not approved. Read-only metadata checks are:

```bash
gh api repos/ikhemissi/newsloom --jq '{owner_id: .owner.id, repository_id: .id}'
gh api repos/ikhemissi/newsloom/actions/oidc/customization/sub
```

The owning Terraform layer validates the exact approved ID-qualified subject.
The first actual dispatch failed before starting a test job because the initial
credential used the obsolete name-only form; its unused database was removed
by explicit operator rescue. The reviewed credential-only correction is now
applied and read back with unchanged issuer/audience and no legacy fallback.
Leave GitHub's default OIDC policy unchanged and prepare a new run rather than
reusing either failed dispatch.

```bash
azd env set PHASE1_ENABLED true
uv run --locked newsloom-platform prepare-phase1-layer
azd provision phase1-acceptance --preview
# Apply only after reviewing the owning additions and narrow grants:
azd provision phase1-acceptance
```

Run preparation explicitly before preview: native azd preview does not run the
preprovision build hook. Missing immutable image inputs correctly fail closed.
The layer's preprovision helper initializes a missing enablement flag to false
and does not build/create resources while disabled. Explicit enablement is
retained in the existing ignored environment. The layer builds its own
immutable image and adds only its dedicated identity/federation, narrow grants
and one Manual job: no schedule, ingress, model capacity or production identity
changes. Its CPU/memory are 0.25 vCPU/0.5 GiB, main execution is capped at
1,200 seconds with no platform retries, and workflow time is capped at 30 minutes.
The normal 300-second processing lease is not reduced to shorten cloud tests.

Review the migration-helper image update separately before using explicit
preparation. Its provider stays pinned to the tested AzureRM 5.10.0 release:
native azd initialization must not upgrade it incidentally during preview/apply.
Source hashing includes platform helpers: a helper change can require fresh
helper/test image digests even when processing code is unchanged. Review those
image previews separately from the conditional grant. Do not update shared
workspace policy/tables or silently include an image refresh in a grant apply.
After successful preparation, the ignored environment retains the
run and fixture/schema/model/image fingerprints. Configure repository variables:

```bash
uv run --locked newsloom-platform configure-phase1-github
```

This adds only missing variables for this repository: `PHASE1_CLIENT_ID`,
`PHASE1_JOB_ID`, `PHASE1_LOG_WORKSPACE_ID`, `PHASE1_LOG_ENVIRONMENT`,
`PHASE1_IMAGE`, `PHASE1_IMAGE_REVISION`,
`PHASE1_FIXTURE_REVISION`, `PHASE1_SCHEMA_REVISION`, `PHASE1_MODEL_REVISION`,
`AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID`. Existing conflicting values stop
before writes and require explicit review; unrelated variables are untouched.
The log workspace query GUID comes from the existing ignored
`LOG_ANALYTICS_WORKSPACE_ID`, not a workflow-dispatch input. The corrected setup
has eleven repository variables. Updated image/revision conflicts must be reviewed,
not overwritten automatically.
These are identifiers/fingerprints, not Azure credentials. No GitHub
environment, client secret, PAT or user bearer token is configured for the job.

Dispatch the **Phase 1 isolated Azure acceptance** workflow on `main`, with
the exact prepared `PHASE1_RUN_ID` and scenario `acceptance`. The controller
checks repository/event/ref, immutable image, attached identity, fingerprint
bindings, exact execution and complete stage evidence. It does not provision
anything. The workflow retains the pinned Container Apps client for job control,
but no longer calls its log-streaming/development-token API. The five existing
job read/start/stop/execution management actions remain assigned only at the
acceptance job; the approved correction removed the unused logstream data grant.

Actual federation signs in successfully, but the original pinned log client first
requests a development-API token through `getAuthToken`. Provider metadata lists
`Microsoft.App/jobs/getauthtoken/action` separately from the approved logstream
data action. This additional management permission is not currently granted;
its description covers logs, exec and port forwarding, so it must not be added
as an assumed log-only permission. The first post-correction workflow failed
with a generic Azure-command category and could not verify its own logs/cleanup.
Independent operator checks verified exact database absence, but acceptance
remains incomplete pending actual corrected-workflow proof. The subsequently
approved conditional query correction is deployed; the historical failure and
its inaccessible automatic evidence remain preserved.

### Conditional log-only query access

The owning acceptance layer manages one **Log Analytics Data Reader** assignment
on the existing workspace, not an unconditional workspace reader. Its mandatory
version-2 condition permits only `ContainerAppConsoleLogs` rows whose
platform-populated `JobName` and `EnvironmentName` exactly match the acceptance
job/environment. Workspace metadata/query actions are read-only; the
`Microsoft.OperationalInsights/workspaces/tables/data/read` grant must never be
assigned without its condition. No custom condition or table selector is
accepted from the caller.

`EnvironmentName` is the generated first label of the existing environment's
`defaultDomain`, not its ARM resource name. Terraform reads that property from
the exact owning environment. The operator helper resolves the same value into
the private `PHASE1_LOG_ENVIRONMENT` variable; the test identity receives no
additional environment-read grant. Workspace and environment bindings are both
retained in private execution state and checked again during cleanup.

The controller uses Entra for `https://api.loganalytics.io`, checks returned
job/environment/replica/container/timestamp metadata before parsing evidence,
and binds the report to its prepared run and fingerprints. Queries have a
bounded execution-time window and permit at most 300 rows/262,144 response
characters; overflow, partial results, foreign metadata and malformed proof
fail closed. The private execution state binds the workspace and start time.

Log ingestion is eventually consistent. The first explicit workflow step, before
checkout, authentication or client setup, records an original UTC start/deadline
pair in `GITHUB_ENV`. Its fixed 28-minute envelope leaves two minutes of the
unchanged 30-minute ceiling for artifacts/post steps. Setup consumes this same
envelope. Private execution state binds both timestamps to the prepared run,
scenario, workflow SHA, GitHub run ID/attempt, target, identity and fingerprints.
Cleanup reuses that original pair; missing, malformed, stale, future, extended
or foreign bindings fail closed rather than starting a fresh envelope.

Main has at most 1,260 seconds from controller entry, including template/start
calls, polling and evidence arrival. There is no separate post-terminal report
cutoff. Cleanup has at most 600 seconds from entry, including exact stop, startup
and evidence arrival. Both are clamped to the shared remainder; main/setup may
leave cleanup less than 600 seconds. Exact-stop verification remains at most
90 seconds, also inside cleanup's remainder. Every Azure command is at most
60 seconds and is clamped to the applicable remainder. Calls and sleeps cannot
continue after a deadline, and a response returned too late cannot pass.
These caps are not additive reservations or delivery guarantees.

Only recognized transport timeouts of read-only status/log queries receive up
to two retries, with bounded five-second waits charged to those same deadlines.
Other CLI failures, malformed/partial/foreign evidence and invalid inputs are
not retried. Start/stop mutations are never automatically replayed after an
uncertain outcome. A possibly accepted start requires operator investigation;
it does not authorize another start or a guessed stop. Exact known executions
can be observed without replaying a previously requested stop.
Fixed timeout/JSON/input/deadline categories expose no raw exception, command,
query, URL, private identifier, stdout/stderr or credential. Original main and
cleanup failures remain separate.

The failed corrected run measured 289-second checkpoint, 271-second report and
218-second cleanup ingestion delays. Its final report arrived after the old
240-second post-terminal window, and startup plus cleanup delivery exceeded the
old cleanup allowance. That workflow remains failed. Its separate generic
cleanup API/input failure is retained without claiming its underlying cause
is proven. Missing/late proof remains failure; a terminal job exit never passes.
This approved timing correction adds no image, resource, grant or workspace policy.

Before deployment, review native previews and explicitly approve the new grant,
streaming-grant removal and any required helper/image refresh. Before acceptance,
read back the exact condition, audit additive/inherited grants, and use the
actual dedicated identity to prove own-job access and no foreign-job/other-table
disclosure even without client query filters. Measure checkpoint/report/cleanup
delivery within the existing budgets. Operator queries are not a substitute.
Unsupported conditions or scope collisions block instead of creating broader
read access. Rollback removes only the reviewed conditional assignment and
leaves acceptance blocked; it never adds development-token/exec permissions.

Validate the isolated corrective launcher snapshot locally before publishing
only the approved bootstrap delta. Verify its exact-SHA offline CI before
dispatch. Preserve all three failed workflows and cleanup evidence, and use fresh
prepared databases for acceptance and each drill. No new grant, corrected
bootstrap CI or live query acceptance is implied by the local implementation.
The [owning evidence](../openspec/changes/phase1-acceptance/tasks.md#approved-conditional-correction-and-verified-bootstrap-2026-10-26)
records the approved apply, actual dedicated-identity no-filter/foreign/table
denials and exact-SHA corrective bootstrap CI separately from the
[failed corrected run](../openspec/changes/phase1-acceptance/tasks.md#corrected-federated-run-blocked-by-evidence-delivery-2026-10-26)
and pending negative drills. The failed run's exact database absence was
independently verified through the retained migration authority.

The trusted-main boundary does not isolate one workflow filename or provide
two-person approval. Restrict repository/main write access and review changes
before dispatch. Do not add push/PR/scheduled cloud triggers. Publishing later
is a separate decision; if adding environment approval later, remove the old
branch-bound credential at cutover so it cannot bypass the new gate.

## Failure, cancellation and evidence

Use a fresh explicitly prepared run for each dispatch; do not reset a consumed
manifest. The only scenarios are `acceptance`, `failure-after-ingestion` and
`cancel-after-claim`. The latter two are negative drills and intentionally leave
the main workflow failed, even when cleanup is verified.

The test harness observes a real committed claim through an internal pipe,
overlaps another worker, terminates only the owned child process, waits for the
unchanged natural lease and requires the same identity on attempt two. Cloud
workers never receive fake inference providers. Local tests use explicit
mocked snapshots/providers only to test control flow, separately from real SQL.

The workflow's bounded `always()` cleanup stops/waits for only its recorded
execution and starts the same job in exact-run cleanup mode. Normal teardown
also closes test processes/connections and checks exact absence. It waits
briefly for target-only sessions to exit, never force-drops or terminates other
connections. Drift, failed cleanup or unavailable logs fail the gate.

A typed scrubbed receipt preserves the original failure, separate cleanup
failure, measured stages and each opaque case's disposition/reason/score/
threshold; stale files/revisions or missing proof cannot
become success-shaped artifacts. The private execution state stays in runner
temporary storage. Only the scrubbed report is uploaded for seven days; job
configuration, identifiers, arguments, raw log payloads and credentials are not.
Authenticated test metrics contain fixed stage/outcome names and numeric
duration only. Export/flush failures remain failures.

If a runner or hard cancellation prevents automatic cleanup, retain the exact
run reference for the explicit operator rescue command above. Phase acceptance
remains blocked until absence is independently verified; rescue never erases
the original failed/cancelled result.

The approved bootstrap exception permits publishing only the locally tested
manual launcher/report contract and its tests so GitHub can register the new
workflow. That bootstrap is not Azure acceptance. Full local, reviewed Azure,
real OIDC run/drill, cleanup and exact-commit CI evidence remain required.

## Metered cost preflight

The 2026-10-25 [Azure Retail Prices API](https://prices.azure.com/api/retail/prices)
readback for France Central gives standard active compute of USD 0.000024 per
vCPU-second and USD 0.000003 per GiB-second. A full 1,200-second execution at
0.25 vCPU/0.5 GiB is approximately **USD 0.009 in job compute** before free grants.
Cleanup/drill executions, registry builds/storage, logs, model tokens and shared
server resource use are additional; this is not a total-spend cap.

The existing normal Data Zone `gpt-5.4-mini` retail meters are USD 0.825 per
million input tokens and USD 4.95 per million output tokens (cached input:
USD 0.0825). The regional large-embedding meter is USD 0.158 per million tokens;
the Microsoft Decision 1 meter is USD 0.042 per million tokens. Priority/batch
rates are not substituted for the deployed standard request path. Actual
subscription terms/taxes and usage determine billing.

No model deployment, SKU, capacity, server tier or always-on app is added.
The test shares the existing quotas; throttling/unavailability fails or defers
within existing budgets, never authorizes higher capacity or fake outcomes.
