# Design

## Context

See [the proposal](proposal.md#why) for motivation and the
[evaluation delta](specs/agent-evaluation/spec.md) for the observable contract.
This is the interoperability foundation, not P2-C06's baseline delivery.

The repository has one Python 3.15 uv workspace, six packages and a
credential-free [primary check](../../../scripts/check.sh). The
[agent image](../../../services/agent/Dockerfile) installs only the agent package,
without development dependencies. Existing research, signed-in client and
content-free telemetry stay unchanged.

The retained AIServices account is owned by the application Terraform root,
uses disabled local authentication and has `prevent_destroy`. Its configuration
does not yet enable project management or define an account managed identity.
AzureRM 5.10.0 documents both `project_management_enabled` and
`azurerm_cognitive_account_project`; the latter requires a managed account
identity and custom subdomain. No new provider is needed for those resources.

The user selected account reuse on 2026-10-28 after reviewing the lasting
configuration trade-off. Disabling project management or removing the required
identity later would require account replacement. They must therefore remain
configured even if the evaluation project is subsequently retired.

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

Register a minimal custom code evaluator that returns the already computed
score, labelled `imported_deepeval_faithfulness`. It does not import DeepEval,
call a judge or reinterpret the score. Foundry's documented code sandbox has no
network access and returns a float, not an explanation. Preserve the explanation
as an explicit synthetic dataset field and verify its accessibility in case
details, rather than promising a native judge-reason field.

Supply the required orchestration deployment reference only after verifying it
resolves to the existing approved deployment. Do not create a deployment merely
to satisfy that field. A demonstration display threshold is not a phase-quality
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
existing operator data-plane access before proposing any missing project or
chat permission. The operator's management authority is not proof of a
least-privilege automation identity; dedicated federated execution is a later
slice. Existing workload identities receive no new grants.

The user selected a custom chat-completions-only grant for that operator at
the retained account scope, plus project-scoped evaluation permissions. This
is operation-level restriction, not deployment-level IAM isolation: it also
authorizes future chat-capable deployments in that account. The runner must
still admit only the approved deployment and model snapshot. Do not assign the
broad Foundry User role or inference grants to either new managed identity.
The exact catalog and evaluation lifecycle permission mapping remains a
preflight gate; an unverified mapping must not trigger broader-role fallback.
This permission-design choice does not approve provisioning or paid inference.

Before provisioning, verify current regional project/evaluation support,
deployment visibility, quota and local-auth state. Review the exact application
and evaluation plans and a principal/scope/operation inventory. Account
replacement, new accounts/models, unsupported scopes or unavoidable broader
permissions require a separate user decision, not an implicit fallback.

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

These are proposed limits, not approval or a verified price quote. Refresh the
existing deployment's throughput and prices first. Admission must use a verified
conservative input-token bound for the actual serialized request, output ceiling
and current prices. If that cannot fit safely, stop rather than dispatch on an
optimistic estimate. Disable provider/library generation retries; transport
admission remains authoritative even if a library attempts an extra call.

Include all admitted attempts in the cumulative receipt. Track observed usage
separately from reserved/unobserved usage; never release an uncertain reservation
or label cancellation as free. Shared scheduled workloads retain priority:
avoid active enrichment windows and do not increase deployment capacity.

Define finite counts/timeouts for dataset/evaluator/evaluation/run mutations and
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
cleanup rather than an assumed automatic TTL. Before upload approval, document
the actual service retention/backup limits and demonstrate the exact-owned
deletion/reconciliation path using a disposable metadata-only probe. Verify that
cleanup cannot target foreign evaluations, shared data or the retained model
account. Unsupported deletion or retention behavior requires a policy decision
before pilot-content upload.

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
- [Result readback and report references](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-results)
- [DeepEval Azure authentication](https://deepeval.com/integrations/models/azure-openai)
- [Pinned account provider documentation](https://github.com/hashicorp/terraform-provider-azurerm/blob/v5.10.0/website/docs/r/cognitive_account.html.markdown)
- [Pinned project provider documentation](https://github.com/hashicorp/terraform-provider-azurerm/blob/v5.10.0/website/docs/r/cognitive_account_project.html.markdown)
