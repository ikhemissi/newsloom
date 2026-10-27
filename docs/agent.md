# Agent skeleton runbook

## Status and scope

[Step 2.1](prd-2.md) is complete and verified. Its
[archived change checklist](../openspec/changes/archive/2026-10-27-agent-skeleton/tasks.md) owns delivery
progress. Local package/protocol compatibility, the agent's separate authorization policy,
request-local delegated adapters and the non-generative authenticated A2A
application are verified locally, as are the opt-in owning layers with mocked
providers, package-only container and explicit PKCE acceptance client.
The owning identity layer is provisioned with independently verified federation,
delegated consent and narrow grants. The immutable non-generative agent app is
deployed with independently verified configuration and public authorization
guards.
Actual browser sign-in, secretless OBO, a user-preserving MCP read and the
required live workload denials have passed. Task 3.2's live gate is complete.
The model-backed revision is now deployed with verified local and Azure runtime
acceptance: actual signed-in streaming, cancellation, authenticated private
telemetry and final workload/data preservation. See the
[live model-stage receipt](#actual-model-stage-azure-acceptance).
Implementation publication and the separate evidence/status receipt passed
their own exact-SHA CI; see the
[publication receipt](#verified-implementation-publication) and
[final delivery receipt](#verified-evidencestatus-delivery).
All 15 tasks are verified; only Step 2.1 is accepted. Its OpenSpec change is
archived with the delivered A2A/delegation contracts synchronized to main specs.
Research and the browser UI belong to later slices.

This runbook owns commands and measured implementation facts, not another
requirements copy. See the
[archived design](../openspec/changes/archive/2026-10-27-agent-skeleton/design.md),
[A2A serving contract](../openspec/specs/a2a-serving/spec.md) and
[delegation contract](../openspec/specs/delegated-mcp-access/spec.md).

## Verified local package and protocol set

The owning [agent package](../services/agent/pyproject.toml) pins:

| Component | Version |
| --- | --- |
| Python | 3.15.1; supported interval `>=3.15,<3.16` |
| Agent Framework core | 1.23.0 |
| Agent Framework OpenAI connector | 1.17.0 |
| OpenAI SDK | 3.39.0 |
| Agent Framework A2A adapter | 1.0.0b261022 |
| Official A2A SDK with `http-server` extra | 1.2.3 |
| Azure Identity | 1.26.0 |
| MCP client | 2.3.0 |
| MCP client's HTTPX2 transport | 2.16.0 |
| Starlette / Uvicorn | 1.9.0 / 0.54.0 |

The adapter's explicit prerelease pin does not enable prereleases globally.
The minimal graph adds 15 packages, including `newsloom-agent`; all 89 prior
lockfile package versions and sources remain unchanged. Serving adds only
`types-protobuf` to development dependencies for strict typing of the pinned
SDK's protobuf parsing API (105 packages at that stage). The post-delegation
model stage adds the official optional `agent-framework-openai` connector,
OpenAI SDK, `jiter` and `sniffio`: **109 locked packages**, retaining all prior
versions. Azure Monitor/OpenTelemetry were already in the graph and are now
direct agent dependencies. Core's optional `telemetry` extra supports the shared
span-rebuilding helper without adding telemetry to its base installation.

The verified wire interface is **A2A 1.0 JSON-RPC over HTTP**, discovered at
`/.well-known/agent-card.json`. SDK 1.2.3 uses protobuf types, not the older
Pydantic message constructors. The compatibility probe uses
`create_agent_card_routes`, `create_jsonrpc_routes`, `DefaultRequestHandler`
and `A2AExecutor`; the client uses `A2ACardResolver` and `ClientFactory`.
The actual application uses the same official routes/executor with its own
bounded `RequestHandler` and producer-side `EventQueue` implementation.

[Compatibility tests](../tests/test_agent_compatibility.py) bind an OS-assigned
loopback port, discover the real HTTP card, invoke through the official client,
retrieve the completed task and check the exact response. Both executor modes
and both client modes are tested. The non-streaming executor returns its message
through task status/history rather than an artifact. Streamed chunks share an
artifact ID with correct append behavior and a completed terminal status. All sockets, servers
and clients are closed after the tests. This deterministic test-only provider
does not call Azure, MCP, Entra or a real model and is not a deployed agent.

## Local commands

Install through the [workspace setup](../README.md#local-development), then:

```bash
uv run --isolated --locked --no-dev --package newsloom-agent newsloom-agent check-runtime
uv run --locked pytest tests/test_agent_compatibility.py tests/test_workspace.py tests/test_mcp_auth.py tests/test_mcp_http.py
uv run --locked mypy services/agent tests/test_agent_compatibility.py tests/test_workspace.py
uv build --package newsloom-agent
```

`check-runtime` imports the actual authenticated application, official A2A client/server, async
Azure Identity and MCP client without reading environment configuration or
making a service request. Its output is a content-free module count, not live
acceptance. In the model-stage checkout, `serve` starts the protected streaming
service on port 8000; it requires the original trusted configuration plus the
[model-stage inputs](#runtime-and-owning-app-inputs).
Missing model/telemetry configuration fails startup rather than silently
falling back to the earlier non-generative runtime. Package-only startup is part of
the [primary check](../scripts/check.sh).

## Deployment boundary

Do not deploy the compatibility probe or expose an unauthenticated placeholder.
The SDK itself is not the agent authorization/privacy boundary: its default
executor can log and return exception text. The delegated runtime must protect
all enabled routes and sanitize failures before it is ready for deployment.

The existing ACA environment and Foundry account remain authoritative. No
Foundry project is selected in the VS Code extension; that does not authorize
creating one or replacing retained azd state. Owning previews, consent and cost
approval are required before cloud mutations. The actual signed-in OBO gate
must pass before model-backed expansion. Local SDK streaming is not that gate
and does not establish real Foundry streaming or user preservation.

## Separate audiences and private callers

The [shared verifier](../packages/newsloom-core/src/newsloom_core/auth.py)
owns only trusted-key refresh, signature/issuer/audience/lifetime validation and
typed claims. Its optional `auth` dependency is requested by MCP and the agent,
not required by base core. Existing MCP claims and the
[MCP adapter](../services/mcp/src/newsloom_mcp/auth.py) retain their previous
scope behavior: `news.read` is the only accepted delegated MCP permission.
`news.agent` is not an alternate MCP permission.

The agent's full delegated scope is `api://<agent-api-client-id>/news.agent`.
The PKCE request, static card, token verifier, registration inventory and consent
all use that exact scope, with no legacy alias. The Terraform output key
`AGENT_INVOKE_SCOPE` is unchanged; its value uses `/news.agent`. This rename
preceded agent registration/deployment and made no Azure changes.

The [agent policy](../services/agent/src/newsloom_agent/auth.py) requires its own
audience and `news.agent`, plus verified tenant, object, subject and authorized
client claims. App-identity markers and ID-token nonce claims are rejected.
Missing/invalid authorization returns 401, insufficient delegated scope returns
403, and trusted-key availability or authentication deadline failures return a
safe 503 category. No upstream error body is returned.

The authentication wrapper guards every HTTP method/path by default; only GET
of the static agent card and `/health/live` bypasses it. WebSockets are refused.
Authorization-only tests use a downstream operation spy. The serving tests
also exercise real HTTP, official A2A clients and the actual delegated
adapters against local identity/MCP transports. No deployed tool/model
invocation is claimed.

Verified caller assertions and identity values are kept only in private,
immutable request objects with representations suppressed. Authorization
carries the original 120-second deadline capped by incoming token expiry.
Future request stages must consume it rather than start a new budget. Compare
users privately by `(tenant, object_id)`; subjects can differ across audiences.
Never put the caller, assertion, claims or a token fingerprint into diagnostics.

The locally signed
[authorization tests](../tests/test_agent_auth.py) cover two-user concurrency,
cross-audience/scope denial, missing/wrong claims, signatures, algorithms,
caller-directed key URLs, bounded key refresh, key-response failures, token size,
expiry, duplicate headers, public-route exceptions and content canaries.
The unchanged MCP authentication/HTTP/privacy regressions pass. These are local
tests, not Entra consent, actual federation, OBO or live user-preservation proof.

Focused checks for this extraction:

```bash
uv run --locked pytest tests/test_agent_auth.py tests/test_agent_compatibility.py tests/test_mcp_auth.py tests/test_mcp_http.py tests/test_mcp_privacy.py tests/test_mcp_verification.py tests/test_workspace.py
uv run --locked mypy
uv run --locked ruff check .
uv run --locked ruff format --check .
```

The observed extraction run passed 111 tests; four database-dependent MCP
verification tests were skipped because no explicit PostgreSQL helper was
started. All 102 typed source files passed. Isolated no-dev core without auth
extras, agent, MCP and ingestion startup passed. This is not the later complete
local gate, which must include the database tests.

## Opt-in owning agent identity layer

The [identity layer](../infra/agent-identity/main.tf) has its own retained
`newsloom/<environment>-agent-identity.tfstate` key. Its providers remain
AzureRM **5.10.0** and AzureAD **3.10.0**, without shared-provider upgrades.
The [azd layer](../azure.yaml) depends on the existing application and MCP
identity outputs, not the MCP application/build hook. The shared four-workload
identity set is unchanged.

The layer owns one new user-assigned identity, a single-tenant v2 middle-tier
API exposing only `news.agent`, and a separate public acceptance client.
The client's only callback is **`http://127.0.0.1:8400/callback`**; the explicit
browser PKCE helper is described below. The API
requests only the existing MCP delegated `news.read` scope, not an application
permission. The API's sole federation binds the configured tenant's exact
v2 issuer, the new identity's principal/object ID (not its client ID) and
`api://AzureADTokenExchange`. It is not GitHub OIDC federation.

Azure grants are limited to `AcrPull` on the existing registry, `Monitoring
Metrics Publisher` on the existing Application Insights component, and a custom
chat-completions-only data action on the existing Foundry account. The layer
creates no database role, embedding/screening authority, management permission,
model, app, job or shared resource.

`AGENT_ENABLED` and **separate** `AGENT_CONSENT_ENABLED` both default to false.
The latter controls two exact tenant-wide **delegated** grants: agent API to
MCP `news.read`, and acceptance client to agent API `news.agent`. They are
not application grants, do not bypass signed-in-user verification, and require
explicit review/consent approval. Configuration alone is not OBO evidence.
Do not disable either setting after delivery as a casual rollback: identity
destruction is prevented, and existing consent cannot be silently removed by
the preparer. App ingress/revision rollback belongs to its owning app task.

### Read-only inventory and permissions

The [preparer](../services/platform/src/newsloom_platform/agent_identity.py)
is also the layer's preprovision hook:

```bash
uv run --locked newsloom-platform prepare-agent-identity
```

With the default disabled flag it makes no Azure calls and fills private azd
inputs with disabled/empty values. When enabled, it only inventories directory
objects and writes ignored retained-environment inputs; it never creates an
app, grants consent or changes Azure resources.

The existing MCP API/public client must already be explicitly configured.
They are read and validated, not updated. Existing agent registrations may be
adopted only by explicit `AGENT_API_CLIENT_ID` / `AGENT_PUBLIC_CLIENT_ID`.
Display-name discovery detects collisions; it never selects an app. Adoption
requires exact contracts, no credentials/app roles or extra redirect surfaces,
same-tenant enabled principals, the signed-in operator as the sole app owner,
exact federation and exact existing consent. Different/shared ownership,
extra scopes/federations or user-specific/broader grants stop for review
instead of being normalized or overwritten. An existing managed identity must
already be owned by this retained layer; an untracked collision needs a reviewed
state-adoption decision, not recreation or automatic takeover.

Before any enabled preview/apply, privately verify:

- The signed-in operator can read these exact apps, principals, owners,
  federation and consent, create/own the new registrations, and manage the
  new managed identity in the existing resource group.
- The provider's directory and delegated-consent permissions are actually
  available. Its [consent resource documentation](https://registry.terraform.io/providers/hashicorp/azuread/3.10.0/docs/resources/service_principal_delegated_permission_grant)
  documents elevated directory authority; do not grant broad roles to work
  around a missing permission. Separate administrator review is required.
- Azure RBAC permits the exact custom role/three narrow assignments. The
  agent workload itself receives none of the operator's management authority.
- Exact retained resource IDs, current production baselines, cost and
  native target-layer previews have been reviewed under task 3.1.

After approval, use only owning target-layer commands through retained azd;
never run `terraform apply` or an unqualified all-layer update. In particular,
shared-source changes can otherwise trigger an unintended MCP rebuild.
The enabled identity preview and approved identity-only provisioning are recorded
below. The app and actual Azure OBO exchange remain unverified.

### Initial read-only cloud preflight

After the complete local gate, exact registration inventory confirmed the
existing MCP contract and no existing agent API/acceptance registrations.
Private baseline files retain the 17 existing resources, five immutable
app/job configurations, two schedules and three unchanged configured model
deployments. No cloud resource, grant, image or environment setting was changed.
This is a baseline for a later comparison, not completed preservation acceptance.

The retained chat deployment is `gpt-5.4-mini`, version `2026-03-17`,
`DataZoneStandard`, capacity 10. Its regional quota inventory showed 110 of
1000 allocation units used across the subscription/region; that is not a
measurement of live throughput or unused request-rate capacity. No new model
allocation or inference was requested.

The operator has Azure `Owner`, but the initially observed active directory roles
did not establish tenant-wide delegated-consent authority. Tenant policy permits ordinary
app registration; that does **not** imply consent-administrator authority.
An authorized Entra administrator must review the two exact delegated grants
before the consent gate is approved. Do not add broad roles or work around it
with credentials, app-only access or a modified MCP policy.
The pinned AzureAD 3.10.0
[grant resource documentation](https://registry.terraform.io/providers/hashicorp/azuread/3.10.0/docs/resources/service_principal_delegated_permission_grant)
specifies `Global Administrator` for its user-authenticated execution path.
Microsoft's [portal consent documentation](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/grant-admin-consent)
allows narrower administrator roles for these custom delegated APIs, but that
does not verify the Terraform path with such a role. Use an existing authorized
administrator under the organization's process; do not assign a broad role as
a workaround. A separate portal-consent/adoption execution path would need
explicit review before replacing the approved azd-managed grant step.

The public [Azure retail price API](https://prices.azure.com/api/retail/prices)
returned France Central consumption rates. For one 0.25-vCPU/0.5-GiB replica
over 730 hours, the marginal compute estimate is **USD 5.91/month if idle**
or **USD 19.71/month continuously active**, before shared free grants, taxes,
telemetry, egress and ACR build charges. Requests are USD 0.40/million before
applicable free grants. This non-generative stage makes no model calls; later
token usage needs its own estimate before the model stage.

Task 3.1 remains unchecked: administrator review, native enabled owning
previews, remaining data/API/capacity checks and explicit mutation approval
are still required. No build, consent or provisioning is authorized by these
read-only observations.

### Enabled identity-only preview

After the operator activated their existing PIM role, a fresh read-only Graph
membership check verified active `Global Administrator` under the same operator
and retained environment. No directory role was assigned by this workflow.
Exact MCP inventory still matched, and neither new agent registration nor a
colliding agent managed identity existed.

Only ignored local azd inputs were prepared with `AGENT_ENABLED=true` and
`AGENT_CONSENT_ENABLED=true`. These flags enabled the **preview**, not consent
or provisioning. The native `azd provision agent-identity --preview --no-prompt`
succeeded: **13 additions, zero changes, zero deletions**.

Independent inspection of the generated native plan established:

- Two separate single-tenant apps and their service principals, owned solely by
  the unchanged operator, with the exact IPv4 PKCE callback.
- Only `news.agent` on the new API and delegated `news.read` on the existing MCP;
  two exact tenant-wide delegated grants, not application permissions.
- The separate managed identity, exact same-tenant issuer/exchange audience and
  principal-bound federation.
- Only registry pull, authenticated telemetry and chat-completions authority at
  their owning retained scopes; no database or MCP application authority.

The 13 additions comprise two app registrations, two service principals, one
API identifier URI, one federation, two delegated grants, one managed identity,
one custom chat role and three narrow RBAC assignments. No app, image build,
model allocation or existing MCP/shared-resource modification is in this plan.
Private evidence retains the plan fingerprint and exact review.

An independent post-preview readback still found **17 resources**, no new agent
managed identity and exact matches for all five retained app/job configurations.
No other service's build hook ran. The owning preview itself did not run the
complete global check hook; the full primary gate is run explicitly rather than
inferred from preview success. Owned local preview helpers were stopped.

Identity/consent apply requires explicit approval of this exact scope. The app
image build, app-only preview/provisioning and actual signed-in OBO remain later
gates; task 3.1 is not complete merely because its identity preview passed.

### Approved identity-only provisioning and independent readback

The operator explicitly approved the reviewed identity provisioning and its two
tenant-wide delegated consents. Native `azd provision agent-identity --no-prompt`
completed with **13 additions, zero changes, zero deletions**. No app, image build
or model call was included.

Independent directory/ARM reads verified the two separate registrations and
principals, exact callback and `news.agent` contract, the principal-bound
federation, both exact delegated consents, the managed identity and exactly three
narrow role assignments. The custom role contains only chat-completions data
access. The original four-workload identity map and MCP/pipeline inputs are
unchanged. Post-apply reads exactly matched all five retained workload
configurations, both schedules and all three existing model deployments.
The resource group now has 18 resources, adding only the new managed identity.

The first independent readback exposed a local verifier defect: Azure's identity
list returned the same ARM path with `resourcegroups` casing, while Terraform's
output used `resourceGroups`. All actual federation fields matched. A failing
local reproduction was added before fixing the resource-path comparison to use
case-insensitive ARM semantics; foreign/malformed paths still fail, and tenant,
principal, issuer, audience and permission checks are unchanged. The focused
identity/MCP/operator regression selection passed **186 tests**, and strict
typing for 115 files plus focused lint/format passed.

After retaining the independently verified registration/adoption inputs, a fresh
native identity-only preview passed with **no pending managed-resource changes**.
Private receipts retain exact plan/readback fingerprints and the initial failed
readback. This is verified identity setup, **not** live user-preserving OBO or
agent acceptance. Task 3.1 still requires the remaining preflight and separately
approved immutable build/app-only deployment; task 3.2 still blocks model work.

### Local identity evidence

[Inventory tests](../tests/test_agent_identity.py) exercise actual preparation
logic with read-only local Azure CLI responses, including new versus explicitly
adopted registrations, forbidden identity reuse, wrong/foreign IDs, sole-owner
checks, credential/redirect/scope/federation/consent mismatches and content-free
receipts. The existing MCP inventory tests are unchanged.

The [15 mocked-provider cases](../infra/agent-identity/tests/identity.tftest.hcl)
pass, covering disabled/no-resource behavior, separate consent opt-in, exact
federation and delegated scopes, narrow grants, invalid IDs/callbacks/adoption
and foreign tenant/resource/MCP permission refusals. Terraform validation and
recursive formatting pass. The combined runtime, identity and platform-control
selection passed **419 tests**, with four explicit database-dependent skips;
all **109 typed files** and workspace lint/format passed. See the
[subsequent complete gate](#complete-offline-pre-cloud-gate) for database-backed
task 2.3 evidence; these are not Azure permission or live OBO proofs.

```bash
terraform -chdir=infra/agent-identity init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/agent-identity validate
terraform -chdir=infra/agent-identity test
uv run --locked pytest tests/test_agent_identity.py tests/test_mcp_identity.py tests/test_platform_contracts.py tests/test_platform_control.py
```

## Request-local delegation adapter

The [delegated adapter](../services/agent/src/newsloom_agent/delegation.py)
accepts trusted tenant/API/resource configuration, the shared agent workload
credential and a trusted-key client. It accepts no request-selected authority,
resource, endpoint, tool name or alternative credential.

For each authorized request it:

1. Asynchronously obtains an MI assertion for
   `api://AzureADTokenExchange/.default`.
2. Requires enough assertion lifetime for the entire remaining request plus a
   30-second margin, then creates a fresh async `OnBehalfOfCredential`.
   Its synchronous callback only checks time and returns the prefetched string;
   it performs no network I/O.
3. Requests only `api://<existing-mcp-api-client-id>/.default` from the fixed
   public-cloud tenant authority. The owning consent must contain only
   `news.read`; actual consent and federation are still unverified.
4. Signature-verifies the downstream token with trusted tenant keys, requiring
   the MCP audience, exactly `news.read`, the middle-tier authorized client and
   matching private tenant/object identity. Subjects need not match.
5. Creates an owned HTTPX2 client and native MCP session, initializes the
   protocol and calls exactly `get_recent_news(limit=1)`. It returns typed news
   and a safe user-preservation comparison, never either token.

The shared MI credential may be reused; user assertions, OBO credentials,
downstream tokens, headers, MCP clients and results are not shared across
requests. All stages consume the original deadline and incoming authorization
lifetime, additionally capped by the exchanged token's signed/provider expiry.
OBO and MCP clients close on success, failure, timeout and cancellation.

The current MCP SDK requires **HTTPX2**, not the separate HTTPX used for JWKS and
A2A. That already-locked dependency is now explicit in the agent manifest.
Its default client also follows some same-origin redirects regardless of the
HTTP client's setting. The adapter therefore rejects all redirects, checks the
exact configured HTTPS `/mcp` URL and authorization channel before each send,
disables environment proxy/auth configuration and bounds response bytes to
128 KiB, including JSON and SSE. It does not start an OAuth-interaction fallback.
The existing MCP endpoint is stateless; no persistent client session is retained
or network termination request sent after its authorization budget ends.

A small `ClientSession` override validates the fixed
[recent-news DTO](../services/agent/src/newsloom_agent/models.py), not
server-selected JSON Schemas or remote references. It neither lists/selects
tools dynamically nor fetches news URLs. Extra/malformed results or more than
one item fail; an empty item tuple is explicit absence, not an error fallback.
Generation, direct PostgreSQL access and operator/app-only MCP access do not
exist in this adapter.

### Local adapter evidence

[The SDK transport tests](../tests/test_agent_delegation.py) run the real async
Azure Identity OBO credential against a local transport, inspecting its actual
OAuth request/callback and closure. The real MCP client exchanges protocol
frames with the local MCP server over in-memory HTTP transports. This is not
an Azure federation test or a claim of live OBO.

The 54 adapter tests passed with exact safe categories for invalid-grant and
interaction-required consent, malformed exchange responses, wrong
signature-bound identities/resources/permissions, MCP denial and malformed
results, two-user concurrency, no reuse after prior success, response-byte
boundaries, empty versus failed news, rejected redirects, deadline/expiry and
cancellation cleanup. Some malformed identity responses are surfaced by the
actual SDK as `ClientAuthenticationError`, hence the safe `exchange_denied`
category rather than a raw response diagnostic.

The combined agent/MCP/workspace regression selection passed 166 tests with
the same four explicitly database-dependent skips. Strict typing passed for
104 source files, and workspace lint/format checks passed. Regression tests
also established explicit refusal of non-string SDK access tokens and a finite
request budget even for a signed, extremely distant expiry; neither reaches an
unhandled type/overflow failure.

Success emits only item count and a user-preservation boolean. Dependency logs
go through the existing content-free handler; canaries in news, credentials and
provider errors are absent from emitted diagnostics. This is not the later
framework/model/authenticated-telemetry acceptance gate.

```bash
uv run --locked pytest tests/test_agent_delegation.py
uv run --isolated --locked --no-dev --package newsloom-agent newsloom-agent check-runtime
uv build --package newsloom-agent
```

## Non-generative authenticated A2A application

The [application](../services/agent/src/newsloom_agent/app.py) is an injectable
ASGI factory, not an unauthenticated placeholder or an operator credential
shortcut. The managed-identity-only runtime and owning image are described
below. The only supported input is one `text/plain` part
containing `recent-news`, optionally surrounded by whitespace. Other requests,
files, URL/data parts, references, required extensions, push configurations,
detached execution and alternative output formats fail before OBO admission.
Request metadata cannot supply executor/provider keyword arguments.

The static public card describes exactly one stored-news read and advertises
**no streaming, generation or research**. It documents the separate Entra
authorization-code/PKCE scope and the A2A 1.0 JSON-RPC HTTPS interface. Only
loopback test servers may use HTTP. Invocation requires `application/json`
and `A2A-Version: 1.0`; legacy 0.3 is not enabled. Host validation and a
default-deny browser-origin policy apply. No debug/Inspector bypass is exposed;
the Foundry Inspector's Responses-API workflow is not an implemented transport.

An admitted request invokes the real `A2AExecutor` with a fresh request-local
Agent Framework provider, session and delegated read. Successful nonempty
output is structured JSON text with `outcome: news`, the actual MCP DTO and
`user_preserved: true`; zero items instead yields `outcome: empty`. Denied or
unavailable dependencies yield a failed task with an application-controlled
category, never a completed empty/model-only answer. The event boundary
replaces the executor's raw exception message before it reaches task state.
Runtime logs must use the existing content-free logging handler.

### Enabled task operations and finite profile

[Task handling](../services/agent/src/newsloom_agent/serving.py) keeps only
transient caller-owned records, without credentials or SDK call contexts.
The context builder passes only a fixed protocol-version header to the SDK;
incoming bearer/identity headers never enter its state. Credential-bearing
request context variables reset on exit; expiry timers have an empty context.

| Limit | Enforced local boundary |
| --- | --- |
| Request body | 65,536 bytes, counted while receiving, including chunked input |
| Input text | 16,384 UTF-8 bytes |
| Active private requests | Four, including auth/body/task operations; excess returns 429 |
| Retained tasks | 64; no active-task eviction to admit more work |
| Task retention | At most 300 seconds from admission; idle timers remove state |
| End-to-end duration | 120 seconds from ingress, capped by verified caller expiry |
| Generated output | None at this stage; the later proposed limit is 512 tokens |

`SendMessage` waits for the result and returns a server-generated task/context.
`GetTask` reads owned state with history length 0-10.
`ListTasks` provides owned metadata-only pages (default 50, maximum 64), with
owned cursor/context checks. It rejects unsupported history/artifact/status
filter options instead of silently ignoring them. This allows a non-streaming
client to find and cancel its in-flight request. `CancelTask` cancels the actual
producer and waits for cleanup under the original deadline before returning
canceled state. It cannot cancel completed tasks.

An owned context may be referenced for another independent one-read request;
it does not restore model history. Task continuation is explicitly unsupported.
Foreign/unknown task/context/cursor references are unavailable, never authority.
Streaming/subscription, extended cards and push operations are explicitly
unsupported and do not start providers. Restart/expiry returns not-found, with
no replay. Public liveness/discovery do not consume private-request capacity.

Body receipt, authentication, execution and cancellation share the original
budget. HTTP disconnect cancels and awaits the request producer, including
real OBO/MCP resource cleanup. Canceled, timed-out and interrupted work cannot
become completed output. Shutdown cancels producers and removes transient state.

### Local serving evidence

[Serving tests](../tests/test_agent_serving.py) verify real loopback HTTP
discovery/invocation and official-client task read/list/cancel, including actual
Azure Identity/MCP SDK transport cleanup during exchange and tool I/O. They
also cover two interleaved users, foreign/unknown references, pagination,
unsupported methods/inputs/configurations, exact byte/text/concurrency/task/TTL
and deadline boundaries, idle expiry without retained authorization, restart,
real socket disconnect, caller expiry, slow bodies, safe failures and content
canaries. These transports are local, not live Entra or Azure acceptance.

The combined agent/MCP/workspace selection passed **237 tests**, with four
explicit PostgreSQL-dependent skips. Strict typing passed for **107 files**;
workspace Ruff lint/format passed. See the
[subsequent complete gate](#complete-offline-pre-cloud-gate) for the full
database-backed checks. Authenticated automatic-telemetry/model privacy
acceptance remains a later task.

```bash
uv run --locked pytest tests/test_agent_serving.py tests/test_agent_auth.py tests/test_agent_delegation.py tests/test_agent_compatibility.py tests/test_mcp_auth.py tests/test_mcp_http.py tests/test_mcp_privacy.py tests/test_mcp_verification.py tests/test_workspace.py
uv run --locked mypy
uv run --locked ruff check .
uv run --locked ruff format --check .
```

## Owning app, immutable image and operator commands

The [app layer](../infra/agent/main.tf) owns only the new agent app in
`newsloom/<environment>-agent.tfstate`. Its azd dependencies are the existing
application, MCP identity and new agent identity layers, not ingestion,
enrichment, migrations or MCP app hooks. It defaults to disabled. The enabled
profile is one always-on Consumption replica, maximum one, 0.25 CPU/0.5 GiB,
one unprivileged process, HTTPS ingress and explicit startup/liveness/readiness
probes. Readiness means process readiness, **not** successful federation or OBO.
Browser origins default to none; the native acceptance client needs no CORS grant.

The [Dockerfile](../services/agent/Dockerfile) installs only the locked agent
package and runtime dependencies, with no development dependencies, database
client, credential fallback or Inspector endpoint. The
[runtime](../services/agent/src/newsloom_agent/runtime.py) uses only the
explicit user-assigned `ManagedIdentityCredential`. It requires:

| Trusted input | Purpose |
| --- | --- |
| `AGENT_TENANT_ID` | Fixed single-tenant authority |
| `AGENT_API_CLIENT_ID` | Separate agent audience/middle tier |
| `AZURE_CLIENT_ID` | Agent workload identity only |
| `MCP_API_CLIENT_ID`, `MCP_RESOURCE_URL` | Existing audience and canonical HTTPS `/mcp` |
| `AGENT_RESOURCE_URL` | Canonical HTTPS `/a2a`, derived from the retained ACA environment |
| `AGENT_RUNTIME_REVISION` | Immutable image input/source hash for operator readback |

Runtime configuration, registration IDs and layer outputs stay in ignored azd
configuration. The runtime accepts only explicit HTTPS origins if configured;
the current azd layer deliberately uses its empty default.
No database, model endpoint or user credential is injected into this temporary
non-generative app.

The [operator helper](../services/platform/src/newsloom_platform/agent_control.py)
separates **build**, **preview preparation** and **read-only verification**:

```bash
# Only after task 3.1 inventory and approval of the build/cloud changes:
uv run --locked newsloom-platform build-agent
uv run --locked newsloom-platform prepare-agent-layer
azd provision agent --preview
# Review that exact app-only preview and obtain approval before applying:
azd provision agent
uv run --locked newsloom-platform verify-agent
```

`build-agent` is an explicit Azure mutation: it builds only `newsloom-agent`,
then retains its immutable digest and matching `AGENT_IMAGE_REVISION`.
The `agent` preprovision hook **does not build**: it refuses an absent/mutable
image, missing identity output or source-hash mismatch. Thus a native
`azd provision agent --preview` cannot trigger an ACR build or another service's
build hook. For identity changes use only
`azd provision agent-identity --preview`, then its approved owning apply.
Never use an unqualified all-layer update, `azd up` or direct Terraform apply
for this slice. Required identity creation/consent precedes the app, so review
the first deployment in stages; do not invent a digest to obtain an app preview.

`verify-agent` independently reads the exact ARM app and checks the sole assigned
identity and its client/principal, immutable image, source revision, complete
trusted environment, ingress/FQDN, ready revision, registry authentication,
resources, scale and all three probes. Its receipt contains only comparisons
and the source hash. It is not a signed-in invocation, permission exercise or
live OBO receipt.

### Failure, disable and compatible rollback

A failed build or source/configuration check stops before app provisioning;
do not rebuild MCP, widen consent or substitute an operator token. Keep the
previous agent digest, matching source hash and verified runtime source revision
privately before an update.

For an approved emergency disable, remove **only the owning app**:

```bash
azd env set AGENT_ENABLED false
azd provision agent --preview
# Proceed only if this removes the agent app and nothing else:
azd provision agent
```

Do **not** provision `agent-identity` or another layer with that disabled flag.
The app-only operation retains registrations, consent, its managed identity,
shared resources, models, schedules and stored data. Do not run `azd down`.

To restore a previously verified image, first safely preserve local work and
use its matching verified runtime source with the **same retained azd
environment/backend**, not newly initialized infrastructure. Set
`AGENT_ENABLED=true`, `AGENT_IMAGE` to that previous immutable agent digest and
`AGENT_IMAGE_REVISION` to its matching input hash. Run `prepare-agent-layer`,
review `azd provision agent --preview`, apply only that layer after approval,
then rerun `verify-agent` and signed-in acceptance. A mismatched checkout/hash
is intentionally refused; do not bypass that check. These commands are
documented recovery paths, not a claim of a live rollback drill.

## Explicit signed-in acceptance client

The [client](../services/agent/src/newsloom_agent/client.py) is an operator
acceptance tool, not a production UI. After the approved deployment and consent,
run it with the ignored retained environment's values:

```bash
uv run --env-file ".azure/<retained-environment>/.env" --locked --no-dev \
  --package newsloom-agent newsloom-agent verify-delegation
```

Replace the quoted environment placeholder with the existing environment name.
In addition to the runtime's tenant/API/MCP/resource inputs, the client requires
`AGENT_PUBLIC_CLIENT_ID` for the separate PKCE registration; it does not use
the workload managed identity or an operator access token.

The command explicitly opens the browser for account selection using S256 PKCE
and unpredictable state. Only IPv4 loopback port 8400 and the exact callback
path/host are accepted. Port conflict, invalid callback/state, browser failure
and timeout fail explicitly and close the listener. Sign-in is bounded to
180 seconds; token responses to 32 KiB. No secret, offline scope, refresh-token
acceptance, persistent token cache or identity-dump endpoint is used.

The client verifies the access-token signature/audience and public-client claim,
discovers the static card without a bearer, validates its endpoint/protocol/
security contract, observes missing/invalid agent-auth and agent-token-to-MCP
audience denials, then invokes and reads the result through the official A2A
client. Its authorized transport permits only POST to the exact configured agent
URL and refuses redirects. The one explicit wrong-audience negative probe is
not a production MCP access path.

Positive acceptance requires one actual news item and the server's privately
verified same-user comparison. Empty news or failed delegation cannot produce
a success receipt. Output contains only item/comparison/denial/task-read counts;
no article text, tokens, claims or raw provider errors. This tool does not yet
exercise every live forbidden-workload case required by task 3.2.

### Local app/client evidence

The agent container was built locally with Podman, imported its six runtime
modules without development dependencies, and ran as UID/GID 65532. Seven live
container checks established liveness, truthful non-streaming discovery,
anonymous denial, wrong-host/origin denial, no server header and non-root
configuration. Its process/container were stopped afterward; no Azure call
or model invocation was made.

The combined [client](../tests/test_agent_client.py),
[runtime](../tests/test_agent_runtime.py), [operator](../tests/test_agent_control.py)
and existing platform-control selection passed **105 tests**. These include
actual loopback cleanup, local SDK A2A/OBO/MCP success versus empty/denied results,
PKCE/token/privacy failure paths, source-bound preparation/rollback, app-only
disable and drift refusal. All **115 typed files**, workspace lint and the
app layer's **10 mocked-provider cases** passed. These are local evidence, not
real browser/Entra sign-in, Azure readiness or live rollback proof.

### Complete offline pre-cloud gate

Task 2.3 passed the complete `bash scripts/check.sh` with an explicitly owned,
loopback-only PostgreSQL 18/pgvector helper: **941 tests passed** and only the
intentional live-publisher test was skipped. All database regressions ran.
The gate also passed lint/format, strict typing for **115 files**, isolated
package startup, feed/identifier validation, **11 strict OpenSpec items**,
validation of all **10 Terraform roots** and **66 mocked-provider cases**.
`uv build --all-packages` built all six wheels and source distributions.
The database helper was stopped and the owned local agent test image removed.

The first full attempt had **940 passing tests and one failure** in the
unchanged ingestion concurrency timing test: five feeds completed, but its
20-ms overlap observed three concurrent fetches instead of the expected four.
Two focused repeats and then the complete unmodified gate passed. The initial
failure receipt is retained privately; no ingestion implementation/test,
assertion, sleep or retry configuration was changed to obtain the pass.
This does not claim that the timing-sensitive test has been repaired.

No Azure provisioning, consent, ACR build, real sign-in/OBO or model call is
part of this gate. Task 3.1's private inventory, cost/permission review and
approved owning previews are next; group 4 stays blocked by actual task 3.2.

After the scope rename to `news.agent`, the focused agent/auth/delegation/client/
serving/identity and existing MCP regression selection passed **363 tests**.
Strict typing for **115 files**, workspace lint/format, **15 identity-layer
mocked-provider cases**, identifiers and all **11 OpenSpec items** passed.
Negative tests reject the former scope in caller tokens, registration adoption
and consent adoption.

Before requesting approval of the enabled identity preview, the subsequent
complete `bash scripts/check.sh` also passed after renaming: **944 tests passed**,
with only the intentional live-publisher test skipped. All database regressions,
115 typed files, lint/format, isolated startup, identifiers, 11 OpenSpec items,
10 Terraform roots and 66 mocked-provider cases passed. All six wheel/source
package builds passed again. The explicitly owned PostgreSQL helper was stopped.

### Approved image build and app-only preview

After separate approval for the agent-only ACR build and app preview, the
immutable `newsloom-agent` image built successfully in the retained registry.
Independent digest lookup and local source hashing matched:

| Binding | Value |
| --- | --- |
| Image input revision | `7e0d878812d82725e40f4a2f435e80b039f7084ebfa955f7aa4767d8e754434f` |
| Image digest | `sha256:a6d182fd21131c4451cfee59a2d04545d3bfd12a76ea675e5b127a53ce805edb` |

Native `azd provision agent --preview --no-prompt` passed with **one addition,
zero changes, zero deletions**. Independent plan inspection verified the retained
ACA environment, exact new identity, immutable image/source binding, one
0.25-CPU/0.5-GiB Consumption replica (maximum one), HTTPS ingress, all three
probes, empty browser origins and only the fixed non-generative runtime inputs.
The plan contains no database/model configuration or other service update.
No app apply was approved or executed.

Fresh read-only inventory still exactly matched all five existing workloads.
The retained chat catalog explicitly advertises chat completions for the pinned
model/version; regional DataZoneStandard allocation remains 110 of 1000 units.
These are compatibility/quota inventory, not actual inference or permission
exercise. A fresh count-only production data baseline remains required before
app deployment; prior Phase 1 counts are not presented as current observations.

The first full local attempt after the ARM-path fix did **not pass**:
**947 tests passed, one failed, one intentional live-publisher skip**.
The unchanged ingestion concurrency timing test again completed all five feeds
but observed only three overlapping fetches during its 20-ms sleep instead of
four. No assertion, test or ingestion runtime was altered to bypass that failure.
The earlier 944-test full pass and later 186-test focused pass remain separate
receipts, not substitutes for this failed latest attempt. The owned PostgreSQL
helper was stopped. Deployment was paused pending an explicit decision about a
deterministic test-only correction and another complete local gate.

### Approved deterministic local-test correction

With explicit test-only approval, the existing
[ingestion concurrency test](../tests/test_ingestion_database.py) now holds the
first four feed workers at an event before database I/O, rather than estimating
overlap with a 20-ms sleep. The entire run has a ten-second timeout. The exact
five-completed, maximum-four-active and zero-active-after-cleanup assertions
remain; production ingestion behavior is unchanged.

Verification after this correction:

- Four consecutive focused runs passed; all 22 ingestion database tests passed.
- A temporary in-process five-worker mutation failed the unchanged maximum-four
  assertion, demonstrating that synchronization does not conceal excess workers.
  No production file was mutated.
- The complete `bash scripts/check.sh` passed against an explicitly owned local
  PostgreSQL 18/pgvector instance: **948 tests passed, one intentional
  live-publisher skip**. Types passed for 115 source files; lint, format, isolated
  package startup, identifiers, strict specs and owning Terraform checks passed.
- `uv build --all-packages` built all six workspace wheels and source
  distributions. The local PostgreSQL helper was stopped and its removal verified.
- The image-input hash still equals the reviewed revision above. The test-only
  change requires no agent image rebuild.

The earlier failed attempts remain evidence, not passing receipts. This clears
the local blocker only. Separate approval for app provisioning and actual
signed-in OBO acceptance are still pending. Tasks 3.1 and 3.2 remain unchecked.

### Approved fresh production baseline and refreshed preview

With separate approval, exactly one execution of the existing migration job ran
only `enrichment-status`, not migrations or enrichment. Independent ARM readback
confirmed its successful execution, exact arguments and unchanged job definition,
identity and immutable image. Its correlated count-only receipt reports:

| Observation | Count |
| --- | --- |
| News / completed queue rows | 1,981 / 1,981 |
| Pending / processing | 0 / 0 |
| Failed queue rows | 1 |
| Retained dead letters / rejected records | 9 / 23 |
| Invalid vectors, completion mismatches, completed without news | 0 each |
| Duplicate URLs, duplicate source/GUIDs, published rejections | 0 each |

The failed queue row is an observed baseline condition, not a successful queue
outcome; it was not retried or modified. The status operation uses a read-only,
repeatable-read transaction with a 15-second statement timeout and emits no news
content.

The refreshed native agent-only preview again passed with **one addition,
zero changes, zero deletions**. Its complete planned app configuration and
unknown-value shape exactly match the earlier reviewed preview. The current
plan fingerprint is
`97c1f1dd38c1c0d529fb6fd71074798a472f407d88cd40c403022b4a5ba550c6`.
The immutable digest was independently found in the retained ACR again, and the
source-input hash still matches. No app apply has been approved or executed.

### Approved agent-only deployment and actual readback

After separate app-only cost/provisioning approval, native
`azd provision agent --no-prompt` completed with **one added, zero changed,
zero destroyed**. Independent ARM comparison confirmed all five existing
workloads' identities, images, configuration and schedules, plus all three
existing model deployments, were exactly unchanged. The resource count rose
from 18 to 19, adding only the approved agent app.

The first operator readback failed because the app ID and assigned-identity map
key used different casing for equivalent ARM paths. Five new local reproductions
failed before correcting the owning verifier to compare complete ARM paths
case-insensitively. It still rejects foreign/suffixed paths, duplicate identity
aliases and every original principal, image, configuration and probe mismatch;
UUIDs, permissions and other fields are not relaxed.

After that operator-only correction:

- All 135 related identity/control tests passed. The complete primary check
  passed **966 tests with one intentional live-publisher skip**, including types
  for 115 source files, lint/format, isolated startup, identifiers, strict specs
  and Terraform checks. All six workspace wheels/source distributions built.
  The explicitly owned PostgreSQL helper was stopped and its removal verified.
- Actual `verify-agent` passed for the sole assigned identity, immutable image,
  exact trusted runtime inputs, HTTPS/registry settings, one small Consumption
  replica, three probes and the ready revision.
- Actual HTTPS liveness returned 200. Official A2A discovery matched the
  non-generative recent-news contract, PKCE and `news.agent` scope. Missing and
  invalid authorization each returned 401. No signed-in invocation or model
  call was made.

The deployed image remains the approved digest and input revision recorded
above (`7e0d8788...`). The later local operator-only fix and README status updates
change the repository-wide input hash; they do not change agent runtime code or
replace the deployed image. These are distinct source states, not a claim that
the image matches the later checkout.
The source-binding guard remains enabled: a future app preview/update requires
an explicitly approved build matching its checkout. No additional build or app
update has been performed for this operator fix.

Task 3.1 is verified. Task 3.2 remains unchecked: real browser PKCE, user-preserving
OBO/MCP access and the remaining actual workload denials are still unverified.
Model-backed group 4 stays blocked.

### First actual browser attempt: sign-in incomplete

After explicit readiness approval, the real `verify-delegation` command started
its IPv4 loopback callback listener and browser sign-in. It exited with the safe
category `browser_sign_in_unavailable` before the client could invoke A2A/OBO.
The listener on port 8400 was confirmed closed afterward. That category alone
does not distinguish a callback timeout from an unavailable sign-in HTTP
dependency; browser/operator observations are needed before another attempt.
No token or authorization code is retained in the receipt.

This is a failed live sign-in attempt, not delegated-access acceptance. Task 3.2
remains unchecked, all model work remains blocked, and no alternate credential,
audience or data path was used.

### Windows-browser retry: actual user-preserving OBO passed

The operator observed no browser from WSL's default Python launcher (`gio`).
An explicitly process-local Windows launcher, without changing application
code, consent or redirect URIs, completed real browser sign-in and immediate
delegated A2A access successfully. For this WSL environment, the tested command
is:

```bash
uv run --env-file ".azure/<retained-environment>/.env" --locked --no-dev \
  --package newsloom-agent python - <<'PY'
import sys
import webbrowser
from newsloom_agent.cli import main

browser = webbrowser.GenericBrowser([
    "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
    "Start-Process -FilePath '%s' -ErrorAction Stop",
])
webbrowser.register("windows-desktop", None, browser, preferred=True)
sys.argv = ["newsloom-agent", "verify-delegation"]
main()
PY
```

Only the client's generated trusted Entra authorization URL is handed to the
desktop browser. PKCE/state, the exact loopback callback, token validation,
memory-only credentials and the original bounded request behavior remain
unchanged. The callback listener was confirmed closed after success.

The actual client receipt reports **one real news item, one verified
user-preservation comparison, two agent-authorization denials, one
agent-token-to-MCP audience denial and one successful task read**. This proves
the deployed identity's secretless exchange and a real existing-MCP response;
it is not a local mock, operator-token forwarding or application-only read.
No article text, tokens, assertions or raw user identifiers are in the receipt.
No model call ran.

At this point task 3.2 was still incomplete: the agent's actual nondelegated MCP
and scoped workload denials remained to be exercised. Group 4 stayed blocked
until those required live checks also passed.

The operator approved the remaining bounded live permission-denial probes but
explicitly deferred their execution until returning the following day. No checks
were scheduled or run during that pause.

### Resumed live denial checks: delegation gate complete

On 2026-10-27 the operator resumed the approved checks. The deployed agent's
exact image, sole managed identity and ready revision passed independent
verification before and after the probes. Bounded execution used the existing
non-root agent container, not a new job, another workload or an operator bearer.
Tokens came only from its explicitly selected managed identity; tenant,
principal and client bindings were compared privately.

| Actual operation under the agent identity | Observed refusal |
| --- | --- |
| MCP `tools/list` with a nondelegated token | HTTP 403 |
| Existing embeddings deployment | HTTP 401 |
| Existing screening deployment | HTTP 401 |
| Existing chat deployment's Responses API | HTTP 401 |
| Foundry account management read | HTTP 403 |
| Foundry account key-list operation | HTTP 403 |
| PostgreSQL login using the agent identity's name | SQLSTATE `28P01` |
| PostgreSQL login as the existing MCP database role | SQLSTATE `28000` |
| PostgreSQL login as the existing administrator role | SQLSTATE `28000` |

The six HTTP probes accepted only 401/403 as denial and did not read response
bodies. The database probe used verified TLS and the actual server's SCRAM
negotiation, presenting the managed-identity token as the authentication
credential. It accepted only authentication-refusal SQLSTATEs and sent **zero
SQL queries**. The first auth-only attempt stopped on unsupported SCRAM before
the session-only probe gained that support; it was not counted as a denial
receipt. No dependency was installed in the container.

All nine required refusals passed. No inference succeeded, no data operation
ran, and no credentials, article text, response bodies or raw upstream errors
were exported. Private evidence retains safe statuses/comparisons and the probe
source fingerprint. The earlier real browser receipt separately establishes
successful user-preserving OBO/MCP access; these denials are not substitutes for
that positive proof.

Independent post-probe comparisons confirmed the agent definition/identity and
all five pre-existing workloads' identities, images, configuration and schedules
were unchanged, as were all three model deployments. The retained resource set
remains exactly 19. No role, consent, model capacity, job or resource changed.

Task 3.2 is now verified: **9/15 tasks complete**. Group 4's identity prerequisite
is satisfied, but model integration, streaming, final telemetry, subsequent
deployment/acceptance and publication remain pending. The last full local gate
is still the separate 966-pass/one-intentional-skip receipt above; no application
code changed during these live checks.

## Model stage: bounded generation and private telemetry

The completed live delegation gate allowed local work on tasks 4.1 and 4.2.
This section describes the model-stage implementation. Its separately approved
agent-only build/update is now deployed with independent readiness/configuration
verification; see the [deployment receipt](#approved-model-stage-build-and-deployment).
The earlier non-generative receipts remain historical evidence. The
[actual model-stage acceptance](#actual-model-stage-azure-acceptance) below
separately verifies signed-in Foundry streaming and telemetry ingestion.

### Fixed model path and A2A behavior

The [generator](../services/agent/src/newsloom_agent/generation.py) uses the
official Agent Framework `OpenAIChatCompletionClient`, not its Responses client,
over the existing Foundry-compatible `/openai/v1/chat/completions` endpoint.
Its explicit async OpenAI/HTTPX2 client uses the agent's managed identity for
`https://cognitiveservices.azure.com/.default`. It has zero retries, no tools,
no stored conversation, no proxy/environment credential discovery and no
redirect following. Incoming user/delegated tokens never enter that client or
the model messages. Caller metadata cannot override its options.

One successful delegated `get_recent_news(limit=1)` read supplies bounded,
typed metadata. Fixed developer instructions and untrusted news JSON are
separate messages. Nonempty news permits one generation with an actual wire
`max_completion_tokens=512`; an empty read emits an explicit no-news artifact
with zero generation calls. Failed OBO/MCP access cannot generate an answer.
This establishes a bounded demonstrator, not research or evaluated injection/
citation quality; those remain in [later capabilities](prd-2-capabilities.md).

The model stage adds a 32 KiB news-JSON input ceiling, a 16 KiB UTF-8 output
ceiling and a 128 KiB model-response wire ceiling to the existing
[request profile](#enabled-task-operations-and-finite-profile). The stream
also bounds provider updates. A finished response must include a normal stop,
nonempty output and observed usage within the output-token bound.
Refusals, tool calls, length stops, missing finish/usage, malformed data,
shared-quota HTTP 429 and partial-stream failures remain failures.

`SendStreamingMessage` forwards genuine model text as append updates on one
artifact. Its eight-event channel applies backpressure. `SendMessage` buffers
the same bounded generation and returns the completed task. Completion carries
a content-free receipt with outcome, item count, user-preservation comparison,
generation-call count and observed output tokens; artifacts contain the answer.
Partial artifacts can be retrieved, but a failed/cancelled task is never a
completed answer. Ownership, metadata-only listing and unsupported methods
remain unchanged.

The HTTP boundary alone reads the real disconnect channel and shares that
signal with the SSE listener. Authenticated requests track their own producer
tasks: disconnect cleanup does not depend on the SDK closing nested generators.
All provider work consumes the original request/authorization deadline.

### Runtime and owning app inputs

The [agent app layer](../infra/agent/main.tfvars.json) adds only:

| Runtime environment field | Existing owning output |
| --- | --- |
| `MODEL_ENDPOINT` | `MODEL_ENDPOINT` |
| `AGENT_CHAT_DEPLOYMENT` | `ENRICHMENT_DEPLOYMENT` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Existing authenticated telemetry routing |

These are trusted deployment inputs, not caller/model selections. The runtime
requires them; there is no new model, capacity, grant, database connection,
identity, job or schedule. The [operator verifier](../services/platform/src/newsloom_platform/agent_control.py)
expects this exact new configuration after the model-stage update; its previous
non-generative readback receipt remains historical evidence, not verification
of this checkout. Only a newly source-bound agent image can deploy this change.

The existing small one-replica profile remains unchanged. The model price review
and separately approved immutable build/app-only preview/update are recorded
below. Actual inference still requires a separately approved acceptance budget.

### Authenticated, content-free telemetry

The [agent telemetry](../services/agent/src/newsloom_agent/telemetry.py) exports
through explicit managed-identity Azure Monitor exporters, with offline storage
disabled. It records only fixed operation/surface/outcome/category labels,
duration, generation-call counts and **observed** input/output-token counts.
Missing usage on failure is marked unobserved, not presented as measured zero
cost. HTTP transport outcomes and execution outcomes are separate, so HTTP 200
carrying a failed A2A task is not reported as successful execution.

Agent Framework instrumentation is explicitly and stickily disabled, including
automatic attempts to enable sensitive-data capture. The trace exporter also
rebuilds every dependency span through a
[shared core privacy helper](../packages/newsloom-core/src/newsloom_core/telemetry.py):
fixed name/resource, validated allowlisted attributes, no events, links,
status descriptions, instrumentation scope or tracestate. MCP uses that same
helper with its existing field policy; it is not imported as an agent server
dependency and its deployed image has not changed.
Console dependency messages still pass through core's content-free handler.

Application Insights ingestion is delayed; the live receipt below verifies it
for this deployed revision. Local exporters and canaries do not substitute for
that Azure evidence.

### Explicit streaming acceptance client

After approval of the inference budget for this deployed revision, the same
deliberate PKCE sign-in flow supports:

```bash
uv run --env-file .azure/dev/.env --locked --no-dev --package newsloom-agent \
  newsloom-agent verify-streaming
```

This command deliberately permits one real generation, verifies streaming-card
parity, the two agent auth refusals and cross-audience MCP refusal, actual
artifact events, completed task/readback parity, one item, user preservation
and bounded observed output tokens. It emits safe counts only. Do not run it
without an approved inference budget. The earlier `verify-delegation` command
remains for the earlier non-generative profile and refuses a streaming-card
mismatch rather than silently generating.

The [WSL Windows-browser workaround](#windows-browser-retry-actual-user-preserving-obo-passed)
still applies; select `verify-streaming` instead of `verify-delegation`.
Tokens, model prompts/answers and callback data remain memory-only.

### Local model-stage evidence

[Generation tests](../tests/test_agent_generation.py) exercise the real pinned
connector and A2A SDK with local MCP/model transports. They prove an artifact
arrives over real loopback HTTP before generation finishes, exact input/output
byte and 512-token bounds, zero retries, no tool/endpoint authority, empty news,
dependency/refusal/partial failures, original deadlines, cancellation and closed
resources. Deterministic blocked-consumer tests establish the exact channel
backpressure threshold.

[Privacy tests](../tests/test_agent_privacy.py) run actual HTTP success,
OBO/MCP/model failure, invalid downstream expiry, overload and disconnect.
They also deliberately force sensitive framework instrumentation back on:
actual automatic SDK spans are observed before sanitization, and news, prompt,
completion, token, assertion, request-ID, exception and synthetic span canaries
are absent from exported spans, metrics and console output.
The [acceptance-client tests](../tests/test_agent_client.py) cover both truthful
profiles without contacting Azure.

The first complete primary gate exposed a regression in the existing MCP
automatic-span privacy test: direct generator use could enable default framework
instrumentation, and a temporary agent-test provider could become cached by the
MCP SDK. The generator now disables capture at its own boundary as well as at
application startup; temporary test tracers are isolated without changing the
existing MCP privacy assertions. The combined generator/agent-privacy/MCP-privacy
regression run passed **37 tests**.

The corrected `bash scripts/check.sh` passed **1,012 tests with one intentional
live-publisher skip**, strict types for **120 Python files**, lint/format,
isolated no-dev imports, configuration/identifier/OpenSpec checks and all
mocked Terraform suites, including **13 agent app cases**. `uv build
--all-packages` built all six workspace distributions and wheels. The explicitly
owned loopback PostgreSQL 18/pgvector helper was stopped and removed; its port
was verified closed.

These results verify tasks 4.1 and 4.2 and the local prerequisites of 4.3.
The following receipt completes 4.3; local canaries do not complete 4.4.

### Approved model-stage build and deployment

On 2026-10-27, read-only preflight confirmed the retained France Central
`gpt-5.4-mini` version `2026-03-17`, `DataZoneStandard`, capacity 10 and
chat-completions support. No model or capacity change was requested.
The public [Azure retail pricing API](https://prices.azure.com/api/retail/prices)
returned these exact non-batch, non-priority France Central Data Zone meters:

| Meter | USD per million tokens |
| --- | ---: |
| `5.4 mini Inp Dz` | 0.825 |
| `5.4 mini cd Inp Dz` | 0.0825 |
| `5.4 mini Opt Dz` | 4.95 |

These are Azure Data Zone prices, not Global Standard or direct OpenAI prices.
At those rates, 1,000 uncached input tokens plus the full 512 output-token
allowance cost approximately **USD 0.00336**. A 65,536-input/512-output example
costs **USD 0.05660**; observed-usage validation is not a prepaid billing cap.
Actual agreement prices, usage and taxes may differ. No inference was run
during this build/deployment step.

The operator separately approved one agent-only ACR build and native app-only
preview, then approved the exact preview before apply:

```bash
AZURE_DEV_USER_AGENT=microsoft_foundry_skill uv run --locked newsloom-platform build-agent
AZURE_DEV_USER_AGENT=microsoft_foundry_skill uv run --locked newsloom-platform prepare-agent-layer
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd provision agent --preview --no-prompt
# Only after approval of this exact preview:
AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd provision agent --no-prompt
AZURE_DEV_USER_AGENT=microsoft_foundry_skill uv run --locked newsloom-platform verify-agent
```

The successful Linux/amd64 build used two vCPUs for approximately 52.427 seconds
with a 900-second timeout. The retail `Task vCPU Duration` meter is zero for its
first 6,000 shared-tier seconds, then USD 0.0001 per vCPU-second. Without assuming
unused free allocation, this build represents approximately **USD 0.01049** of
compute, excluding image storage and any agreement adjustments.

| Runtime provenance | Verified value |
| --- | --- |
| Build-input/source hash | `4e3290d2d03a2e9fb6fc340c39529c439383fc210cd1fef99bf518bcd1b1e2a9` |
| Immutable image digest | `sha256:3330932020ffdbd758298ea7a649989687427a704dceb0b02b519e5c1ad763d6` |
| Native preview | 0 add, 1 in-place agent change, 0 destroy |
| Native apply | 0 added, 1 changed, 0 destroyed |

The source hash binds the build input before this later status-documentation
update; it is not a Git SHA or a claim that subsequent documentation has the
same input hash. The existing corrected primary-gate and all-six-package build
receipts above remain the local evidence; native provisioning is not claimed
to have rerun that complete gate.

Only the agent image/source and the three documented runtime inputs changed.
The first immediate operator readback correctly failed while the new revision
was still activating and the previous revision remained ready. No predicate
was weakened: subsequent ARM readback found the new revision ready, its one
container running, zero restarts and the full exact image/environment/identity/
ingress/registry/probe/resource/scale configuration matching. The pinned
eight-module local runtime import check used about 130 MiB peak RSS; that is not
a loaded-service memory measurement or full generation acceptance.

Actual public HTTP checks passed: liveness 200, streaming card 200 with one
skill, and missing/invalid authorization both 401. Independent pre/post
comparisons found exactly the same 19 resources, five existing workload
definitions/identities/schedules and three model configurations/capacities.
MCP was not rebuilt or redeployed; no identity or grant layer was applied.
Private receipts retain the original failed readback, successful retry,
preview/apply, source/digest, configuration and preservation comparisons.

This deployment receipt verified task 4.3 at **12/15 tasks complete**, without
running inference. The following separately approved acceptance completes 4.4.

### Actual model-stage Azure acceptance

On 2026-10-27, the operator approved at most two model-backed A2A requests,
512 generated tokens and 120 seconds per request, plus read-only workload,
telemetry and stored-record verification. One count-only execution of the
existing migration job was used, not a migration or enrichment run.
No image, infrastructure, registration, consent, grant, model or capacity was
changed during acceptance. The runtime provenance remains the
[approved deployment's source hash and digest](#approved-model-stage-build-and-deployment),
not the later status-documentation input hash.

The first sign-in attempt ended with `browser_sign_in_unavailable` before any
agent/model request. Its listener closed. After explicit approval to reopen,
the Windows browser PKCE flow completed; credentials remained memory-only and
the callback listener closed again after acceptance.

| Actual signed-in case | Measured result |
| --- | --- |
| Discovery/schema/security parity | Pinned A2A client accepted the streaming card and separate `news.agent` contract |
| Missing/invalid agent authorization | Two HTTP 401 responses |
| Agent-audience token sent to MCP | Refused before tool access |
| Completed request | One delegated item, verified same-user comparison, one real Foundry generation |
| A2A output | 93 artifact events; completed task/artifact readback matched |
| Model usage | 282 observed input tokens, 96 observed output tokens |
| Completed client duration | Approximately 3.291 seconds |
| Cancellation | Acknowledged after model output began; 28 observed artifact events/153 bytes |
| Cancellation client duration | Approximately 0.901 seconds; retained task cancelled, never completed |

The completed answer's cited URL matched an independently read stored URL by
in-memory comparison. Read-only SQL snapshots under the existing MCP database
identity bracketed the A2A requests: both had **2,078 news records**, the same
selected record/URL fingerprints and an identical full stored-news metadata
fingerprint. News, prompts, answers, tokens, user identifiers and URLs were not
written to receipts. This operator verification is not a database path or
credential fallback available to the agent.

Actual authenticated Azure ingestion contained both execution outcomes. The
completed span reported one generation and 282/96 token usage; cancellation
reported one generation with usage absent, not a measured zero cost.
At the reviewed retail rates, the completed request's observed tokens represent
approximately **USD 0.00070785**, excluding cancelled/unobserved usage and other
charges.
All **36** returned execution/dependency spans had the rebuilt fixed name and
only allowlisted fields plus Azure's `_MS.ResourceAttributeId` reference.
Success/cancellation counters and usage-observation metrics were ingested with
only operation/outcome/category dimensions; input/output usage metrics existed
for success, not fabricated cancellation usage. The six actual agent console
records were structured and exposed only the existing safe diagnostic schema.
Application Insights local authentication remained disabled. These live
schema/ingestion checks complement, rather than replace, the hostile
automatic-instrumentation canaries verified locally.

Final probes under the deployed agent identity again observed:

| Forbidden operation | Actual refusal |
| --- | --- |
| Nondelegated MCP | HTTP 403 |
| Embeddings, screening and Responses API | HTTP 401 each |
| Foundry management read and key listing | HTTP 403 each |
| PostgreSQL login as agent identity | SQLSTATE `28P01` |
| PostgreSQL login as MCP/admin role | SQLSTATE `28000` each |

HTTP denial probes read no response bodies; the three database-denial probes
sent zero SQL queries. Independent read-only operator SQL is reported separately.
Readback matched the agent's original three narrow grants, unchanged chat-only
role permissions, registrations, exact federation and both delegated consents.
All four Phase 1 workload grants matched the retained owning grant contracts.
Exactly **19** resources remained; all five existing workload images,
identities, templates/schedules and all three model configurations/capacities
were unchanged. The exact deployed agent revision remained healthy.

The count-only job's actual execution arguments were independently verified as
`enrichment-status`. Its result was **2,078 completed/news**, pending/processing/
failed zero, **10 dead letters** and **24 rejections**. Invalid vectors,
completion mismatches, completed-without-news, duplicate URLs/GUIDs and published
rejections were all zero.
An initial comparison with the older 2026-10-26 baseline failed: that earlier
snapshot had 1,981 news, one failed item, nine dead letters and 23 rejections.
Rather than overwrite that evidence or alter history, count-only pipeline
summaries at 11:00 UTC established the current values **before** the 11:25 UTC
A2A requests. Those pre-invocation values matched the final readback; stored-news
fingerprints also matched across the actual requests. Active scheduled production
data was not incorrectly treated as frozen overnight.

Private evidence retains the failed sign-in, initial operator-probe/input
mistakes, older-baseline comparison, corrected actual results and final
16-gate receipt. No model retry beyond the two approved successful/cancelled
requests was made; no data was restored, rewritten or deleted. No owned listener
or remote probe remains running.

This live receipt verified task 4.4 at **13/15 tasks complete**.
The following publication receipt records subsequent delivery gates.
Full research, phase-wide quality evaluations and browser UI remain later slices.

## Verified implementation publication

On 2026-10-27, after local and actual Azure acceptance, the verified
implementation was committed and pushed as
[`1b8d4af01fd9a88d880d654c0d984bcdebed5c1f`](https://github.com/ikhemissi/newsloom/commit/1b8d4af01fd9a88d880d654c0d984bcdebed5c1f).
Its primary
[CI run 40500304977](https://github.com/ikhemissi/newsloom/actions/runs/40500304977)
completed successfully for that exact SHA. The required contributor trailer
is present. Unrelated prompt deletions/new customization skills, ignored
environment/state and private operator evidence were excluded.

Immediately before publication, the complete `bash scripts/check.sh` gate
passed again with the disposable loopback PostgreSQL service:

| Check | Actual result |
| --- | --- |
| Ruff lint/format | Passed; 204 files formatted |
| Strict types | 120 source files passed |
| Local tests | 1,012 passed, one intentional live-publisher skip; 144.28 seconds |
| CI tests | 1,012 passed, the same intentional skip; 38.35 seconds |
| Isolated package startup | Agent, enrichment and MCP checks passed |
| Catalogue, identifier and strict OpenSpec guards | Passed; 11 OpenSpec items |
| Terraform | All ten owning layers validated and mocked-provider suites passed |
| Workspace builds | All six packages produced source archives and wheels |
| Owned local PostgreSQL | Stopped/removed; loopback port closed |

CI is offline runtime/regression evidence, not another Azure acceptance run.
Publication caused no deployment, grant or model invocation. Runtime provenance
remains source-input hash
`4e3290d2d03a2e9fb6fc340c39529c439383fc210cd1fef99bf518bcd1b1e2a9`
and image digest
`sha256:3330932020ffdbd758298ea7a649989687427a704dceb0b02b519e5c1ad763d6`.
The hash binds the original build input, including its then-current README;
it is not a Git SHA or a claim that later status-only documentation has the
same conservative build-input hash. The immutable deployed code was not rebuilt
to reconcile documentation.

This implementation-publication receipt verified task 5.1 at **14/15 tasks
complete**. The following separate receipt closes 5.2 only after its own
exact-head CI passed.

## Verified evidence/status delivery

The separate documentation-only evidence/status receipt was committed and
pushed as
[`58afd2132d85f11531ee64dde11f20c70a5abd6f`](https://github.com/ikhemissi/newsloom/commit/58afd2132d85f11531ee64dde11f20c70a5abd6f).
Its primary
[CI run 40501029431](https://github.com/ikhemissi/newsloom/actions/runs/40501029431)
completed successfully for that exact SHA **before task 5.2 was checked**.
It updates this runbook, phase/capability/ADR status, README and checklist;
the production source, deployed configuration and runtime digest are unchanged.
Local receipt checks passed all 118 local links/anchors, 16 shell blocks,
identifier hygiene and all 11 strict OpenSpec items.

Task 5.2 is verified: **15/15 tasks complete**. Step 2.1's A2A and secretless
delegation slice is delivered, not a complete research agent or Phase 2.
Full research, frozen quality evaluations and the browser UI remain pending.
Archival was separately approved after the closure receipt passed CI, as
recorded below. Closure/status-only heads require their own exact-head
CI before publication is reported complete and do not replace runtime or
implementation provenance.

## Verified skeleton archival

The final delivery closure
[`8bf48bedc48d9a0298233b229a0b2c4930d97f69`](https://github.com/ikhemissi/newsloom/commit/8bf48bedc48d9a0298233b229a0b2c4930d97f69)
passed its own
[exact-head CI](https://github.com/ikhemissi/newsloom/actions/runs/40501562347).
On 2026-10-27, the operator then approved synchronizing the delivered specs.
Both purposes and all 13 requirement blocks matched their accepted delta
verbatim; all 12 main specs passed strict validation before moving the change.
The [archive](../openspec/changes/archive/2026-10-27-agent-skeleton/tasks.md#verified-archival)
retains all 15 checked tasks and links to the original acceptance evidence.
No runtime, environment/state, grant, model, schedule or stored data was changed;
no additional inference was performed.
