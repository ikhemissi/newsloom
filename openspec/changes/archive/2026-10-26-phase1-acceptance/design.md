# Design

## Context

See [the proposal](proposal.md) for motivation, approved resource scope and
prerequisites, and the [acceptance contract](specs/phase1-acceptance/spec.md) for
the gates. This design adds an isolated test unit, not a fourth business service.

Observed implementation constraints:

- The [normal CI workflow](../../../../.github/workflows/checks.yml) runs the
  credential-free primary gate against disposable local PostgreSQL. It has no
  OIDC permission, Azure test identity or cloud integration job.
- [Platform configuration](../../../../services/platform/src/newsloom_platform/config.py)
  deliberately fixes the production database to `newsloom`.
  [Migration initialization](../../../../services/platform/src/newsloom_platform/database.py)
  also manages the four production principal mappings, and
  [001_vector.sql](../../../../services/platform/src/newsloom_platform/migrations/001_vector.sql)
  explicitly revokes/grants privileges on `newsloom`. Blindly replaying that
  setup for another database would touch production permissions.
- Ingestion separates protected retrieval, parsing/staging and
  [screening/durable processing](../../../../services/ingestion/src/newsloom_ingestion/job.py).
  Enrichment's [worker](../../../../services/enrichment/src/newsloom_enrichment/job.py)
  and [repository](../../../../services/enrichment/src/newsloom_enrichment/repository.py)
  already expose real finite claims, atomic completion and a 300-second lease.
  The MCP [repository](../../../../services/mcp/src/newsloom_mcp/repository.py)
  accepts a connection and uses fixed public-news projections.
- Existing [grant definitions](../../../../infra/main.tf) distinguish Decision
  provider, chat and embedding API actions. This new test unit needs those
  operations together, but must inherit none of the production identities.
- The old temporary platform probes include a migration-admin job; the new CI
  identity cannot start or override that job or production pipeline executions.
- Real labelled model studies and native user sign-in are already retained in
  their owning changes. A four-item test is not a new quality benchmark or
  proof of separate production-workload privilege boundaries.

Primary references:
[GitHub OIDC on Azure](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect),
[manual workflow dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch),
[job execution logs](https://learn.microsoft.com/en-us/cli/azure/containerapp/job/logs?view=azure-cli-latest),
and [PostgreSQL database cleanup](https://www.postgresql.org/docs/18/sql-dropdatabase.html).
These document capabilities, not evidence that the proposed tenant permissions
or workflow have been exercised.

The first post-correction federated run signed in successfully but could not
read its execution evidence. Both the pinned and inspected upstream CLI
implementations request a job development-API token before streaming. Provider
metadata lists that management action separately from the approved logstream
data action. An operator ARM-bearer probe of the exact stream endpoint returned
401; it is not a verified replacement authentication path.
The exact cleanup record in Log Analytics belongs to the shared environment,
not the job resource. Its structured console table has platform-populated
`JobName`, `EnvironmentName` and `ContainerGroupName` string columns.
These observations motivate the conditional query path below; they do not
prove enforcement under the dedicated identity.

Subsequent approved deployment and actual dedicated-identity queries proved
that conditional boundary without development-token access. The corrected
federated workflow then failed on evidence timing: checkpoint/report/cleanup
ingestion delays were 289/271/218 seconds, and the report arrived after the
240-second terminal allowance. Startup plus cleanup delivery also exceeded
the 240-second recovery allowance. Its separate generic cleanup API/input
error does not identify the underlying exception. Preserve this failed run
and independently verified database absence; neither a successful job exit nor
the complete late operator report is passing workflow evidence.

## Goals / Non-Goals

**Goals:** reproducible cross-stage evidence, no production fixture writes,
one constrained test principal, actual process-loss recovery, finite cost/work,
and cleanup that is necessary for acceptance.

**Non-Goals:** a general test platform, production database override, new
public fixture publisher/MCP endpoint, production runtime fault flags, recurring
cloud CI, replacement quality sets, or database administration from GitHub.

## Decisions

### 1. Use one disposable database rather than test rows in production

Each operator-prepared run gets `newsloom_phase1_` followed by a validated
32-hex run ID. Reject other names, production names, URI/identifier input and
unprepared targets before any write. Quote the generated identifier with the
existing SQL composition helpers; values remain parameters.

Use the existing migration identity for explicit preparation through the retained
migration job. Add separate, versioned acceptance bootstrap steps and their own
ledger/manifest. Install vector in the test database and apply the unchanged
application-table migrations in order. Do not call production principal setup,
replay the hard-coded production database grants, change their checksums, or add
acceptance setup to application startup/default migration execution.

Record the run ID, exact database name, expected test principal, fixture/schema/
model/policy fingerprints and ownership in a manifest. Create the normal
`public.feed_sources`, queue, quarantine and news structures only in that
database. This permits reuse of unmodified SQL/projections, unlike a new schema
selector threaded through every service.

Keep production `RuntimeConfig` and MCP public inputs restricted as they are.
The test-only configuration derives the target from its explicit run ID and
verifies `current_database()` and the manifest on every new connection.
No environment switch on the production jobs or serving endpoint is introduced.

### 2. Isolate authority, including the ability to clean up

Add one dedicated user-assigned identity for this acceptance unit. It is both
the GitHub OIDC principal and the test job's workload identity, but is not any
of the four production principals.

| Authority | Allowed | Explicitly forbidden |
| --- | --- | --- |
| PostgreSQL | Its Entra login; CONNECT and required data access in the exact prepared database; ownership of that database for teardown; maintenance-database connection for absence/cleanup checks | CONNECT to `newsloom`, production roles, `azure_pg_admin`, SUPERUSER/CREATEDB/CREATEROLE, server administration or ownership of other databases |
| Models | The existing Decision-provider, chat-completions and embedding inference actions at the already supported account scope | Keys, model-management/capacity changes and unrelated APIs |
| Registry | Pull the test image from the existing registry | Registry admin credentials, push or build authority |
| Job control | Read/start/stop and exact execution status for the single named acceptance job | Write/delete job definitions, production/migration job execution, app exec or broad resource-management roles |
| Diagnostics | Authenticated publishing to the existing sink; conditional console-table/job/environment log-data reads and read-only metadata at the existing workspace | Shared keys, unrestricted workspace/foreign-job/table data access or development-token/exec permissions |

The operator creates/maps the new principal and hands ownership of only the
prepared database to it. Ordinary database ownership permits dropping that
database from another connection; it does not require global CREATEDB.
The implementation must verify that Azure PostgreSQL supports this exact
handoff and a usable maintenance connection without broader role membership.
If not, stop for a new decision; do not grant admin to make cleanup work.

The identity can administer its disposable database, so its permissions are
not a substitute for production role-isolation evidence. Reuse the separately
verified production workload tests for that matrix. Direct encrypted production
connection and privileged-role attempts under the actual test identity must be
denied for a server authentication/authorization reason, not mere timeout.

For log reads, use the verified built-in **Log Analytics Data Reader** role
with one mandatory conditional assignment at the existing workspace. Its
management actions are only `Microsoft.OperationalInsights/workspaces/read`
and `Microsoft.OperationalInsights/workspaces/query/read`; its data action is
`Microsoft.OperationalInsights/workspaces/tables/data/read`.
The data permission without a condition would expose all workspace log data,
so never create an unconditional intermediate assignment.

Use Azure Monitor's documented
[granular RBAC](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/granular-rbac-log-analytics)
and [restrictive condition pattern](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/granular-rbac-use-case#build-restrictive-condition).
Require all three conditions: table equals `ContainerAppConsoleLogs`,
platform-populated `JobName` equals the exact acceptance job, and
`EnvironmentName` equals its reviewed environment. Bind the assignment to the
existing workspace from retained state; do not accept table/workspace/job or
environment selectors from workflow-dispatch inputs. Do not use article text,
parsed log messages or caller-provided query filters as permission attributes.
Missing or unsupported conditions must block rather than broaden access.

Audit the dedicated identity's other/inherited grants because RBAC is additive.
Under that identity, verify permitted own-job evidence and that unfiltered,
foreign-job and other-table queries disclose no unrelated data. Validate the
trusted metadata bindings and actual workspace/table compatibility; stop on
scope collisions, unavailable conditions or other grants bypassing the row
boundary. Operator-authorized queries do not prove this isolation.
Remove the now-unused job-logstream data grant. Keep the five existing job
management actions and all inference/registry/telemetry grants unchanged.
Do not add `getAuthToken`, exec, wildcard or unconditional reader permissions.

### 3. Keep cloud execution opt-in and manually approved

Add an owning `phase1-acceptance` azd/Terraform layer, disabled by default.
It owns the dedicated identity/federated credential, narrow custom grants and
one Manual Consumption job. Reuse the existing environment/registry/server/
model/telemetry outputs; never expand production identity maps or recreate
shared resources.

Use a test-only image/harness under `tests/azure/`, with the locked installed
service packages and frozen fixtures, not extra production startup dependencies.
Extend the existing build helper with exact hashing of this harness/Dockerfile/
fixtures plus imported service/core, migration, taxonomy and prompt bytes.
Pin the image by digest and run as nonroot.

Proposed initial execution bounds, not measured SLOs: one 0.25-vCPU/0.5-GiB
replica per execution, no retries, no schedule/ingress, 1,200-second main job
budget and a 30-minute workflow budget including cleanup recovery. Keep
existing model retry/item/lease settings rather than shortening them to fit.
The 300-second natural lease makes a sub-minute end-to-end test unrealistic.

The workflow uses `workflow_dispatch` only, trusted `main`, `contents: read`
and `id-token: write`. The user explicitly approved keeping the personal Free
repository private and using manual dispatch itself as operator approval, since
that plan cannot provide required environment reviewers on a private repository.
Do not attach a GitHub environment or depend on environment variables/secrets
whose availability would require a different plan.

Configure issuer `https://token.actions.githubusercontent.com`, audience
`api://AzureADTokenExchange`, and exactly
`repo:ikhemissi@1769608/newsloom@1429962749:ref:refs/heads/main`.
The owner/repository IDs were verified through the read-only GitHub API and
match the actual assertion from the first failed OIDC dispatch. GitHub's
[current default format](https://github.blog/changelog/2026-04-23-immutable-subject-claims-for-github-actions-oidc-tokens/)
binds names and immutable IDs for this repository. No wildcard, environment
subject, legacy name-only subject, other branch/ref or repository/owner ID is
trusted. The workflow and standalone
launcher independently require the exact repository, dispatch event and main
ref before starting the test job.

Correct only the existing dedicated federated credential through the owning
Terraform/azd layer, after reviewing the native preview. Preserve the same
issuer, audience, identity and all resource permissions. Do not change GitHub's
default OIDC policy or retain/add a parallel legacy credential. Preserve the
failed sign-in and exact operator-cleanup evidence; subsequent verification
uses a newly prepared run rather than reusing or relabelling the failed one.
Use [Microsoft's immutable-subject guidance](https://learn.microsoft.com/en-us/entra/workload-id/workload-identities-github-immutable-subjects)
for the subject format, not its parallel-credential migration strategy: no
working legacy flow exists here that requires a dual-trust transition.

Actual tenant/subscription/client/job identifiers and immutable revision values
live in repository-level Actions variables and ignored azd configuration, not
committed files. They identify resources but are not stored Azure credentials.
No PAT, client secret, developer token or Authorization header enters the
workflow configuration.

This is a trusted-main boundary, not a workflow-filename or two-person approval
boundary: other trusted main-branch workflows with OIDC permission could request
the same identity. Keep repository/main write access tightly limited, review
changes before dispatch, and use any available branch controls without claiming
paid private-repository protection is present. No automatic PR, push or scheduled
cloud trigger is introduced. The isolated Azure authority remains unchanged.

Allow one acceptance run at a time; do not cancel an older run automatically.
Take a prepared run ID and a fixed test-only scenario enum as validated input,
not arbitrary SQL/database names, images, commands or scripts. Normal acceptance,
deliberate failure after ingestion, and controlled job cancellation are the only
scenarios. Neither drill may be reported as a successful acceptance run.
The controller must verify the exact owning job, image/fixture revisions,
execution and report correlation. Query only the conditional console table,
with exact job/environment/container bindings and platform execution/replica
metadata for the recorded execution, never the latest unrelated execution.
Use Entra-authenticated Log Analytics queries, not development-API tokens.
Keep workspace query identifiers in the existing private operator/repository
configuration, using conflict checks and readback; no user bearer token,
shared key or caller-selected workspace is introduced.

Log Analytics is eventually consistent. Poll for the committed-claim checkpoint,
final stage report and cleanup event within one shared, non-resettable deadline,
including after terminal status. The revised evidence allowances below replace
the failed short collection windows, not the approved job/workflow ceilings.
Bound each query, time range, record count and response size. Validate actual
delivery latency and complete exact-run evidence; missing, duplicate, stale or
later-than-deadline evidence remains failure. Query filters provide execution
correlation only; Azure's assignment condition provides authorization.
Do not increase the 1,200-second job or 30-minute workflow ceiling, shorten the
natural lease or broaden permissions to compensate for unavailable evidence.

The first explicit workflow step creates a UTC start/deadline pair with a
**28-minute (1,680-second) controller envelope**, leaving two minutes inside the
30-minute job ceiling for artifact/post-step overhead. This precedes checkout,
authentication and client setup; their elapsed time consumes that same envelope.
It is fixed workflow configuration, not a dispatch input or selectable override.
Retain the original pair in the workflow environment and private execution state,
binding it to prepared run/scenario, workflow SHA, GitHub run ID/attempt and the
existing job/image/workspace/environment bindings. Reject missing, malformed,
naive, stale, foreign or extended deadlines. Cleanup must load the same deadline,
not construct a fresh one.

Derive each process's remaining allowance from that original deadline, then use
monotonic elapsed time for local phase/call enforcement. Never reset a deadline
after a timeout, retry, new polling iteration or cleanup process. The GitHub
30-minute ceiling remains the outer hard stop, not permission to borrow time
reserved for artifact/post-step work.

| Phase | Maximum and accounting |
| --- | --- |
| Main controller | 1,260 seconds from entry, including template checks, start request, status/query calls, sleeps and evidence collection; clamp to shared remaining time |
| Terminal main evidence | No separate 240-second cutoff; collect only until the earlier main/shared deadline, keeping exact report/status validation |
| Cleanup controller | 600 seconds from entry, including stop, startup, status/query calls, sleeps and evidence collection; clamp to shared remaining time |
| Exact main stop | Still at most 90 seconds, additionally clamped to cleanup/shared remaining time |
| Each Azure command | At most 60 seconds and no more than its phase/shared remaining time |
| Read-only timeout retry | At most two retries after the first attempt, with five-second waits charged to the same phase/shared budget |

These caps are not additive reservations or delivery guarantees: setup/main may
leave cleanup less than 600 seconds. Do not issue a call or sleep after its
applicable time is exhausted. Stop only the recorded execution; if absence or
cleanup proof cannot be established in time, fail and retain the operator rescue
reference. Delayed evidence cannot retroactively change a timed-out workflow.

Retry only recognized transport timeouts of read-only execution-status and
log-query operations. Generic nonzero CLI exits, malformed/partial/foreign
evidence and validation failures fail immediately; do not infer retryability
from arbitrary stderr. Never automatically replay a timed-out or ambiguous
start/stop mutation. An unknown start outcome is not proof that no execution
exists and does not authorize starting another or stopping a guessed execution.

### 4. Freeze four complete authored items and reuse real processing

Place one benign and one hostile item in each of an RSS and Atom document.
Give them full required fields and stable `example.com` attribution so article
recovery cannot fetch a fixture URL. Freeze opaque IDs, labels, documents and
expected dispositions before the first model call.

The harness supplies these authored documents at the existing document-retrieval
boundary, then invokes the real parser/staging/screening path. Only the feed
document transport is supplied by the test; it is not a fake scanner or model.
Public network retrieval/SSRF/robots/XML/large-feed protections remain covered by
the existing local hostile fixtures; do not claim public-publisher retrieval
from an in-memory test document.

Use the deployed scanner policy, threshold and calibration binding unchanged.
Require exactly two accepted and two rejected identities; a model failure or
misclassification fails the gate. Replay both documents through actual ingestion
with conditional-validator bypass to prove four duplicates and zero new rows.
Do not insert queue/news/quarantine fixture outcomes directly.

Real model calls use only the dedicated identity and current configured
deployments. A blocked benign generation, invalid output or exhausted budget
fails this test. Do not regenerate labels, tune policy/prompts, retry the whole
study until it looks good or weaken the closed-schema contract.

### 5. Prove recovery without adding production fault injection

Start a test child process that uses the real enrichment worker/providers/
repository. A test-only delegating claim observer reports the committed claim's
opaque identity through an internal pipe, then pauses before model work.
Independently read its processing lease from another connection.

While it owns that identity, start a second worker and prove it claims and
completes the other benign item. Terminate only the first child by its known
PID, verify actual exit and retain its committed processing state. Close all
test process connections.

Wait according to the observed database lease deadline with a finite polling
budget. Do not change the lease, attempts or retry timestamps or pass faster
test limits to production code. Run recovery and require the original identity
on attempt two, one final news row per accepted identity, zero unfinished test
work and zero published hostile identities.

The observer/termination orchestration stays in the test harness. It does not
become an environment flag, remote command input or special branch in the
scheduled enrichment worker. Unit tests separately exercise harness cancellation
and guard failure without real model calls.

### 6. Verify queries without misrepresenting identity or quality coverage

On a read-only snapshot of the test database, invoke the existing MCP repository
for recent, detail, represented-source/category discovery, metadata filters and
query-embedded cosine ranking. Independently read the expected IDs/attribution/
vectors from SQL; verify boundaries, all-tags containment, ranking/scores,
null metadata scores and absence of rejected identities.

The test identity has sandbox write/cleanup authority, not a delegated user
token. This is a real serving-query-path integration test, not another public
MCP endpoint or proof that app-only access works. The earlier actual native
VS Code/Copilot acceptance remains a separate required evidence row.

Likewise, retain the delivered scanner holdouts, 20 enrichment quality cases
and 20 retrieval cases with their original denominators, gates and revisions.
Check their artifact/model/policy/prompt/taxonomy provenance; drift requires
rerunning the owning evaluation, not assuming old measurements still apply.

### 7. Require exact, independently observed cleanup

In `finally`, stop/wait for only owned child processes, close their connections,
verify the exact run/owner/manifest, and connect to the maintenance database.
Drop only the validated disposable database and independently verify catalog
absence before emitting overall success. Use no wildcard, production name,
automatic discovery sweep or blanket connection termination.

If a process is hard-cancelled, the controller's bounded `always()` path stops
the recorded execution and starts the same manual job in explicit exact-run
cleanup mode under the dedicated identity. Cleanup-only mode cannot run model
or data-processing stages. It verifies absence on repeated cleanup; when a
database exists, ownership/manifest checks are mandatory before any DROP.
It must never create a missing target or use another run's manifest.

Cleanup failure leaves the workflow failed and preserves only the exact private
recovery reference. An operator can use the retained migration authority for
explicit rescue, but CI never receives it. Successful rescue does not erase
the original test/cancellation failure. A new run needs a freshly prepared ID.

### 8. Separate bootstrap commits from acceptance evidence

GitHub documents that first-time `workflow_dispatch` requires the workflow file
on the default branch. The user explicitly approved a narrow exception to the
normal Azure-before-commit order: after local validation, publish the minimal
manual workflow/controller bootstrap while its Azure/phase tasks remain
unchecked. Verify that bootstrap SHA's existing offline CI.

The bootstrap launcher/report validator must be self-contained and locally
tested, without importing still-uncommitted harness or service changes.
The bootstrap may call only the already reviewed acceptance job and must fail
closed on missing repository settings or unprepared databases. It must not
provision infrastructure, dispatch automatically, grant itself roles or execute
unreviewed pull-request code. Keep other implementation changes uncommitted
until their required local/operator Azure gates pass.

Then exercise the real manually approved main-branch OIDC dispatch, capture its exact workflow SHA,
immutable image input hash and prepared-run manifest, verify cleanup and the
state-preserving baselines, and commit verified implementation/evidence in the
usual sequence. A published bootstrap is never a completed acceptance run.

The log-query correction changes the launcher and its private inputs. Verify an
isolated corrective bootstrap snapshot and its exact-SHA offline CI before a
new dispatch; the original streaming launcher's CI is historical, not proof of
the replacement. Preserve both failed workflows and their independent cleanup
evidence. Use a fresh prepared database, never reset a consumed run.

The subsequent deadline/diagnostics correction is launcher/workflow/test and
direct-documentation scope only. It requires no new image, grant, resource,
model, workspace policy or production deployment. Revalidate an isolated
published-base plus only the necessary launcher delta, publish it through the
same narrow bootstrap exception, and verify exact-SHA offline CI before a fresh
dispatch. Preserve all three failed workflows, their receipts and cleanup
evidence; the earlier query correction's CI does not validate the new timing
implementation. Any unexpected infrastructure/image drift requires separate
review rather than being absorbed into this correction.

### 9. Preserve content-free and complete evidence

Use the existing safe diagnostic categories/handlers, plus a strict per-stage
report validator. Suppress raw SDK/HTTP/SQL/subprocess exceptions and capture
child events through typed allowlists. Fixtures, summaries, queries, vector
arrays, tokens and actual tenant/client/resource identifiers are not uploaded.

Classify recognized command timeouts, invalid JSON responses and input/deadline
validation separately using fixed safe categories identifying only the
allowlisted operation class. Preserve the original main failure and any cleanup
failure separately. Retain generic failure when the cause is unknown, not a
guessed timeout; the historical cleanup error remains unproven. Never print
exception text, stdout/stderr payloads, commands, URLs, queries, headers or
resource identifiers to explain a new category. Read-only retry diagnostics
must remain content-free and cannot turn exhausted retries into empty success.

Keep an operator-private report and upload only a scrubbed, finite GitHub
artifact containing stage/case IDs, counts, timings and source/image/config/
fixture fingerprints. Use short retention (seven days proposed); committed
acceptance records link to measured workflow results, not raw payloads.

Final phase readiness is a matrix of local regressions, this new federated
integration/cleanup, prior real quality studies, actual production role denials,
native user access and exact-commit CI. Do not require the live backlog to be
empty or erase retained dead-letter work as a convenient passing condition.

## Risks / Trade-offs

- **Database ownership handoff:** test it under real Azure Entra authentication;
  a need for broader/global administration blocks implementation.
- **Shared capacity/quota and Decision retirement:** refresh current support,
  available capacity/rate limits and rates; preserve all deployments/capacities.
  Model/provider/network failure is a failed test, not attack detection.
- **Conditional log authorization:** require exact table/job/environment
  conditions and real no-filter/foreign-data denial tests; additive broader
  grants invalidate the boundary rather than being ignored.
- **Eventual log delivery:** measure checkpoint/report/cleanup availability
  within finite existing budgets; timeout fails and never restores a
  development-token or unrestricted log-reader fallback.
- **Cancellation/finalizer loss:** recovery uses only the same job/identity and
  exact manifest; retain a named operator rescue path and fail closed.
- **Combined test principal:** its union of inference/test-data rights cannot
  prove separate production-unit isolation; use the existing real workload
  evidence for that requirement.
- **Four cases are a smoke, not a quality estimate:** keep original labelled
  evaluation gates and fingerprints unchanged.
- **Workflow bootstrap exception:** constrain it to a locally verified manual
  launcher; leave cloud/phase acceptance open until actual federated evidence.
- **Private Free plan lacks environment reviewers:** explicit manual dispatch
  is the approved gate; trust only main and narrowly scope the test identity.
  This does not provide independent review or isolate a specific workflow file.
- **Later public-repository migration:** publication and environment-review
  setup require a separate decision. Verify the new environment-bound flow and
  remove the old branch-bound credential at cutover, otherwise it could bypass
  the new approval gate. Do not expand the identity's Azure permissions.

## Migration Plan

1. Implement and locally test the private bootstrap/harness/report/cleanup and
   owning infrastructure. Run the full credential-free gate and package checks.
2. Refresh permission/ownership/log API/quota/cost preflights and private baseline.
   Review/apply only the opt-in acceptance additions through existing azd state.
3. Configure exact main-branch federation and private repository-level variables;
   keep manual dispatch as the operator gate. Prepare a run database via the
   migration authority and verify production access denial.
   For the log correction, locally validate the conditional assignment,
   unused-logstream removal, query controller and private input setup. Review
   their native owning preview before seeking deployment approval. Review any
   required helper/image refresh separately; do not silently include changes
   to the shared workspace policy, tables, models, schedules or identity trust.
   Verify actual conditional-role readback and dedicated-identity denial gates.
4. Publish only the explicitly approved workflow/controller bootstrap as needed
   for GitHub dispatch; record its offline CI and keep Azure tasks unchecked.
5. Explicitly dispatch the real main-branch federated workflow, then controlled failure and
   cancellation/recovery cases, verifying exact cleanup and unchanged production.
6. Verify the phase matrix, commit/push completed implementation and retain
   exact-SHA CI, then record final status separately. Leave unverified checks
   pending and leave other changes unarchived.
7. On failure stop only the named test execution; clean the exact database with
   verified ownership. Retain shared state/resources and production data.
   Disable further test dispatch if necessary, without disabling pipeline jobs.
   If the conditional log path must be rolled back, review removal of only its
   assignment and leave acceptance blocked. Do not grant development tokens,
   restore broader readers or alter the shared workspace as a fallback.
