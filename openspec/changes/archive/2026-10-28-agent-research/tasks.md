# Tasks

Local implementation, the current owning deployment, signed-in acceptance,
preservation and separate implementation/evidence CI are verified. The delivered
skeleton is the prerequisite, not evidence
that any research behavior below is implemented. Follow the
[design](design.md), [research delta](specs/news-research/spec.md) and
[A2A delta](specs/a2a-serving/spec.md). Web/toolbox and persistent memory/Work IQ
remain in the [PRD TODOs](../../../../docs/prd-2.md#deferred-research-todos).
The user's 2026-10-27 standing authorization covers Step 2.2 implementation,
agent-only deployment and bounded paid acceptance without further approval
prompts. Preserve local-check, owning-preview, finite-budget and verification
gates. It does not authorize new grants, models/capacity, project/toolbox
resources or Step 2.3 evaluation execution.

The first live answer was a correctly cited stored excerpt but failed an
explicit complete-summary request combined with `detail=brief`. The user
confirmed that explicit content requests override presentation hints.
The [initial deployment receipt](../../../../docs/agent.md#research-owning-deployment-readback)
and [failed attempt](../../../../docs/agent.md#first-signed-in-research-attempt-acceptance-remains-open)
remain historical evidence; task 2.5 required fresh local and owning-deployment
verification for the amended source before further live acceptance.

Subsequent candidates passed the complete-summary and comparison cases but
failed discovery safely: first by selecting synthesis with only metadata, then
by attempting an unknown detail ID. These attempts and their observed usage
remain failures. The user approved state-constrained planning, not another
prompt-only retry; task 2.6 tracks the verified follow-up. Repeated local and
exact-source deployment checks, fresh inventory and a cumulative envelope
preceded the passing six-case signed-in run. Prior consumption and unobserved
usage remain explicit. See the
[measured acceptance](../../../../docs/agent.md#state-constrained-actual-acceptance).
Separate implementation and measured evidence/status publication passed
exact-SHA CI; the [delivery receipt](../../../../docs/agent.md#verified-research-delivery)
records completion. Review passed before synchronization/archival; see the
[archival receipt](../../../../docs/agent.md#verified-research-archival).
The approved optional terminal period applies only to individual metadata
comparison claims; complete-summary equality and all other independent
evidence/citation checks remain unchanged.

## 1. Typed research and request-local execution

- [x] 1.1 Add strict research request, presentation-preference, fixed tool/result and final-answer contracts without importing the MCP server into the agent. Verify selected-ID cardinality/duplicates, unknown fields, UTF-8 limits, explicit timezone-aware filters, normalized tags, metadata/detail/not-found shapes and unchanged recent-news DTOs in focused contract tests. Document the additive request and evidence-limit semantics in the agent runbook.
- [x] 1.2 Extract only reusable request-local OBO/session mechanics and implement the four typed read-only MCP operations. Test actual SDK/local HTTP multi-call flow, exact same-user and `news.read` checks, selected/discovered ID boundaries, malformed/denied/expired results, two-user concurrency, original/delegated deadlines and session/token closure on every exit. Existing recent-news and MCP authorization regressions must remain unchanged; document the maintained authority boundary.
- [x] 1.3 Implement structured planning/final synthesis with the pinned Agent Framework chat-completions connector and application-owned dispatch, not automatic tool invocation. Prove the actual local wire options and response parsing, fixed endpoint/model, no provider retries, no arbitrary tool/endpoint/schema execution, explicit malformed/refused/incomplete failures and unchanged single-generation recent-news behavior. Document the verified connector shape and stop for review if pinned compatibility fails.
- [x] 1.4 Implement selected-item bootstrap and the bounded controller with immutable caller constraints, deduplicated evidence and the exact design profile. Test all four tool choices, valid multi-step flows, source/category/tag/date constraints, missing selection, inconsistent records, repeated calls, aggregate byte/token/call limits and exact-boundary/one-over admission without silently truncating evidence. Document accounting and safe failure categories; no web, SQL or model-recollection fallback is allowed.

## 2. Validated answer delivery and private operations

- [x] 2.1 Implement final-structure, evidence-reference, safe-URL, coverage and rendered-size validation before exposing answer text. Test independently authored single/multi-item comparisons, request-local preferences, healthy no-match, missing selected items, absent supporting detail, unknown citations, model-authored replacement URLs and unsupported claims. Every returned citation must resolve to current retrieved evidence; all scripted cases must pass, with semantic support reviewed separately rather than inferred from schema validity. Document explicit limitations and no repair generation.
- [x] 2.2 Wire the additive JSON research operation, truthful enabled/disabled card and explicit PKCE client command through the existing A2A server/task registry. Verify actual loopback official-client progress/validated-artifact streaming, completed readback parity, unsupported/disabled requests doing zero work, unchanged recent-news behavior, malformed inputs and caller-isolated read/list/cancel/context operations. Document buffered validated delivery rather than live draft-token streaming.
- [x] 2.3 Add default-off research enablement to runtime/CLI and the owning app inputs, plus safe aggregate outcome/call/usage observations. Test configuration fail-closed behavior, immutable source binding, native app-only preview/apply wiring, mocked-provider preservation and existing package-only startup. Usage accounting must cover all turns and distinguish unobserved cancellation usage; document enable/disable and agent-only rollback commands.
- [x] 2.4 Extend hostile-content and automatic-instrumentation canaries through actual local HTTP success, invalid plans/citations, OBO/MCP/model failures, overload, expiry and cancellation. Assert no question, preference, plan, news, URL, draft, completion, credential or raw error enters any diagnostic surface. Test disconnect/backpressure and awaited cleanup during tool/planning/final/validation/emission stages; no failed/cancelled request may become completed. Document the unchanged allowlist and observed cleanup behavior.
- [x] 2.5 Implement the confirmed explicit-content-first rule in trusted research instructions without allowing questions/preferences to override caller filters, evidence availability, permissions or budgets. Add focused wire/regression cases for complete stored-summary requests with brief preferences, ordinary brief answers and unavailable full articles. Repeat task 3.1's complete local gate and tasks 3.2-3.3's exact-source immutable build, reviewed owning preview/apply and preservation checks for the amended candidate. Retain the first failed attempt and actual observed usage; define a fresh finite cumulative live envelope before rerunning the exact complete-summary conflict and remaining task 4.1 cases. Do not waive the failed instruction-following case merely because its excerpt and citation were factually supported.
- [x] 2.6 Implement the frozen typed planning scope shared by per-turn closed schemas and independent whole-plan validation before any dispatch. Constrain detail IDs and synthesis to legal starting state, preserve independent batches and all per-call guards, and reject dependent/unknown IDs or invalid later calls without partial execution, repair or retries. Add actual pinned-wire/controller regressions for discovery/detail/synthesis, premature synthesis, healthy empty retrieval, source-list-only state, selected mode, independent batches, caller isolation, remaining budgets and privacy; verify strict-schema compatibility and serialized input bounds. Repeat task 3.1's complete checks, package builds and four-request memory bound, then tasks 3.2-3.3's fresh current inventory and exact-source immutable agent-only build, reviewed preview/apply and readiness/preservation checks. Define a finite cumulative live envelope retaining every prior failed attempt and known/unobserved consumption before rerunning task 4.1; do not mark live, telemetry, cancellation or preservation gates complete until actually verified.

## 3. Complete local gate and authorized owning deployment

- [x] 3.1 Run focused research/agent/MCP/privacy/operator/infrastructure regressions, then `bash scripts/check.sh` and `uv build --all-packages` with disposable loopback PostgreSQL. Retain actual test/type/build/startup/spec counts and no unrelated dependency/provider drift. Measure peak RSS below 400 MiB for four near-limit concurrent requests on the existing profile, including cancellation/backpressure; stop rather than resize or waive a failed bound. Stop/remove owned local helpers and verify their ports are closed.
- [x] 3.2 Privately read back the retained resources, exact app configuration/image/grants/consents, three model configurations/capacities, existing workload images/identities/schedules and time-correlated stored-data/history baselines. Recheck current regional chat availability/shared quota and reviewed chat plus MCP-query embedding price envelope. Under the user's standing Step 2.2 authorization, run only an agent immutable build and native app-only preview; retain the exact source/digest/configuration and expected change set, with no project/toolbox/model/grant additions.
- [x] 3.3 Review the exact owning preview before applying through retained azd state under the user's standing Step 2.2 authorization; no further approval prompt is required within scope. Verify the research-enabled revision is actually ready with the reviewed immutable image, identity/configuration, public card and authorization guards; distinguish activation delay from failure. Reconfirm unchanged resources, other workloads, grants, models and schedules. Leave live acceptance unchecked and use only reviewed agent disable/rollback if deployment is unsafe.

## 4. Actual signed-in research and preservation acceptance

- [x] 4.1 Define and enforce a finite real-client case/model/tool/embedding/token/time envelope under the user's standing Step 2.2 authorization, then perform browser PKCE sign-in and actual selected single-item, multi-item comparison, constrained discovery/search, no-match/detail-limit and cancellation checks. Prove same-user OBO for multiple actual tool calls, safe progress before validated answer artifacts, exact terminal/readback parity and cancellation cleanup. Independently compare every citation with stored records and review each factual claim against its supplied summary/metadata; all executed cases must pass or remain explicitly blocked. Keep content/credentials memory-only and close the callback listener.
- [x] 4.2 Independently verify authenticated content-free traces/metrics/console shapes and actual allowed/forbidden workload operations under the deployed agent identity. Compare pre/post selected-news metadata and actual time-correlated pipeline history, plus resources/grants/consents/images/models/schedules, without assuming scheduled production data froze overnight. Retain actual failures, delayed-ingestion corrections and safe receipt hashes; do not restore/delete data or broaden access. No research acceptance is complete while any required live, privacy, citation or preservation gate is unmet.

## 5. Persistent verified delivery

- [x] 5.1 Only after complete local and actual Azure acceptance, commit/push the verified implementation with the required contributor trailer and verify primary CI for that exact SHA. Exclude unrelated customization changes and private environment/evidence. Retain runtime source/image/configuration provenance separately from Git/documentation heads and preserve unsuccessful attempts honestly.
- [x] 5.2 Publish a separate measured evidence/status receipt covering local/CI, actual user-preserving research, semantic/citation review, telemetry, denials, cancellation, cost and preservation. Update the runbook and owning phase/capability/ADR/checklist status, validate links/commands/identifiers/specs and require its exact-head CI before checking completion. Mark only Step 2.2 delivered; frozen phase-wide evaluations, deferred web/toolbox, memory/Work IQ and UI remain pending.

## Workflow follow-up

- Present verified results and request review before synchronization/archival.
- Archive only after every tracked acceptance task is actually verified.
- Propose Step 2.3's frozen phase-wide evaluation slice separately.
- Revisit web enrichment and persistent preferences through the owning PRD TODOs,
  not hidden additions to this change.
