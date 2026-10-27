# Design

## Context

See [the proposal](proposal.md#why) for motivation and
[PRD-2 Step 2.1](../../../../docs/prd-2.md#delivery-plan) for ownership.
The [MCP serving](../../../specs/mcp-serving/spec.md) and
[workload-access](../../../specs/workload-access/spec.md) contracts are delivered.
The MCP verifier already checks trusted v2 tenant keys, its own audience and
`news.read`; its public client has actual browser sign-in evidence. None of that
proves middle-tier OBO.

The workspace has five Python 3.15 packages but no agent package. Its shared
platform creates four workload identities; do not edit that identity set to
smuggle in a fifth principal. Existing owning MCP identity/app layers, immutable
build helpers, HTTP authentication tests and diagnostics provide the patterns.
Core has bounded model transport and allowlisted diagnostics, not a generic
identity framework.

This is a required design: it adds protocol/identity dependencies and a new
cross-service authentication boundary. All behavior below is proposed, not
implemented or Azure-verified.

## Goals / Non-Goals

**Goals:**
- Put the uncertain live identity exchange before model-backed expansion.
- Keep the new audience, managed identity, registrations and state independently
  owned while preserving every existing public MCP contract.
- Make request lifetime the boundary for user credentials, streams and task state.

**Non-Goals:**
- No standing agent-to-MCP principal, database login or operator-token shortcut.
- No durable agent sessions, generic workflow engine or production browser client.
- No research-quality acceptance by inference from a transport smoke.

## Decisions

### 1. Self-host the A2A server in the existing ACA environment

Add `services/agent` as its own workspace package, CLI and immutable container,
using Microsoft Agent Framework with the official server-side A2A adapter and
A2A SDK. The current [Python server documentation](https://learn.microsoft.com/en-us/agent-framework/hosting/self-hosting/a2a/server)
documents `A2AExecutor`; `A2AAgent` is a client, not a server substitute.
Pin a mutually compatible package/protocol set and test a real loopback HTTP
server/client on Python 3.15 before provisioning.

Use one small Consumption replica, initially the same 0.25 CPU/0.5 GiB profile
as MCP, with one replica maximum and no durable task store. This gives a simple
single-process ownership boundary. Recheck memory/streaming behavior and actual
regional replica/token cost before apply; resizing requires review.

Public `/.well-known/agent-card.json` and liveness expose static metadata only.
Guard every SDK invocation/task route before handlers or providers. Advertise
only the implemented recent-news skill and supported streaming mode. Disable
push notifications, remote attachments, arbitrary URL retrieval and unsupported
methods. No Foundry-hosted agent resource, new project, AG-UI route or UI framework
is needed for this ACA-hosted service.

**Alternatives:** a REST-only stub would not prove A2A; using a remote-A2A client
would reverse the required boundary; Foundry-hosted scaffolding would change the
agreed hosting and resource scope.

### 2. Separate the three identities involved in delegation

```text
Signed-in PKCE client
  -- user token A: agent audience / news.agent -->
Agent API + its user-assigned managed identity
  -- validated token A + managed-identity assertion --> Entra OBO endpoint
  <-- token B: existing MCP audience / news.read ------
  -- token B --> Existing MCP --> Existing stored news
  -- own managed identity --> Existing Foundry chat deployment
  -- A2A response stream --> Signed-in client
```

The new middle-tier app exposes delegated `news.agent` and requests only the
existing MCP API's delegated `news.read`. Give the acceptance client its own
public PKCE registration, with reviewed exact loopback callbacks and no stored
credential. Preserve the working MCP public client's IDs, redirects and consent.
Inventory/adopt only explicitly identified owned registrations; never guess by
display name.

The middle tier's federated credential uses the configured tenant's exact v2
issuer, the new managed identity's principal/object ID as subject and the global
cloud's `api://AzureADTokenExchange` audience. These are not the GitHub workflow's
issuer or repository subject. Both identity and app belong to the same tenant.
Keep all real IDs in ignored environment/state outputs.

Use an async managed-identity credential to obtain the assertion for
`api://AzureADTokenExchange/.default`, then a fresh
`azure.identity.aio.OnBehalfOfCredential` for the validated request. Its
documented `client_assertion_func` returns a string, so prefetch the assertion
asynchronously and let the callback return that request-local value without
network I/O. Require enough remaining assertion lifetime for the bounded request.
Request the existing MCP resource's fixed `.default` scope only after verifying
that its consent contains only `news.read`.

The [federated credential documentation](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-config-app-trust-managed-identity),
[OBO protocol](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow)
and [async credential API](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.aio.onbehalfofcredential?view=azure-python)
document the separate primitives. They are not proof that their combination
works with this tenant, consent, pinned SDK and deployed identity. Live proof
is mandatory before the model stage.

**Alternatives:** app-only tokens lose the user; forwarding token A violates
audience separation; client secrets/certificates violate this slice's secretless
contract; a custom OAuth HTTP implementation is unnecessary when the supported
async credential can be verified.

### 3. Reuse verification without coupling the two servers

Extract only the framework-neutral verified-token/key-refresh logic needed by
both services into core, keeping the MCP SDK adapter and `news.read` behavior
unchanged. Add the agent's own audience/scope policy and required user identity
claims separately; do not make `news.agent` an alternate MCP permission.
Run existing MCP signed-key/HTTP/canary tests unchanged and add two-audience
regressions. If extraction changes existing outcomes, fix that before deployment.

Represent the user internally by verified tenant/object identity, not a
cross-audience comparison of `sub`. Bind any transient task/context to that
identity and check ownership on every read, continuation, cancel and subscription
route that the SDK exposes. Client-provided IDs are references, not authority.
No persistent model history or shared mutable bearer headers.

Create an outgoing MCP SDK client and delegated credential per request; close
both on completion, failure and cancellation. Managed-identity credential reuse
is allowed for workload authentication, not user-token caching. Do not import
the MCP server package as the agent's client implementation.

**Alternatives:** duplicating the verifier risks policy drift; importing an entire
server couples deployments; a shared user-token/client cache creates an avoidable
cross-user boundary for this small slice.

### 4. Prove the real delegation path before generation

First deploy a minimal, authenticated, non-generative A2A access path that invokes
`get_recent_news(limit=1)` over the actual MCP HTTP protocol and returns its real
structured result. Its card describes only that implemented capability; it is
not a fake model or a claim that the final streaming agent is complete.

An explicitly signed-in PKCE test client obtains token A and invokes that path.
The actual agent identity supplies the federated assertion. Verify accepted MCP
access and matching user tenant/object identity through private, trusted
token-validation evidence; never compare audience-specific subjects or log
tokens, assertions, raw claims or user IDs. Keep only safe comparison booleans,
operation counts, source/image/configuration fingerprints and test outcomes in
the report. Do not add a public identity-dump endpoint or broaden MCP telemetry.

Also prove missing/invalid incoming authorization, direct token-A-to-MCP refusal,
nondelegated agent-to-MCP refusal and actual out-of-scope workload denials. Use
locally signed tests for exhaustive two-user/token variants; distinguish those
from the live cases actually exercised. Do not disable working federation or
consent merely to induce a failure in another workload.

**Go:** all live delegation and safety evidence is complete. **No-go:** stop with
the affected tasks unchecked before model integration; retain safe failure
evidence and seek a decision rather than weakening credentials or audiences.

### 5. Add only a single-call streamed demonstrator after the gate

Use Agent Framework's Azure OpenAI chat-completions path with the existing
`gpt-5.4-mini` deployment/configuration and the new identity's chat-only data
action. Do not silently switch to a Responses API requiring broader authority,
add an embedding grant or provision another model. Confirm package/API
compatibility and shared quota before inference.

Support one documented recent-news operation: one delegated metadata read and,
for nonempty results, at most one generation streamed through A2A. Keep the
fixed tool outside model-selected authority in this slice. Empty news gets an
explicit no-news result; unknown operations get an unsupported response.
No multi-step research, source fetching or quality score is implied.

Pass bounded MCP result strings as untrusted data, separate from fixed
instructions, without tokens or shared history. The only tool implementation
available to this demonstrator is the approved read path. Later research
orchestration and its adversarial/citation studies belong to Step 2.2/2.3.

**Alternatives:** introducing an autonomous tool loop now would obscure whether
identity or research behavior failed; changing the production model would
invalidate the narrow cost/provenance boundary.

### 6. Bound the full request and suppress SDK content capture

Proposed initial profile: 64 KiB request body, 16 KiB input text, four active
requests, 64 transient tasks retained for at most five minutes, 512 generated
tokens and 120 seconds total wall time. Clamp trusted-key, assertion, OBO, MCP
and inference calls to that remaining budget and token validity. Reject overflow
explicitly; do not evict an active task to admit more work.

The stream/task adapter must map disconnect, cancellation and dependency failure
to cleanup and truthful terminal state, never a successful empty answer.
Bound cancellation with the original request deadline rather than starting a
new recovery allowance. Tests cover exact thresholds and release of each
provider/client after failure.

Reuse core diagnostics and authenticated telemetry, with only operation/outcome,
counts, duration and safe categories. Suppress framework, OpenAI, A2A, MCP and
identity body/query/error logging and content-capturing spans. Token fingerprints
are not a substitute for keeping tokens out of evidence. Canary tests must
exercise automatic instrumentation as well as application logging.

**Alternatives:** SDK defaults alone do not establish end-to-end limits or
privacy; durable task infrastructure is disproportionate to this first boundary.

## Risks / Trade-offs

- **Federated OBO may fail despite valid-looking configuration:** make the live
  same-identity call the blocking gate, with no credential/authority fallback.
- **Agent Framework/A2A dependencies may conflict with Python 3.15 or existing
  MCP pins:** resolve and isolated-startup test first; do not downgrade Python,
  weaken MCP behavior or broadly upgrade existing services to make them fit.
- **One replica and transient state lose tasks on restart:** expose explicit
  loss/not-found; do not promise durable conversations or automatic replay.
- **Shared quota and a new always-on replica add cost:** preview measured regional
  cost, cap requests/output and preserve current model capacity/schedules.
- **A valid delegation smoke is not research quality:** retain the scope boundary
  in the card, runbook, phase status and eventual evaluation evidence.
- **Claim comparisons or framework traces could disclose identity/content:**
  compare privately at trusted verification boundaries and export allowlists only.

## Migration Plan

1. Resolve package/HTTP compatibility and implement the minimal auth/OBO path;
   run focused regressions and the primary gate before any cloud operation.
2. Add opt-in owning `agent-identity` and `agent` layers with separate retained
   state keys. The identity layer owns the new identity, app/client registrations,
   exact FIC, explicitly reviewed delegated consent and narrow grants. The app
   layer depends on it and existing platform/MCP outputs. No database migration
   or change to the shared workload identity set is needed.
3. Inventory permissions and production baselines, review native azd previews and
   actual cost, then apply only approved additions in the existing environment.
   Use the repository's immutable build/source-hash patterns.
4. Run the signed-in non-generative OBO gate immediately. On failure, stop
   expansion, make the new agent unavailable if unsafe and retain owned state
   for diagnosis. Do not destroy registrations or roll back another service.
5. Only after the gate, implement/model-test the streamed demonstrator, rerun local
   checks, review its owning app preview and deploy the immutable update.
6. Verify real A2A discovery/authentication/streaming/cancellation, workload
   denials, content-free telemetry and unchanged Phase 1 resources/data.
   Roll back only the agent revision or disable its ingress if verification fails.
7. Commit verified implementation, check exact-head CI, then record a separate
   evidence/status receipt with its own CI. Archive only when all tasks are
   actually verified; Step 2.2 remains a separate proposal.
