# Design

## Context

See the [proposal](proposal.md#why) for motivation and the
[baseline delta](specs/agent-quality-baseline/spec.md) for acceptance.
The [foundation](../../specs/agent-evaluation/spec.md) is delivered and archived.
This is an external operator workflow, not a Foundry-hosted agent migration.
Known target: `services/agent/`, retained `dev` azd environment; actual deployment
context stays in its existing ignored configuration, not `.foundry` overlays.

Observed reusable interfaces:

- [The A2A client](../../../services/agent/src/newsloom_agent/client.py) already
  returns `ResearchInvocation.text` and metered counts from `invoke_research`;
  it validates streaming against completed task readback. Its verification
  command intentionally exposes counts only.
- [Research contracts](../../../services/agent/src/newsloom_agent/research_models.py)
  bound requests to five selected items, eight tool calls, four model calls,
  120 seconds, 262,144 observed input tokens and 4,096 output tokens per receipt.
  These limits remain authoritative; baseline tooling cannot increase them.
- [Pilot inputs](../../../tools/agent-evaluation/agent_evaluation/inputs.py)
  are deliberately closed to exactly two authored cases. The
  [metric](../../../tools/agent-evaluation/agent_evaluation/metric.py),
  budget and canonical-string publication primitives are reusable; its pilot
  approval/result schema must not be widened into a general content uploader.
- [MCP search](../../../services/mcp/src/newsloom_mcp/app.py) invokes one logical
  query embedding for a non-null query.
  [The retained transport](../../../packages/newsloom-core/src/newsloom_core/model_transport.py)
  permits three attempts. The A2A receipt does not provide per-case embedding
  billing, so this exposure must remain separately reserved.

## Goals / Non-Goals

**Goals:** freeze a small measurable baseline, exercise actual signed-in research,
detect evidence drift, and preserve exact content-free results and failures.

**Non-Goals:** changing agent behavior/image, broadening tool authority,
persisting production-derived content, or treating a small baseline as
statistically calibrated population quality. Later comparisons/monitoring remain
separate. No new dependency or resource is proposed.

## Decisions

### 1. Freeze a manifest, not the live database

Commit authored request templates, schema, case IDs and control fixtures.
Keep actual selected-item IDs in ignored private input bindings. Bind question/
preference templates, allowed evidence/result-set fingerprints, authored
expectations, source/image/configuration, metrics and applicability into a
versioned manifest before generation. Oracles contain authored expectations,
not copied news text. Summary content is read under the same signed-in user
only into memory and verified before/after each case.

The initial 12 live cases are fixed:

| Cases | Coverage |
| --- | --- |
| b01-b02 | Selected-item explanation, language/detail preferences and explicit content priority |
| b03-b04 | Two-item and multi-item comparison with exact selected-item/citation coverage |
| b05-b06 | Discovery and source/category/tag/date constraints within a frozen candidate pool |
| b07-b08 | Partial missing selection and unavailable external detail, with honest limitations |
| b09-b10 | Healthy no-match and requests exceeding available evidence/tool authority |
| b11-b12 | Missing authorization and wrong-audience authorization, with expected denial |

Freeze semantic/citation eligibility for b01-b08; b09-b12 have contract-only
oracles. A failure to produce the expected supported/limited claims is a case
failure, not grounds to switch applicability. Discovery checks pin the complete
bounded candidate pool and date cutoff; unexpected matches, missing items or
changed summaries stop that case. No automatic snapshot refresh or production
write is permitted. Later reruns require identical bindings or a new version.
Preparation uses only source/detail/recent or query-less filtered MCP reads,
not semantic searches that trigger paid embeddings. Discovery pools must fit
the public response bounds completely; an ambiguous truncated pool is rejected.
Any semantic search occurs only inside the subsequently approved paid envelope.

Alternative rejected: judging against whatever news appears later, which makes
model drift and evidence drift indistinguishable.

### 2. Keep the two locked environments separate

Use a root-workspace capture worker launched explicitly through the locked
agent package environment. It composes existing PKCE, `invoke_research`, official
A2A/MCP clients and strict receipt checks; it does not change the production
verification command or server output. A separately locked evaluator
supervisor/worker owns DeepEval, judge credentials, accounting and publication.
Never import the agent via an undeclared cross-environment path or combine locks.

Use typed versioned, nonce/case/hash-bound memory pipes, not content files or
environment-variable payloads. Bound an IPC frame to 256 KiB and each direction
to 8 MiB cumulatively; reject overflow before processing rather than truncate.
Raw evidence/answer frames are transient. Judge explanations never cross into
saved results. Tokens remain with their owning client and never cross IPC.
Do not forward child stdout/stderr or raw parse failures to logs; use fixed safe
categories and test noisy/crashing children with canaries.

The current A2A token is not an MCP token. Reuse the separately registered public
MCP client and its existing consent for read-only evidence binding, with
independently validated same-user identity. Prove this adapter locally and under
a separately approved bounded readiness/sign-in check before paid generation.
No new scope, application, application-only fallback or migration identity is
allowed if that proof is unavailable.

Alternative rejected: adding agent dependencies to the DeepEval environment,
which repeats the dependency-isolation problem; production tracing is likewise
not a substitute for an operator capture interface.

### 3. Calibrate first and keep scoring dimensions explicit

Use eight authored controls: four fully supported and four wholly unsupported/
contradictory answers, including untrusted-instruction text. Freeze labels and
fixtures. Proposed gates are supported scores at least 0.8 and unsupported
scores at most 0.2, with complete execution/usage and all eight labels matching.
Failing controls stop before live generation; their scores/usage remain recorded.
This is a small calibration sanity gate, not evidence of population accuracy
or independence between a judge and agent sharing a model family.

For b01-b08, use the existing asynchronous DeepEval faithfulness adapter on the
actual answer and exact frozen summary evidence. Proposed release criteria are
each eligible score at least 0.8 and their macro mean at least 0.9. All frozen
deterministic citation/request/denial gates must pass. These criteria require
review and freezing before execution; do not tune them after observing answers.

Validate canonical stored citation URLs and expected item coverage separately.
URL membership proves structural validity, not semantic support; faithfulness
and authored evidence obligations supply the semantic check. Judge against
provided evidence, not the model's training cutoff or external current facts.
Keep no-match and denied-case applicability explicit rather than manufacturing
zeros or counting them in a semantic average.

Exact operation/argument/identity/no-dispatch controls run against the actual
research controller and scripted MCP/model transports offline, including hostile
retrieved summaries. Live receipts prove only their actual exposed fields,
caller preservation and observed outcomes; they are not per-call traces.
Do not insert attack items into production to claim a live indirect-attack test.

### 4. Reserve all model exposure before dispatch

The following is a proposed execution envelope, not approval:

| Surface | Proposed bound |
| --- | --- |
| Live A2A requests | 12 slots, including denials/failed or unknown sends; one in flight |
| Agent chat exposure | At most 48 logical model calls; reserve 262,144 input/4,096 output tokens per live request before dispatch |
| Judge | 80 attempts, one in flight, at least 70 seconds apart, 1,024 output tokens/attempt |
| Judge bytes | 64 KiB request/response per attempt; 5 MiB each cumulatively |
| Evidence MCP operations | 160, including binding and drift checks; 64 KiB per response, 10 MiB cumulative |
| Query embeddings | Reserve up to 768 dispatch exposures: three attempts times 96 agent-tool operations plus 160 operator MCP operations |
| Context/readiness | 60 scoped reads before and 60 after; 40 authentication metadata/token HTTP operations, at most four explicit PKCE flows |
| A2A readback | 12 completed-task GET slots; request-owned cancellation only within the original case window |
| Publication | Three metric definitions/runs, six creates, 180 reads, 30-second requests, five-second polling |
| Overall | One three-hour execution deadline and USD 10 combined agent/judge/embedding estimated admission ceiling |

Reserve embedding cost for every possible query-bearing operation using a
verified conservative token bound for the existing 2,048-character query limit,
including all three retained transport attempts. Do not equate transport
observations for shared traffic to per-case measured usage or claim embedding
cost is zero. Keep unobserved embedding/failed-request exposure reserved in the
receipt. Agent chat usage and isolated judge usage are reported separately.
Verify actual physical retry/call limits and current prices before admission;
any mismatch or inability to fit the combined ceiling stops execution.

Journal only metadata intent/counters before each request. Preserve all prior
reservations and unknown outcomes across failure. Scoring is not replayed after
process loss; losing transient answer data does not authorize regenerating it.
Fresh user approval is needed for another run, with the original attempt linked.
No periodic credential renewal, mutation retry or additional sign-in silently
extends the shared deadline. Respect enrichment windows and retained throughput.
This ceiling is not billing enforcement and excludes infrastructure charges.

### 5. Publish metadata only, without an N/A score fiction

Use a distinct `baseline-v1` approval/journal and strict allowlisted rows:
opaque suite/case/metric IDs, source/configuration/input hashes, canonical score
text, modality and fixed outcome categories. Never reuse the pilot's
question/evidence/answer/explanation-bearing row schema or old approval.

Publish three native inline Python reports: faithfulness and citation validity
for their frozen eligible cases, and contract adherence for all live cases.
Use one definition/run pair per metric so inapplicable cases need no fabricated
float or service-error skip placeholder. A content-free suite index binds all
12 cases and each metric's exact eligibility mask and denominator.
Control/offline outcomes remain separately labelled receipts, not live averages.

Reuse canonical-string score encoding, minimal numeric replay, preview headers,
wrapped-row normalization and paginated exact parity. The grader replays a
measured score and never calls a judge. Require API and actual report UI
case/metric parity; user attestation remains distinct from API receipts.
Propose the same 30-day manual report retention. Do not delete accepted reports
as probes or assume automatic expiry/backup erasure.

### 6. Preserve content and deployment boundaries

The user selected transient real evidence and metadata-only saved results.
Only authored templates/controls and private non-content bindings persist.
Production-derived questions/preferences, summaries, answers and judge reasons
enter no new file, log, cache, trace, crash report or Foundry dataset. Existing
authorized A2A task/model-service retention is unchanged and disclosed; Python
memory lifetime is not a physical-erasure guarantee.

Canary-test capture, IPC, actual libraries, subprocess failure/cancellation,
scoring and publication. Keep the pilot's authored-only behavior untouched.
Do not turn privacy/parser failure into a safe-looking score or default field.

No deployment is intended: local operator tooling invokes the retained accepted
image. Keep evaluator/capture source distinct from that image's provenance.
Run local gates before source-bound azd owning no-change previews and scoped
readback. Reject unexpected resources, grants or production changes; if a
deployment becomes necessary, stop for an owning scope decision.
Verify selected evidence and runtime/model/grant/configuration/schedule
boundaries without promising a fresh full-database/admin verification or
unchanged inherited access. Policy-managed scanning resources remain outside
direct application ownership; no Defender work is introduced.

## Risks / Trade-offs

- Small suite and same-family judge bias -> label the limits, use authored
  positive/negative controls and independent deterministic checks.
- Limited live tool observation -> retain exact offline assertions and exposed
  live receipts as different evidence, not a fictional complete live trace.
- Changing discovery/news -> freeze IDs/result sets and check hashes; drift
  blocks acceptance rather than refreshing the baseline silently.
- Existing MCP retries/unattributed embedding usage -> reserve worst-case
  exposure inside the combined ceiling; disclose unknown rather than estimate
  it as measured or broaden telemetry access.
- Transient-only content cannot resume after loss -> retain failed metadata
  and require a separately approved run, never persist raw content for recovery.

## Migration Plan

1. Implement only operator tooling, fixtures and tests; preserve both locks and
   production closures, then pass the local primary gate and six builds.
2. Obtain fresh bounded readiness/sign-in authorization; verify exact no-change
   owning previews, identity/evidence/model/price readiness and selected oracles
   using only non-inferencing preparation reads. Carry these read counters
   into execution approval rather than resetting them.
3. Present the frozen manifest, thresholds, conservative combined reservations,
   retention and exact envelope for separate explicit execution approval.
4. Run controls, actual cases and scoring once; stop on errors/drift/limits.
   Publish exact metadata-only results without rewriting any failed receipt.
5. Verify UI/API parity and scoped preservation, then publish implementation
   and separate measured status with exact-source CI before baseline acceptance.

Rollback stops operator work and closes owned clients/processes; it changes no
production configuration and does not remove retained pilot/baseline reports.
No schema migration, new admin execution, archival or PRD-3 work is implied.
