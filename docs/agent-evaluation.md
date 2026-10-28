# Agent evaluation

## Status and scope

This is the active [evaluation foundation](../openspec/changes/agent-evaluation-foundation/proposal.md),
not the frozen quality baseline or completed
[P2-C06](prd-2-capabilities.md#p2-c06-repeatable-agent-quality-and-azure-acceptance).
The [task ledger](../openspec/changes/agent-evaluation-foundation/tasks.md) owns
acceptance status. Research is already delivered; its measured evidence belongs
to the [agent runbook](agent.md).

Verified locally: the separately locked evaluation project resolves on Python
3.15.1, real DeepEval and Projects SDK imports and mocked wire execution succeed
with network admission blocked, and import-time privacy checks pass. The application lock and all six
production dependency graphs remain unchanged; isolated agent startup and six
application package builds pass. The isolated check passes 213 tests, strict
types, lint and formatting, including the complete bounded scoring pipeline
with real DeepEval and the native OpenAI SDK over scripted transports.
The native SDK publication pipeline and ambiguous-outcome recovery also pass
against scripted transports, as do exact-owned cleanup and fresh-process
privacy canaries. The Azure foundation, actual service/sandbox
execution, API/report visibility and paid acceptance are not established by
those tests.

No evaluation project, model, grant or paid run has been created. Account reuse
and dependency isolation are design choices, not execution approval. Exact Azure
previews, identities/grants, retention and the finite pilot envelope still need
the owning task's explicit approval.

## Owning infrastructure boundary

The [application root](../infra/main.tf) configures project management and a
system-assigned identity directly on the retained AIServices account. These
are lasting prerequisites, independent of whether the evaluation layer is
enabled. The account's `prevent_destroy`, disabled local authentication,
subdomain, model definitions and production workload grants remain configured.
[Application outputs](../infra/outputs.tf) expose the resulting identity and
project-management state for independent readback.

The separate [evaluation root](../infra/agent-evaluation/) is registered in
[azd](../azure.yaml), depends only on `application`, and uses the existing
AzureRM 5.10.0 provider with Entra-authenticated state at
`newsloom/<environment>-agent-evaluation.tfstate`. It creates no model, account,
application, storage connection, diagnostics setting or standalone execution
identity. Its disabled default has no resources or identity-context reads.
When explicitly enabled, its entire resource boundary is:

- One child project with its own system-assigned identity and destruction guard.
- Two custom data-only role definitions, with no management actions, keys,
  connection secrets, wildcard data permissions or inherited-role substitutions.
- Two assignments to the exact selected human operator: chat completions on
  the retained account, and the evaluation operations below on this project.
  Neither new managed identity nor any production workload receives a grant.

The user selected account-scoped chat-only operator access. This is not
deployment-level IAM isolation: it authorizes future chat-capable deployments
in the account too. The fixed judge transport and approval still admit only
the selected deployment/model snapshot. The broader built-in Foundry User
role is deliberately not assigned.

The candidate project role enumerates the registered provider data actions
`Microsoft.CognitiveServices/accounts/AIServices/evaluations/read`,
`Microsoft.CognitiveServices/accounts/AIServices/evaluations/write`,
`Microsoft.CognitiveServices/accounts/AIServices/evaluations/delete`,
`Microsoft.CognitiveServices/accounts/OpenAI/evals/read` and
`Microsoft.CognitiveServices/accounts/OpenAI/evals/write`. Native registration
proves that these operation names exist, not that every catalog/run/delete
route authorizes against this set. Exact catalog/lifecycle mapping, native
project scoping and actual report access remain unverified. A permission
failure must stop for review, never add Foundry User or account-wide evaluation
authority as a fallback. See the official
[evaluation permissions](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluation-permissions)
and [custom-role guidance](https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry#create-custom-roles-for-projects).

### Metadata-only preparation

The [platform preparer](../services/platform/src/newsloom_platform/agent_evaluation.py)
is exposed as `newsloom-platform prepare-agent-evaluation-layer`; azd invokes
it for this layer. Disabled preparation initializes only missing private
evaluation inputs and preserves existing operator/output values. Enabled
preparation checks the retained account ID/name/endpoint, selected CLI
subscription/tenant/human operator, local-auth denial, account identity and
the existing chat model/version/SKU/capacity/no-upgrade contract. All four
Azure operations are metadata reads. Only the verified evaluation operator and
tenant inputs are written back to the existing private azd environment.

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

These are local mocked-provider/configuration checks, not proof that the
retained account's native update plan is replacement-free or that Azure accepts
the proposed authorization. Both owning native plans and independent deployed
readback remain separate gates before pilot use. The primary check includes
the new layer's locked initialization, validation and tests.

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
agent image. Native preview/review and execution approval remain pending.

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
exercise `AIProjectClient.get_openai_client()` with the real SDK's Azure-specific
criterion type. The observed paths are the project's `/openai/v1/evals`,
`/evals/{eval}/runs` and `/evals/{eval}/runs/{run}/output_items`. Inline
precomputed input uses `type=jsonl` with a `file_content` source containing
`{"item": row}` entries. Readback follows both mocked output pages rather than
accepting the first page. The publication tests additionally exercise native
catalog registration and version-list serialization/authentication over the
controlled transport. Real catalog submission and sandbox execution remain
unverified.

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
The runner also excludes the 70-second windows around half-hour schedule
boundaries; it does not change schedules or increase capacity.

The [shared controller](../tools/agent-evaluation/agent_evaluation/budget.py)
implements the [proposed finite envelope](../openspec/changes/agent-evaluation-foundation/design.md#5-finite-accounting-before-the-first-paid-request).
Each admitted request reserves the full 400,000-token model context as a
conservative input bound, plus 1,024 output tokens. This deliberately exceeds
the [documented model's](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
272,000-token maximum input; it is not an optimistic bytes-to-token estimate.
At the illustrative, not freshly Azure-approved, USD 0.825/4.95 per-million
prices, each reservation is USD 0.3350688. Only reliable, strictly validated
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
| `publication_mutation_limit` | 3 |
| `publication_read_limit` | 60 |
| `publication_request_timeout_s` | 30 |
| `publication_poll_spacing_s` | 5 |

The three mutations are one custom evaluator version, one evaluation definition
and one run containing the explicit two-row inline dataset (`file_content`).
There is no separately registered storage-backed dataset, Blob credential or
new storage grant. Reads include catalog/evaluation/run reconciliation, polling
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
The existing approved deployment is independently checked before use as the
service's required orchestration reference. No new deployment is created.

Raw output pages are validated before the permissive SDK response models can
coerce values. Case IDs, exact scores (including fractional values), synthetic
explanations and complete row lineage must match the original rows. Missing or
duplicate cases, stale rows, boolean/nonfinite/range errors, definition drift,
sandbox execution errors and incomplete/failed runs cannot become valid zero
scores or a successful publication.

Each mutation's intent is fsynced before dispatch. The private
`publication-state.json` retains its attempted stages, unknown outcome, owned
references, consumed reads and latest verification state. An exclusive local
lock prevents concurrent publishers for one journal.
Reinvoking `publish` defaults to read-only recovery: it reconciles exact owned
catalog/evaluation/run metadata and can finish readback for an already submitted
run, but cannot repeat a create request.

If reconciliation establishes that later metadata operations were **never
attempted**, the operator can explicitly add `--continue-unsubmitted`.
Only those still-unused operations may then run, within the original three
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
HTTP transports. They cover all three ambiguous mutation stages, read-only
recovery and explicit unsubmitted continuation, full pagination, persistent
60-read polling exhaustion, deadline preservation, fractional scores, malformed
rows, failed runs, definition drift and retained unknown judge reservations.
They do not establish service-side sandbox behavior, deletion, retention, actual
Foundry visibility or deployed-agent quality.

## Retention and deletion feasibility

The proposed pilot-artifact window is 30 days, with explicit operator-owned
cleanup, not automatic service expiry. Exact-target cleanup and privacy
canaries are implemented and verified locally. The real metadata-only deletion
probe and observed service lifecycle remain pending in the
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
| `schema_version`, `execution_approved` | `1`, and the separately recorded execution decision |
| `source_sha256`, `context_sha256` | Current cleanup source and selected operator/environment fingerprints |
| `historical_approval_sha256` | Exact original producer approval bytes and registry entry |
| `publication_state_sha256` | Exact historical publication-state file bytes |
| `project_id`, `project_endpoint` | Selected private azd outputs, checked independently on execution |
| `origin` | `imported_deepeval_faithfulness`, or the separately owned `newsloom_metadata_probe` namespace |
| `catalog_version`, `evaluation_id`, `run_id` | Exact owned references; evaluation/run may be null only for unattempted stages |
| `approved_at`, `expires_at` | Timezone-aware timestamps; approval valid for at most one day |
| `read_limit`, `mutation_limit` | Exactly `60` project metadata reads, `3` deletes, cumulative across re-entry |
| `request_timeout_s`, `deadline_s` | Exactly `30`, `600`; deadline starts at approval, not restart |

The catalog name is derived from the historical approval fingerprint, not a
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

Before any deletion, exact GETs verify catalog/evaluation/run metadata ownership,
names and parent references. Runs must be terminal. Complete paginated metadata
inventories reject foreign runs and other evaluations depending on the selected
catalog. Deletion proceeds through the owned run, then its empty evaluation,
then the exact evaluator version. No project, model, grant, shared dataset or
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

Project API/regional support is documented, but evaluation API/lifecycle
feasibility and the exact missing grants still require the remaining preflight
and owning previews. No account setting, grant, model or stored record was
changed. Refresh baselines and pricing before execution approval.

## Provenance and remaining acceptance

The workspace exclusion and README are agent build inputs even though runtime
dependencies are unchanged. The new evaluator checkout must not be presented as
the source that built the already accepted production agent image. Later
evaluation receipts must bind the tool manifest/lock, source, fixtures and
configuration separately from that accepted image/source.

The two-answer runner, imported-score publication/recovery bridge, exact-target
cleanup and privacy safeguards are verified locally. Real service acceptance
and the proposed retention policy
remain governed by the
[design](../openspec/changes/agent-evaluation-foundation/design.md).
Neither local evidence nor proposed limits establish cloud behavior or permission
to run inference. Continue through owning Terraform and full integration checks
before requesting execution approval. Do not upload production news or
conversations, enable content tracing, or use Confident AI credentials.
