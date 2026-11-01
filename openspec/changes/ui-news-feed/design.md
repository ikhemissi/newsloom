# Design

## Context

See [proposal](proposal.md) for motivation and scope. The existing React/MSAL/
A2A UI works after its redirect-cache correction; the user attested successful
sign-in and a cited answer. Its formal automated browser evidence and
implementation/status publication are not yet complete.

Observed surfaces:

- `services/web/src/App.tsx` renders research as the main signed-in page.
  AuthSession and ResearchClient currently cover only the agent.
- MCP `RecentInput` supports `limit` 1-50 and optional `since`; NewsResults
  contains items with `id`, `title`, `summary`, `source`, `category`, `tags`,
  `published_at` and `url`. Retrieval has no embedding/generation requirement.
- MCP `SearchInput` accepts a nonblank query of 1-2048 characters and a 1-50
  limit; `search_news` preserves semantic relevance ranking and uses existing
  query embeddings. It does not call the research agent.
- `services/mcp/.../app.py` enables host/origin transport security and exposes
  stateless Streamable HTTP, but supplies no browser CORS layer.
- MCP Terraform has `allowed_origins`; native `main.tfvars.json` does not bind
  it. Runtime parsing silently filters empty list entries. Owning normalization
  and independent ARM image/origin readback need deliberate wiring.
- The SPA has only agent `news.agent`; UI runtime configuration and CSP currently
  contain only the agent endpoint. Direct MCP needs its own scope/origin.
- The current image source hash misses root npm manifest/lock inputs consumed by
  the UI Dockerfile. Resolve this tightly coupled build-input binding in the
  first UI's publication follow-up, retaining historical image/source receipts.

## Goals / Non-Goals

**Goals:** One news-first landing page with a top MCP search form, a closable
right-hand A2A panel and one visible selected-item research context.

**Non-Goals:** No full feed framework, filter UI, detail page, pagination,
multi-select, polling, persistent news cache or conversational memory.
Do not build the handoff's complete directory tree.

## Decisions

### 1. Top search, news first and optional right-hand research

Use a top navigation row with the search form and an Agent panel toggle.
Below it, use a two-column desktop layout: news content and a 380-420px right
agent panel. Closing the panel gives the news column the full available width.
The latest-news view has a heading and explicit Refresh action.
Show 20 items without `since`, retaining server order and displaying local
publication time through a labelled time element. Show actual source/category
IDs rather than fetch a second catalogue only for label enrichment.

The panel is closed initially and uses an accessible named aside with an explicit
Close button, not a desktop modal or overlay. Opening it moves focus to the
composer; closing restores focus to its opener. On narrow screens it expands
below the main content with the same controls and no horizontal clipping.
Closing hides but does not clear or replay in-memory interaction state or cancel
an active request. A busy indicator on the toggle makes ongoing work visible;
reopen to use the existing Stop action. Sign-out still stops and clears work.

"Ask about this"
sets one current item ID and inert title chip, opens the panel and focuses the
question field; it never submits a prompt. General "Ask Newsloom" opens the panel
without selection. Removing context clears the ID; freeze selection while a
request is running so displayed context cannot differ from dispatched context.
When a search/latest view is replaced, clear idle selected-item context if that
item is no longer displayed. An active question keeps its frozen visible context;
its result must not be relabelled as research about a newly selected item.
Do not infer agent context from the top search string or all 20 visible items.
This slice's context is the explicitly selected current news item.

Extend the typed ResearchClient request with optional selected item IDs and
validate the same server constraints. The UI exposes one selected item now;
do not change the backend's existing five-distinct-ID ceiling or A2A artifact.

### 2. Minimal latest/search NewsCatalog with official modern MCP

Add `recent({limit}, {signal})` and `search({query,limit}, {signal})` to the typed
NewsCatalog boundary and its McpCatalog adapter. Components never import MCP
protocol types. Use exact
`@modelcontextprotocol/client` 2.4.0 with native fetch/AbortController and Zod
at the structured-result boundary; validate UUIDs, publication times, item count,
duplicate IDs and safe display fields. Reject `isError` and malformed results
explicitly, never convert them into an empty list.

Use a native top search form with explicit submit. Editing the input never
dispatches work. Trim the submitted query, validate the server's 2048-character
bound, then call `search_news({query,limit:20})`. Preserve MCP ranking and show
"Search results - ranked by relevance", not the latest-news order.
Keep query text in transient UI state, not telemetry or URLs. Clear search or
blank submit returns to `get_recent_news({limit:20})`; the latest-news Refresh
control performs only a recent read. There is no hidden debounce, automatic
query retry, semantic refresh or pagination. A reader may explicitly resubmit.

The official [protocol-version guide](https://ts.sdk.modelcontextprotocol.io/v2/protocol-versions.html)
states the default remains legacy. Explicitly use
`versionNegotiation: {mode: {pin: "2026-07-28"}}`; no auto/legacy fallback.
Modern discovery uses `server/discover`, not `initialize`. The
[modern HTTP binding](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http.md#request-metadata)
requires MCP-Protocol-Version, Mcp-Method, and Mcp-Name for tool calls, with matching
body metadata. There are no modern protocol sessions or legacy GET streams.
The handoff's initialize/session/header examples are not assumed correct.

Cap the compatibility check at 30 minutes of active investigation. Prove pinned
discovery, `get_recent_news({limit:20})`, `search_news({query,limit:20})`,
required headers/body metadata and
cancellation against an authored instance of the current Python SDK server.
Do not weaken protocol/auth or invent SDK provider APIs if the probe fails.

Inject only an intended MCP token into the exact configured `/mcp` endpoint;
do not run the SDK's independent OAuth registration/refresh flow or send tokens
to advertised endpoints. Close the client on sign-out/unmount. One catalogue load per view
uses a finite 90-second deadline and 1 MiB aggregate response limit enforced before
unbounded buffering. Abort stale loads and guard against post-sign-out state
updates. Superseding view requests abort prior loads; guard against stale results.
Refresh and search are explicit; no background polling, retries or cross-user cache.

### 3. One account session, two audience-bound tokens

Retain MSAL's user-approved tab sessionStorage and stable redirect bridge.
AuthSession acquires a token for a trusted resource scope selected from runtime
configuration, not from news or URLs. Initial feed sign-in requests MCP
`news.read`; explicit research obtains agent `news.agent` silently where possible.
Interaction-required authorization is visible and never automatically resends
a research question.

Extend the existing SPA's `required_resource_access` and add exactly one
MCP delegated consent grant, retaining the agent grant and redirect URIs.
Inventory only exact existing agent/MCP/SPA applications and consent. If the
operator cannot create the new consent, retain partial Terraform state, obtain
the user's admin action and import the exact grant; never broaden directory roles.
Runtime `/config.json` adds validated `mcpUrl` and the existing canonical
`api://<MCP audience>/news.read` scope. Extend CSP connect-src only to that origin.

### 4. Exact MCP CORS without widening existing clients

Extract reusable exact-origin CORS mechanics from the first UI implementation
into the shared core where appropriate, with explicit per-service path/header
policies. Do not import the agent service into MCP. Preserve the agent's existing
policy and rerun its tests.

For modern browser MCP, allow POST `/mcp` and only Authorization, Content-Type,
Accept, MCP-Protocol-Version, Mcp-Method and Mcp-Name. Preflight terminates before
authentication, tool semaphore admission or data/model work. Use exact-origin
response headers, no credentialed CORS, and fixed 300-second max age with proper
Vary. Reject duplicated/unallowed origins and unsupported requests.

Normalize HTTPS origins using the existing shared helper; wire the native azd
encoded-origin input through `infra/mcp` and preparation. Add independent ARM
readback for immutable MCP image, exact origins, environment, identity and
unchanged profile rather than substituting the existing broad `verify-mcp`
workload/model probe for browser readiness.

### 5. Own and verify the smallest delta

Update owning PRD-3 assignments, ADRs and runbook during implementation.
Use the existing primary gate and frontend tests, with real-SDK contract cases
and browser checks that assert zero agent/model requests on default feed load,
refresh and merely opening research. Label authored fixtures separately from
real Azure data/identity evidence. Do not retain live traces, screenshots,
storage-state, article content or raw upstream errors.
Explicit search must dispatch only MCP semantic search and its existing bounded
embedding path, never A2A; do not misreport that intentional embedding call as
zero inference. Keep search embeddings separate from research chat accounting.

No new infrastructure/environment/model is needed. Reviewed owning deltas are
SPA MCP permission/consent, MCP image/origin, and UI image/config/CSP only.
The agent image, OBO grants and research pipeline remain unchanged.

## Risks / Trade-offs

- Direct browser MCP expands the SPA's delegated permission -> Exact consent
  review and separate tokens; no application access or shared identity.
- MCP supports only four concurrent tools -> One feed read per view, no polling,
  explicit busy state; this is not an unlimited-traffic scale claim.
- SDK defaults to legacy -> Pin modern explicitly and prove the actual wire.
- Latest 20 is not the archive -> Label the bound; no timestamp-only paging
  that silently drops ties. Cursors belong to a separate slice.
- Semantic search incurs embedding work -> Submit-only queries, existing MCP
  transport bounds and explicit resubmission; no inference while typing/browsing.
- Panel/view changes can imply stale context -> Visible removable selection,
  immutable in-flight context and no implicit search-query or whole-feed context.
- A stale selected item disappears from storage -> Preserve the agent's explicit
  missing/limited response; never substitute another item or fabricate detail.
- Extra runtime fields can break old bundles -> Deploy validated version-compatible
  UI configuration and image together; retain old immutable inputs for rollback.

## Migration Plan

1. Implement the scoped catalogue/search, right-panel research context, auth/config and MCP
   CORS, with adjacent tests/docs; run local checks before cloud work.
2. Before acceptance/publication, finish first UI's remaining actual evidence
   and selective publication gates. The user explicitly approved local
   implementation and the exact reviewed early-access rollout for regular-browser
   verification while these remain open. User sign-in takes place only in their regular browser:
   no new test-browser session or credential export. Manual attestation does
   not substitute for still-unverified automated GetTask/accessibility evidence.
3. Review exact existing SPA/MCP inventories and owning plans. Provision/adopt only
   the intended MCP consent with preserved agent grant and redirects.
4. Deploy the reviewed MCP image/origin and UI image/configuration through retained
   azd layers. Verify exact image/config/identity/CORS and no unrelated mutations.
5. Verify a signed-in browser sees real latest news with zero automatic inference,
   explicitly submits an MCP search and opens/closes the right-hand agent panel,
   then explicitly requests one item-context research answer with citations.
   Run deployed keyboard/axe and safe metadata-only checks.
6. Selectively commit this slice and verify exact-source implementation/status CI;
   keep all still-unverified phase/evaluation work open.

Rollback restores the prior owning UI/MCP image/configuration and removes only
the UI's MCP origin if withdrawing browser access. Preserve registrations,
historical reports and state; do not delete grants or undo consent casually.
