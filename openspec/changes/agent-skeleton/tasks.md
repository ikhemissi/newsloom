# Tasks

All 15 tasks are verified: the live delegation gate, local model/telemetry checks,
deployed signed-in streaming/cancellation/telemetry/denial/preservation acceptance,
implementation publication and separate evidence/status exact-SHA CI passed.
Only Step 2.1 is complete; research, frozen evaluations and the UI remain pending.
Follow
[the design](design.md), [A2A serving](specs/a2a-serving/spec.md) and
[delegated access](specs/delegated-mcp-access/spec.md). The live gate in 3.2
blocks group 4; a failed identity proof must not become a model-only workaround.

## 1. Compatible protocol and minimal delegated runtime

- [x] 1.1 Add the `services/agent` workspace package and resolve/pin the Agent Framework A2A server, official A2A client/server, Azure Identity and MCP client dependencies on Python 3.15. Verify isolated no-dev import/CLI startup, actual loopback HTTP server/client discovery and the selected protocol/streaming APIs, plus unchanged existing dependency/startup tests. Stop on an incompatible graph rather than downgrading Python or broadly upgrading existing services; document the verified package/protocol set in the owning agent runbook.
- [x] 1.2 Extract only the reusable token-verification/key-refresh functionality into core while preserving MCP's adapter, audience and `news.read` policy. Add the agent's separate `news.agent` policy and verified caller identity. Run existing MCP auth/HTTP tests unchanged and add locally signed two-audience/user, signature/key, issuer/tenant/scope/lifetime, ID/app-only and token-directed-URL tests proving refusal before OBO/tool/model work; document the separate audiences and private claim handling.
- [x] 1.3 Implement typed async assertion/OBO and outgoing MCP adapters using the documented request-local assertion callback, fixed authority/resource/scope and one `get_recent_news(limit=1)` call. Test actual SDK callback integration with local transports, assertion lifetime, deadlines, malformed/denied/interaction-required exchange, wrong audience, two-user concurrency, request-local headers, closure/cancellation and no token/endpoint/model-only fallback. Canary-test success/errors and document secretless consent requirements and safe categories without tokens or raw identity-provider payloads.
- [x] 1.4 Implement the minimal non-generative A2A access path, truthful static card, authentication middleware and caller-owned bounded task/context handling without advertising full research. Verify real HTTP discovery/invocation and every enabled task-read/cancel/subscription route, foreign/unknown IDs, unsupported methods/attachments, exact body/text/concurrency/task/deadline boundaries, restart/expiry, disconnect and diagnostic canaries. Document the temporary capability, proposed profile and explicit absence versus failure behavior.

## 2. Owning deployment and pre-cloud readiness

- [x] 2.1 Add opt-in owning `agent-identity` Terraform/azd state for the new user-assigned identity, middle-tier API, separate PKCE acceptance client, exact same-tenant managed-identity FIC, reviewed delegated `news.read` consent and only registry-pull/telemetry/chat grants. Reuse explicit inventory/adoption patterns and pinned providers; test wrong/foreign IDs, no display-name guesses, exact FIC issuer/principal/audience, callback/scope boundaries, no secrets/app-only/DB grants and unchanged shared/MCP resources with mocked providers. Document permission/consent preflight and separate layer inputs; do not modify the shared four-identity set.
- [x] 2.2 Add the owning agent app layer, Dockerfile, immutable build/source-hash and operator verification wiring in the existing environment. Add an explicitly signed-in PKCE A2A acceptance client with memory-only tokens and allowlisted receipts, not a production UI or identity-dump endpoint. Test image/package-only startup, layer dependencies, opt-in behavior, one-replica profile, HTTPS/host/origin/probe controls, private configuration, source binding and failure/rollback commands. Document target-layer previews that cannot run other services' build hooks.
- [x] 2.3 Run the focused identity/protocol/adapter/privacy/operator/infrastructure tests, then `bash scripts/check.sh` and `uv build --all-packages`. Verify all existing ingestion/enrichment/MCP regressions, types, locks and package startup, retain actual counts and stop any owned local helper. Do not call Azure, publishers or real models from normal tests; leave cloud tasks unchecked.

## 3. First live gate: actual secretless user delegation

- [x] 3.1 Privately inventory current directory permissions, exact existing MCP scope/client, model/API compatibility, regional quota, production image/identity/schedule/data baselines and the new replica/token cost estimate. Review the native owning identity/app previews and obtain approval for only the additions/consent before applying through retained azd state. Deploy the immutable non-generative access path without changing MCP registration, shared identities, model capacity or schedules; verify actual app identity, image and trusted configuration.
- [x] 3.2 Complete actual browser PKCE sign-in and invoke the deployed A2A path immediately. Prove the agent identity's exact federated assertion, OBO token for existing MCP `news.read`, one real MCP response and privately validated matching tenant/object user identity; record only safe comparisons/counts/fingerprints. Exercise actual missing/invalid agent authorization, agent-token-to-MCP and nondelegated agent-to-MCP rejection, plus scoped workload denials without altering working grants. Distinguish live cases from local variants and inventory. If any proof is missing, keep this task unchecked and stop group 4; document the exact safe failure and next decision, with no credential, audience, direct-database or app-only workaround.

## 4. Model-backed streaming only after the live gate

- [x] 4.1 After 3.2 passes, wire the single recent-news demonstrator through Agent Framework's existing Foundry chat-completions deployment and A2A streaming, with at most one generation and no model-selected tool authority. Verify real HTTP streaming/terminal states with local model/MCP transports, exact output/time limits, shared quota errors, empty news, unsupported requests, untrusted result strings and no generation on delegation failure. Preserve chat-only authority, request-local history and all current model configurations; document the demonstrator rather than claiming completed research.
- [x] 4.2 Add the final authenticated agent outcome/duration/usage telemetry and disable content-capturing framework/dependency spans. Verify user-message/news/prompt/completion/token/assertion/error canaries on actual HTTP success, OBO/MCP/model failure, overload, expiry and cancellation, including automatic instrumentation. Document the allowlist, delayed ingestion, safe operational categories and bounded request/resource cleanup.
- [x] 4.3 Rerun focused and complete primary checks plus all workspace builds after model/streaming integration. Retain actual results and verify no unrelated package/provider drift; stop owned local helpers. Review the owning app-only immutable update preview and deploy only that revision, not an unqualified all-layer update or a rebuilt MCP image.
- [x] 4.4 Invoke the deployed service from the real signed-in A2A client and verify card/schema parity, user-preserving MCP access, actual streamed Foundry output, correct terminal results, cancellation/cleanup and authenticated content-free telemetry. Independently verify the selected stored record, approved chat access and actual forbidden workload operations; recheck unchanged Phase 1 resources/grants/images/models/schedules and retained data/history. Keep every unmet acceptance gate explicit and roll back/disable only the agent if needed; this does not complete research or phase-wide quality evaluations.

## 5. Persistent verified slice delivery

- [x] 5.1 Only after local and Azure acceptance, commit/push the verified implementation with the required trailer and check the primary CI for that exact SHA. Retain runtime source/image/configuration and measured evidence separately from later documentation heads; do not amend away failures or include unrelated customization changes.
- [x] 5.2 Update the owning runbook, PRD-2/capability/ADR status and this checklist with the measured OBO/streaming/denial/telemetry/local/CI results. Validate links, identifiers and specs, and verify exact-head CI for a separate evidence/status receipt before checking completion. Mark only Step 2.1 complete, leaving research, frozen evaluations and the UI pending.

## Delivery evidence

- Runtime source/image/configuration, actual user-preserving OBO, streaming,
  cancellation, telemetry, denials, data/history preservation and local results:
  [agent runbook](../../../docs/agent.md#actual-model-stage-azure-acceptance).
- Implementation `1b8d4af01fd9a88d880d654c0d984bcdebed5c1f`:
  [passing exact-SHA CI](https://github.com/ikhemissi/newsloom/actions/runs/40500304977).
- Separate evidence/status receipt `58afd2132d85f11531ee64dde11f20c70a5abd6f`:
  [passing exact-SHA CI](https://github.com/ikhemissi/newsloom/actions/runs/40501029431),
  verified before checking 5.2. Later documentation heads do not replace the
  immutable runtime provenance.

## Workflow follow-up

- Present verified results before archival; never archive an unverified OBO gate.
- After review and all acceptance tasks, sync the two delivered capabilities and
  archive this change, preserving evidence and exact runtime provenance.
- Propose Step 2.2 research separately; no implementation follows automatically
  from this planning change.
