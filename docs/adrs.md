# Architecture Decision Records

| # | Decision | Why and consequences |
|---|---|---|
| 1 | **Lean, iterative delivery with OpenSpec.** One PRD per phase and small changes; acceptance follows the [OpenSpec delivery contract](../openspec/specs/repository-foundation/spec.md#requirement-honest-ordered-delivery). | Always shippable, little speculation. Cost: every change needs a deployable slice. |
| 2 | **Three apps on ACA, shared libraries.** Ingestion job, enrichment job, MCP server, then agent and UI. Shared packages for config, database, identity, telemetry, domain; repository packaging follows the [OpenSpec workspace contract](../openspec/specs/repository-foundation/spec.md#requirement-reproducible-typed-python-workspace). | Independent deploy and scale; no shared runtime identity. |
| 3 | **PostgreSQL 18 + pgvector as store and queue.** Queue operations behind a repository interface; HNSW index, cosine distance, `vector(1536)`. Initial MCP ranking applies all filters in a materialized eligible relation before exact cosine ordering; keep HNSW for later measured tuning. | One datastore to run. Exact ranking avoids selective approximate-index underfill at the current scale; finite SQL budgets bound work. A real queue (Service Bus) can replace it later without touching the units. |
| 4 | **Identity.** Users via single-tenant Entra. MCP retains delegated `news.read`, its public PKCE client, localhost callback and canonical v2 resource alias; private Copilot configuration preserves `oauthClientId`. The agent has a separate `news.agent` audience/client and exact managed-identity federation for request-scoped OBO to MCP `news.read`. Database workloads have distinct identities and migration-created roles; the agent has no database role or standing MCP access. | Secretless. MCP's warning-free VS Code/Copilot sign-in and four tools remain [verified](../openspec/changes/archive/2026-10-26-mcp-server/tasks.md#acceptance-evidence), without DCR, a proxy or weakened audiences. Actual signed-in user-preserving OBO passed before model integration; the [agent runbook](agent.md) records exact federation, consent, live evidence and denied workload access. The [MCP runbook](mcp.md) retains its own setup. |
| 5 | **Models from one Foundry (AIServices) account.** Pinned deployments: a small GPT for enrichment (today `gpt-5.4-mini`), `text-embedding-3-large` at 1536 dimensions, and `Microsoft-Decision-1` for scanning. Key access disabled; each unit gets only the inference role it needs. All behind interfaces. | Quota is shared per subscription, so capacities are variables. Models are replaceable by configuration. |
| 6 | **Content security with `Microsoft-Decision-1`.** It is a Foundry *decision* model, not a chat model: `POST <endpoint>/providers/microsoft/v1/systemone` receives a complete serialized entry as `state` and typed questions. `noul` returns a numeric score, not an explanation or demonstrated exploit probability. The [contextual follow-up](../openspec/changes/archive/2026-10-23-contextual-content-screening/design.md) asks about attempts to redirect the consuming processor, not merely the presence of AI instructions; acceptance is neither sanitization nor a safety guarantee. Thresholds use full-entry labelled calibration and separate validation, bound to policy/fixtures/model configuration. **Fail closed:** operational errors are deferred, not accepted. | Preview, `DataZoneStandard` only, 60 requests per minute in the EU zone, and **inference is deprecated on 2027-02-04**, so it sits behind `ContentSecurityScanner` for a later verified model replacement. No runtime no-op, whitelist, or bypass; fake verdicts exist only in tests. Paired evaluation gates rollout. No automatic quarantine release. |
| 7 | **Untrusted content everywhere.** Feed text is data: delimited in prompts, closed output schemas, no tools in the enrichment model, parameterized SQL, MCP serves only stored rows. | Prompt injection cannot reach tools, queries or configuration. |
| 8 | **Infrastructure.** Terraform (`azurerm`; `azuread` for owning MCP/agent registration layers; `azapi` only where missing, with a comment), azd with the Terraform provider, and the [OpenSpec state-bootstrap contract](../openspec/specs/repository-foundation/spec.md#requirement-secretless-remote-state-bootstrap). Images are built in the registry; workloads update through owning azd layers/hooks. One developer environment, kept and updated incrementally, never recreated casually. Common tags from one variable. | Same proven flow as today. Public ingress in v1; isolation is a later PRD. |
| 9 | **Observability.** OpenTelemetry, structured logs, Application Insights with Entra-only ingestion. Attribute allow-list scrubber; third-party HTTP loggers kept at WARNING. Identifiers and counts only. | Safe by construction. A log line that could carry content is a bug. |
| 10 | **Agent and UI stack.** Microsoft Agent Framework + A2A server on ACA, verified for Step 2.1's bounded recent-news demonstrator and Step 2.2's request-local stored-news research runtime. Per-turn schemas derive from frozen application-owned state; independent whole-plan validation and existing per-call guards retain authority, evidence and budget boundaries. The phase 3 spike still chooses the UI framework and UI-specific integration transport; it does not replace the A2A boundary. | Keeps phase 3 open without blocking phases 1 and 2. The [research receipt](agent.md#state-constrained-actual-acceptance) retains failed prompt-only attempts and verified local/Azure follow-up; [PRD-2](prd-2.md) owns release status. No web, persistent memory or broader grant is implied. |
| 11 | **Tests and evals follow each phase.** Local PostgreSQL container for database tests; hostile fixtures for retrieval and parsing; labelled sets for the scanner, enrichment and retrieval; frozen questions for the agent; browser end-to-end for the UI. | Phase 1 runtime gates are [verified](phase1-acceptance.md#verified-phase-acceptance-matrix), including explicit manual OIDC integration in one exact disposable database and bounded same-identity cleanup after failure/cancellation. Conditional log-only access adds no development-token/exec authority. Scanner/enrichment/retrieval quality and native-user evidence remain distinct from the four-item integration corpus. Step 2.1 transport/identity acceptance is [verified](agent.md#actual-model-stage-azure-acceptance); Step 2.2's [focused research checks](agent.md#state-constrained-actual-acceptance) do not establish a frozen phase-wide quality score. Step 2.3 must refine DeepEval plus Foundry-visible results, quality/cost governance and iterative candidate comparison; phase-wide evaluations and UI gates remain pending. |
| 12 | **Early-access UI: React/Vite/strict TypeScript, Tailwind/daisyUI, MSAL and official A2A on ACA.** Use native browser APIs and existing text citations. | The explicitly approved [sequencing exception](prd-2.md#delivery-plan) unblocks a usable browser journey, not PRD-2 quality or full PRD-3 acceptance. [Comparison](#ui-stack-comparison) explains the choice. Direct-MCP feed/search and structured citations follow separately. No SWA deployment-token exception or standing research identity. |

## UI stack comparison

ADR 12 supersedes ADR 10's pending UI selection only; its deployed agent decision
and all verified research boundaries remain unchanged.

Plain React with the official A2A client directly matches the deployed A2A 1.0
JSON-RPC progress/final-answer contract. CopilotKit/AG-UI would require evaluating
an additional integration layer for this backend; its value is not needed for
the first bounded journey. This is not a claim those frameworks universally
require a particular server runtime or cannot interoperate.

The user selected React/Vite, strict TypeScript, Tailwind 4/daisyUI 5, MSAL,
native History/fetch APIs and no router/query library. Native route handling
arrives with feed/item pages; the first UI needs only chat and its auth callback.
The official SDK's exact headers, streaming, cancellation and task mappings
must pass a bounded compatibility check before live acceptance.

ACA preserves the retained Terraform/azd environment and secretless image
deployment. The proposed SWA deployment-token exception was not selected.
The first SPA requests only agent `news.agent`; the agent's existing secretless
OBO remains the MCP path. Direct browser MCP `news.read` is a subsequent owning
slice. Evaluations evolve as versioned product baselines; incomplete acceptance
and previously consumed attempts remain recorded.

## News-first browser interaction

The `ui-news-feed` slice makes latest stored news the default page, with a top
submit-only MCP search box and a closable right-hand agent panel using A2A.
Current-news context is an explicit removable item selection, not an implicit
copy of search text or all visible articles. Closing/reopening preserves transient
interaction state without replaying requests.

The browser acquires separate delegated MCP `news.read` and agent `news.agent`
tokens through MSAL. The existing agent OBO remains unchanged. Add only the
intended SPA MCP consent and exact MCP/UI origin/configuration changes through
owning layers. Default browsing has no model cost; semantic search's existing
query embeddings and explicit research chat have separate accounting.
Live user sign-in is only through the user's regular browser; unavailable
automated checks stay open instead of borrowing/exporting credentials.

## Explicit filters and subsequent API transport

The `ui-news-filters` slice keeps draft edits separate from applied browsing and
structured A2A constraints. Catalogue discovery uses existing MCP `list_sources`;
metadata-only browsing uses query-less `search_news`, with no embeddings.
Calendar presets use local dates, not fixed-hour subtraction. Submitted research
context remains attached to its answer when browsing changes.

After measured UI publication and filters, the confirmed preferred direction is
a cached HTTP API co-hosted in the MCP ACA app where practical, with existing
delegated `news.read` and workload identity. Its owning proposal must define
route authentication/CORS explicitly and authorize before every cache lookup/hit.
Credentials and conversations are not cached. Detail/cursor contracts, cache
freshness/invalidation, authorization partitioning and replica behavior belong
there, not in filters. No cache resource has been selected.

The user selected a process-local 60-second cache, avoiding a shared cache resource.
The `cached-news-api` slice uses per-caller authorization partitions and absolute
read-start expiry; every hit still validates the delegated user. Browse-only
keysets order publication descending and UUID ascending, without durable snapshot
claims. Semantic search remains top-k (maximum 50), not a paginated session.
The [API runbook](news-api.md) owns route/error/cache/rollout details.

The later UI slice swaps the transport-neutral NewsCatalog adapter to HTTP;
agent interaction stays A2A and agent tools stay MCP. Versioned evaluations resume
after that migration, preserving historical attempts, receipts and accounting.

## HTTP-backed reader navigation

The `ui-http-news-catalog` slice replaces browser MCP with the deployed HTTP API,
without replacing the agent's A2A interface or agent-side MCP tools. The user
selected shareable native-history item pages and explicit Load more, 20 per
request with a 200-item display cap; no new router, query cache or virtual list
dependency is needed. Search stays bounded, and details expose only stored public
summary/metadata, never a fetched/rendered publisher article.

An owning app-only config mode pairs the new strict newsApiUrl/newsScope fields
with the matching UI image. Preserve old config/image bindings for reviewed
rollback; do not retain runtime MCP fallback or remove the existing news consent.
Historical UI deltas retain their old transport evidence; this migration owns
the current transition, not retroactive completion of those acceptance ledgers.

## Scheduled shared briefing, separate from interactive research

The [daily briefing](../openspec/changes/daily-news-briefing/proposal.md) is a
shared product artifact, not an unattended delegated-user A2A request. A dedicated
managed-identity writer reads a frozen seven-day stored-news snapshot and
publishes one atomic summary/TL;DR pair for each 05:00 UTC slot. Hierarchical
synthesis considers all eligible stored records rather than silently using an
interactive top-k or UI page. TL;DR derives from the completed summary.

Use the retained database/ACA environment with additive migrations and one
separate pinned chat deployment for throughput, not the existing pipeline's
capacity or a new model choice. Preserve historical principal checksums and
foundation identity inventory. The co-hosted HTTP API retains delegated
news.read and read-only MCP identity; no application-only caller scope,
browser regeneration or conversation persistence is introduced.

The panel displays TL;DR above a native full-summary collapsible, closed by
default. Reading/expanding cannot generate or mutate research context. Durable
run/call accounting prevents duplicate/uncertain inference replay; stale
publication remains visibly stale. Measure calls/tokens/latency/model cost
before deciding a spending policy; no daily dollar cap is added. Actual RBAC
scope and semantic/citation/scheduling acceptance must be measured, not inferred
from a client deployment name or local fixture.
