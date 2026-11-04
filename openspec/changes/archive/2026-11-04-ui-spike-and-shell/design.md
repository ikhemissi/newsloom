# Design

## Context

See [proposal](proposal.md) for motivation and approved scope. The browser journey
is new; the research pipeline is not.

Observed integration constraints:

- `services/agent/.../app.py` checks Origin but supplies neither preflight nor
  CORS response headers. Its JSON-RPC boundary requires A2A version `1.0`,
  JSON content, and no extensions; its deadline is 120 seconds.
- `serving.py` accepts one research data part and enforces one final text part.
  Progress is structured JSON inside status-message text. Research delivers a
  validated answer, not draft token streaming.
- `research_models.py` bounds questions at 8192 UTF-8 bytes; `research.py` renders
  the fixed stored-summary limitation followed by numbered URL paragraphs.
- `newsloom_platform/agent_control.py` currently verifies
  `AGENT_ALLOWED_ORIGINS` as an empty string. Terraform already has the origin
  input; preparation, validation and independent readback must agree.
- `azure.yaml` has owning identity/app layers but no UI. The root npm package
  owns OpenSpec only, and `scripts/check.sh` has no frontend gates.
- npm metadata confirms the handoff's A2A SDK 1.3.0 and MCP client 2.4.0 exist.
  The A2A README describes protocol 1.0, JSON-RPC, interceptors and streaming.
  This is not proof of our strict wire contract or browser authentication.

## Goals / Non-Goals

**Goals:** Ship one deployed page with stable sign-in, usable research, safe
citations and explicit failures; keep additions limited to that path.

**Non-Goals:** No feed adapter, MCP dependency, catalogue cache, pagination,
structured artifact, new research model, inference proxy or saved conversation.
Do not scaffold the handoff's entire future directory tree.

## Decisions

### 1. Plain React and official A2A, not a translation runtime

Create `services/web` as a root npm workspace with Vite, strict TypeScript,
React 19, Tailwind 4 and daisyUI 5. Use a simple Material-inspired light/dark
theme, system fonts and native controls. Only a theme preference can persist.
No router or query library is necessary for the initial chat page and callback.
Add native History routing when feed/item routes arrive.

Keep a typed `ResearchClient` between components and SDK transport, with small
request/progress/answer/failure types and Zod validation. SDK imports stay in
the data adapter. Use native fetch and AbortController through supported SDK
hooks, not a hand-written JSON-RPC/SSE replacement.

Record a short ADR comparison against CopilotKit/AG-UI: the existing backend is
A2A, so a separate bridge/runtime adds authority and deployment surfaces without
improving this journey. This is a scoped choice, not a claim those products
universally require or cannot support a particular runtime.

The compatibility check is capped at 45 minutes of active investigation and
must test exact request headers/body, discovery, stream framing, cancellation
and GetTask mapping against the current server contract. Use a local strict
transport fixture first and the eventual stable Azure UI for live proof.
Do not repeat CLI sign-in/calibration experiments or silently introduce a proxy
if SDK compatibility fails; surface the concrete incompatibility.

### 2. One browser resource token, unchanged OBO

Provision a separate single-tenant SPA registration with an exact HTTPS UI
callback, authorization-code/PKCE and delegated `news.agent` only. MSAL owns
initialization and redirect handling once. The user approved MSAL-managed
sessionStorage for tab-scoped authorization after live sign-in proved that MSAL
5 explicitly rejects redirect flows with memoryStorage. No exported tokens,
localStorage credential cache or saved browser storage-state; questions and
answers remain in memory only. Auth tests include a real-SDK browser regression.

Acquire a token before sending a question. Interaction-required sign-in is a
visible redirect, not a hidden retry. Do not persist or automatically resend
the question across redirects. Clear the in-memory thread on sign-out; describe
independent requests rather than imply conversational memory.

Token injection is confined to the exact configured agent interface. Discovery
uses an unauthenticated fetch and validates endpoint, JSON-RPC version, streaming,
input/output modes and agent scope before authorized traffic. Do not send bearer
tokens to a card-selected host or follow authenticated cross-host redirects.

Direct browser MCP later needs its own delegated `news.read` consent, per-audience
token, CORS and client compatibility work. None is added speculatively now.

### 3. Add CORS outside existing admission/auth boundaries

Use the existing HTTPS origin input, shared strict parsing/serialization and
an outer CORS layer. Permit discovery GET and `/a2a` POST, including task
operations carried by JSON-RPC. Allow Authorization, Content-Type, A2A-Version
and Accept only; no cookies, extensions, wildcard reflection or credentials.

Recognized allowed-origin OPTIONS requests return before auth/capacity admission.
Use a fixed max age of 300 seconds; vary preflight on Origin and requested
method/headers. Reject unsupported origins/paths/methods/headers explicitly.
Actual response headers cover success, authorization errors, overload, timeout
and SSE startup. Preserve headers and behavior for clients without Origin.

Update agent preparation and independent ARM readback to compare the normalized
expected origins, not to ignore that field or merely trust HTTP health. Add
focused origin/readback tests alongside the existing client-preservation tests.

### 4. Only completed validated text becomes an answer

Submit exactly one JSON data part with `operation: research`, a trimmed,
nonblank question and the server's existing default filters/preferences.
Accept text/plain output only, A2A-Version 1.0, and no extension header.
Test 8192-byte input acceptance and excess-byte rejection using UTF-8, not
JavaScript string length.

Map the known progress phases without rendering arbitrary server status text.
Accumulate the one text artifact and validate successful terminal state before
displaying success. Deployed acceptance separately checks exact same-caller
GetTask parity; normal successful requests need no extra readback roundtrip.
Failure or a truncated stream stays an explicit failure.
Never replay SendStreamingMessage automatically on auth/network errors; bounded
read-only reconciliation of a known task does not authorize a new generation.

Bound the request to 120 seconds, final artifact to the server's 16 KiB serving
limit and aggregate raw stream input to 1 MiB. Enforce transport byte bounds
before unbounded SDK buffering and test exact-boundary behavior. Stop closes
the stream and uses same-caller cancellation when a task ID is known; a failed
cancellation receipt is not confirmation that backend execution stopped.

Parse only the existing trailing numbered URL paragraphs as citations, validating
numbers, duplicates and reference membership. Preserve all other paragraphs,
unknown text and limitations inertly. Invalid citation structures fail explicitly;
unsafe links stay nonclickable. Do not infer an outcome badge or invent article
titles/source names absent from the text contract.

Use a reusable HTTPS-only, credential-free link guard. React text nodes render
all content; no markdown/HTML renderer. Keyboard citation controls focus the
corresponding reference; external links show their hostname and use noopener/
noreferrer. Structured metadata is a later separately compatible change.

### 5. Immutable static UI on the retained ACA environment

Add `infra/ui-identity` and `infra/ui`, plus narrowly scoped platform preparation,
build and readback helpers following the existing owning-layer pattern.
Use the existing ACR and ACA environment, a new UI workload identity with only
scoped registry pull, an immutable image, HTTPS ingress and a nonroot static
server. Start with Consumption, 0.25 CPU/0.5 GiB, min replicas zero/max one;
review cold-start behavior and scoped cost before apply.

Derive the stable UI hostname from the retained environment default domain and
deterministic app name before provisioning the SPA registration. Validate it
against eventual app readback. This avoids an identity/app dependency cycle,
temporary redirect URI or placeholder deployment.

Serve `/config.json` as validated deployment-generated public JSON with no-store,
containing tenant, SPA client, agent URL and scope only. Keep actual identifiers
in ignored azd inputs/runtime configuration, not source or build-time bundles.
Serve immutable hashed assets; avoid caching HTML/config across revisions.
Azure's readback can omit the configured zero minimum-replica value; admit only
omitted/zero for this min-zero profile, with max one still checked exactly.

Use CSP restricted to self, the approved Entra endpoints and agent origin,
plus no-referrer, nosniff and framing restrictions. Self-host all assets.
Disable raw static-server access/query logs and prohibit content-bearing error
logs. Verify startup/configuration and headers with canaries.
No SWA token exception, separate hosting region, linked API or inference access.

## Risks / Trade-offs

- SDK convenience helpers may emit unwanted headers or replay a POST -> Exact
  wire tests and scoped hooks; fail rather than weaken the deployed contract.
- Text parsing lacks structured outcome/title metadata -> Preserve the current
  footer contract, show numeric/host labels, and defer richer metadata.
- Authorization redirects can lose an unsent question -> Explain the transition;
  do not save private questions or transparently replay them.
- Scale-to-zero introduces cold starts -> Show loading/errors honestly and
  measure the deployed journey before adjusting the reviewed replica profile.
- The handoff's timestamp-only paging can omit tied items -> Address that in
  the later feed proposal; do not claim complete pagination from this slice.
- Browser diagnostics can capture content/tokens -> No live HAR, traces,
  screenshots, console body dumps or saved authentication state; metadata only.
- Early-access sequencing can be mistaken for acceptance -> Keep PRD-2's ledger
  intact and full PRD-3 tests/remaining capabilities visibly pending.
- The baseline verifier pins the root manifest bytes -> The user approved a
  second exact production-input set for the uv UI exclusion. Retain the original
  set and return the actual matched set's digest, never normalize new bytes to
  the historical digest. Existing frozen provenance must reject current-source
  drift; no approval schema, receipt, budget, journal or inference changes.
  Keep the small manifest verifier and self-contained tests independent of the
  parked baseline implementation so UI publication need not stage that work.

## Migration Plan

1. In implementation, update the owning phase/capability documents and ADRs with
   the approved narrow sequencing exception and stack; do not complete evaluations.
2. Implement and locally test frontend, CORS, identity/app layers and readback.
   Run the primary check before any deployment; record the unchanged baseline.
3. Read only scoped existing registration/resource metadata, preserve exact IDs,
   and review the UI identity/app and agent-only plans. Existing models, MCP,
   schedules, evaluation grants/reports and data must remain unchanged.
4. Provision SPA identity for the derived UI origin, build immutable UI/agent
   images, deploy the owning CORS agent update and UI app, and verify exact
   image/configuration/origin/permission readback using retained azd state.
5. With the user ready in the deployed browser, verify real sign-in, progress,
   answer/task parity, citation navigation, stop/error handling and accessibility.
   Account observed model estimates separately from hosting and unknown costs.
6. Commit only this slice after local/Azure checks; obtain exact-source CI,
   then publish measured status separately. No automatic archival of either
   existing active change or incomplete phase gates.

Rollback retains the prior immutable agent/UI image/configuration and Terraform
state. Withdraw the UI origin through the owning agent layer if disabling the
UI; account for the bounded preflight cache. Do not replace the retained
environment, delete unrelated consent or reset evaluation history.
