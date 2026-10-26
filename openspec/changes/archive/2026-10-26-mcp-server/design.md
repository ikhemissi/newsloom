# Design

## Context

See [the proposal](proposal.md) for scope and user-approved defaults, and the
[serving](specs/mcp-serving/spec.md) and [search](specs/news-search/spec.md)
contracts for observable behavior.

Observed integration surfaces:

- [The MCP package](../../../../services/mcp/pyproject.toml) contains only its
  boundary/core dependency; no server or user-token verifier exists.
- [Enrichment's migration](../../../../services/platform/src/newsloom_platform/migrations/003_enrichment.sql)
  already provides stored attribution, summary/category/tags, `vector(1536)`,
  embedding model/version metadata, uniqueness and date/source/category/tag/
  cosine indexes. The MCP role does not yet have news access.
- [The platform](../../../../infra/main.tf) already provisions the MCP managed
  identity, embedding-only inference grant, registry pull and telemetry access.
  There is no API/public-client registration or `news.read` implementation.
- The existing [azd layers](../../../../azure.yaml) and
  [operator build helper](../../../../services/platform/src/newsloom_platform/control.py)
  provide immutable registry images and native previews. Both real pipeline
  schedules are operating; this slice must not disturb them.

Official references checked while planning:

- [VS Code MCP configuration](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)
  supports an explicit `oauth.clientId` for remote servers.
- [MCP authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
  supports pre-registration and protected-resource metadata.
- [Python SDK authorization](https://py.sdk.modelcontextprotocol.io/run/authorization/)
  separates token verification from the authorization server and documents
  Entra's application-ID audience distinction.
- [SDK deployment](https://py.sdk.modelcontextprotocol.io/run/deploy/) describes
  host/origin controls, reverse-proxy URLs and legacy stateless behavior.

These are compatibility inputs, not proof that the installed VS Code/SDK
combination has signed in successfully.

## Goals / Non-Goals

**Goals:** one read-only service, native Entra sign-in, SQL correctness before
approximate-search tuning, real quality evidence, and minimal owning additions.

**Non-Goals:** an authorization server/proxy, dynamic client registration,
conversation/session storage, chat generation, cross-workload refactoring,
new search infrastructure, or declaring all of PRD-1 complete.

## Decisions

### 1. Use the official SDK as a stateless resource server

Implement the service as a typed ASGI application using a pinned stable official
MCP Python SDK and its supported Streamable HTTP integration, served by an ASGI
runner. Resolve the supported stable release and test its Python 3.15 and
installed VS Code compatibility before building against it; do not silently
adopt a prerelease or a different framework if incompatible.

Expose `/mcp` at its exact configured canonical path without a redirect that can
downgrade HTTPS behind ingress. Use stateless request handling for legacy clients
and supported negotiated protocol versions; do not implement custom JSON-RPC,
session persistence, SSE resumption, sampling, prompts or write tools. Cancellation
must propagate to database/model work.

Publish structured input/output schemas and read-only tool annotations, with
clear descriptions that returned source text remains untrusted. Return typed
Pydantic models, not rendered publisher HTML or model-authored prose. Input
validation and HTTP bearer authorization happen before repository/inference use.
Actual HTTP tests exercise discovery and calls; an in-memory SDK client bypasses
the HTTP auth boundary and cannot prove it.

### 2. Separate public user OAuth from workload authentication

Use a single-tenant Entra API registration exposing the delegated
`api://<api-client-id>/news.read` permission and v2 access tokens, plus a dedicated
public-client registration using authorization code with PKCE. No client secret
or certificate credential is needed. The public client requests this API scope,
not a Graph token or the workload model scope.

Add an owning `mcp-identity` azd/Terraform layer using the appropriate directory
provider. Inventory exact existing registrations/service principals first;
adopt/import matching objects into the owning state, never recreate or blindly
select by display name. Review API scope, client grant, consent and registered
redirect URIs before creation/update. Tenant administration is an operator
responsibility: lack of Graph permissions or consent blocks progress rather than
permission to grant the deployer a broad directory role.

Determine the exact callback used by the installed VS Code harness in a bounded
PKCE sign-in preflight and register only its supported loopback/VS Code redirect,
not wildcard callbacks. Verify PKCE S256, client ID, scope and actual audience
through the real flow. A callback or scope limitation that requires an auth proxy,
secret or architecture change is a blocker requiring a separate decision.

The actual installed-client browser flow reported a `localhost` redirect with
an ephemeral port, unlike the initially inspected registration-prompt examples.
Following explicit approval, register `http://localhost` on the existing public
client alongside the two original callbacks. Entra's documented localhost rule
ignores ports; no wildcard, per-port registration, secret or proxy is required.

The service publishes protected-resource metadata, tenant-specific authorization
server discovery and a `WWW-Authenticate` resource-metadata challenge. It does
not host a login page, handle authorization codes, mint tokens or pretend to
support dynamic registration.

Validate JWTs using a maintained JOSE library: permitted asymmetric algorithm,
trusted tenant issuer, API audience, expiry/not-before and required delegated
`scp` value. Use only configured tenant discovery/JWKS URLs with bounded cached
retrieval and a bounded refresh for unknown key IDs. Reject token-directed
`jku`/`x5u`, algorithm substitution, ID tokens and app-only tokens missing `scp`.
Do not persist decoded personal claims in logs.

The canonical MCP resource URL and Entra token audience are different identifiers.
Configure SDK audience/resource handling explicitly: validate the actual API
audience in the verifier rather than asserting that it equals the endpoint URL.
Never forge verified audience data or disable all audience checks to satisfy SDK
metadata. Test that the issuer/scope advertised to VS Code obtain the token the
verifier actually expects.

After actual VS Code token acquisition reported `AADSTS9010010`, the user
approved adding the canonical HTTPS MCP URL as a second Application ID URI on
the existing v2 API, retaining the original `api://` URI and scope ID/name.
Microsoft documents matching the client's resource indicator and scope to the
same API registration. The URI alias is created/adopted by the owning identity
layer after the app URL is known; JWT audience remains the API GUID. No
resource-metadata forgery, proxy or relaxed token validation is introduced.

Reject missing/invalid credentials with 401 and a safe discovery challenge;
valid tokens lacking permission receive 403/insufficient scope. If trusted-key
discovery cannot establish validity, fail closed with a safe operational error.
The MCP identity, not the user, obtains database and Foundry tokens; no user-token
forwarding, OBO or automatic inference grant is added.

### 3. Expose explicit public-news records and bounded tools

Define `NewsItem` with `id`, `title`, `summary`, `source`, `category`, `tags`,
`published_at` and `url`. Item detail additionally returns stored `author`,
`date_origin` and publisher categories. It does not return raw articles, publisher
GUIDs, embeddings, model metadata, lease fields or quarantine state. Wire
timestamps as UTC ISO strings and stable category IDs from the existing catalogue.

Return collections as `{items: [...]}`. Search items also carry `similarity`,
null for metadata-only queries; semantic scores are `1 - cosine_distance`,
finite values approximately in [-1, 1], not relevance probabilities. Detail uses
`{found: false, item: null}` for a valid absent UUID and `{found: true, item: ...}`
when present. Malformed UUIDs are input errors.

`list_sources()` derives distinct source IDs and source/category associations
from committed news only, returning labels for represented category IDs. No
`feed_sources` read or duplicated feed catalogue is needed. Sources with no news,
including retired-only history, are not advertised as populated filters.
Every tool observes current committed data; do not cache result bodies.

Apply the approved 10/default and 50/maximum limits strictly, excluding booleans.
Accept aware timestamps only, normalize to UTC, include lower bounds and exclude
upper bounds. Search combines exact source/category and tag containment (`all`
semantics); empty optional tag arrays mean no tag restriction. Normalize tag
whitespace/case with the shared contract. Unknown category IDs fail; a valid
unmatched source/tag returns empty results without relaxing constraints.

Expose the JSON name `from` even if its Python argument needs an alias. Tests
must inspect the actual SDK tool schema and calls, not just a helper's signature.
No pagination/cursors or undocumented seven-day cutoff are introduced.

### 4. Use a narrow database projection and exact filtered vector ranking

Add `004_mcp_read.sql`, leaving all applied migration checksums intact. Grant
`newsloom_mcp` only schema usage and SELECT on the needed news columns, including
embedding/model/version columns used internally by search. Do not grant access
to queue/quarantine/administration or add write grants. The API serializes only
the public fields above, not every granted column.

Keep a typed `NewsRepository` with fixed projections and parameterized queries.
Open short read-only operations under the managed identity, enforcing statement
timeouts and consistent snapshots where more than one query builds a response.
For this low-concurrency first slice, bounded per-operation connections avoid a
new custom pooling/credential-renewal layer. Close/cancel connections reliably.
The existing identity and role isolation is tested locally and in Azure with
actual allowed reads and denied unowned operations.

Recent/metadata-only paths use deterministic descending publication then ID
ordering. Semantic search first produces a **materialized eligible relation**
using all source/category/tag/date predicates, then computes exact pgvector
cosine distances over that relation and applies ordering/limit. The LIMIT is
never global before filters. Exact ranking is intentional for the current modest
corpus: it avoids selective HNSW underfill and makes correctness reproducible.
The existing HNSW index remains untouched; approximate tuning is not this slice.

Before semantic ranking, check eligible-row embedding model/version against the
configured query deployment contract within the same snapshot. If incompatible
rows would be ranked, return a safe mismatch error rather than silently exclude
them or change models. Metadata-only browsing still requires no embeddings.
No similarity threshold or relevance-reranker model is introduced.

### 5. Reuse the embedding boundary without coupling runtime services

Extract the existing bounded Foundry request and vector-validation functionality
into core where needed, preserving enrichment's re-exports and behavior through
regression tests. Keep generation/prompt/usage policy in its owning service.
Expose a typed query-embedding operation accepting only the validated query text,
using the existing `text-embedding-3-large` deployment and 1536 dimensions under
the MCP identity.

Do not embed filters in place of the query or call the enrichment model. Reject
wrong length, nonfinite/boolean/zero data and unexpected response shapes using
the existing strict vector semantics. Unknown HTTP errors and exceeded
Retry-After/deadlines remain explicit failures, never successful empty search.
Do not add a cross-user query/result cache to bypass quota or reduce test cost.

Initial implementation bounds, to be tested rather than claimed as measured SLOs:

| Surface | Proposed bound |
| --- | --- |
| Tool result count | 10 default; integers 1-50 |
| Query text | Nonblank when supplied; at most 2,048 characters |
| Tags | At most 10; same concise 48-character normalized tag shape |
| Input body | 64 KiB, including streamed/chunked messages |
| Concurrent tool operations | 4 per process, bounded acquisition then explicit overload |
| Whole operation / SQL statement | 90 seconds / 5 seconds |
| Embedding request / attempts | At most 20 seconds each / 3 within overall deadline |
| Token/JWKS/network acquisition | Bounded by overall deadline; key fetch at most 5 seconds |

Use one process/replica initially. Respect the deployment's actual shared quota;
model calls can be throttled by enrichment and must fail/defer explicitly within
budget rather than increase capacity. Invalid input is rejected before consuming
that quota.

### 6. Measure retrieval in an isolated explicit evaluation path

Freeze 20 authored query cases before live inference: ten unfiltered, ten with
source/category/tag/date constraints. Include 1-5 relevant eligible IDs per case,
all 11 categories across the corpus, paraphrases, distractors and date/tag/filter
boundary traps. Keep development examples separate. For each query,
`recall@5 = relevant retrieved IDs / all labelled relevant eligible IDs`.
Compute each group's arithmetic mean independently and require >=0.80 plus zero
filter violations. Empty eligible relevance labels are invalid fixtures, not 1.0.
Report every missing/error case as a failed gate; no denominator shrinkage.

Offline tests use disposable local PostgreSQL with deterministic vectors and
actual SQL; these prove protocol/filter/ranking mechanics, not real-model recall.
The real measured evaluation runs the same embedding and ranking implementation
under the actual MCP identity, not a fake model or a changing live-news corpus.

The user approved a short-lived, migration-owned schema in the existing database.
Prepare only authored fixture projections there and grant the MCP role temporary
schema usage/SELECT, not writes. During an explicit evaluation-only CLI execution
inside the existing MCP app replica, compute corpus/query embeddings in memory.
Supply the bounded corpus vectors as parameterized SQL data joined to the fixture
IDs, then pass that eligible projection through the same ranking query builder.
No corpus embedding INSERT or runtime DDL privilege is required. The production
repository uses a fixed news projection and cannot accept schema/relation
selection from a client. Test both repository paths for identical semantics.

Use the existing migration job for exact named preparation/cleanup, and the
native app execution facility for evaluation; add no permanent evaluation worker
or debug HTTP endpoint. The administrator tracks the exact evaluation schema in
private state and drops it on both success and failure, verifying its grant is
gone. If interruption prevents cleanup, report that explicitly and complete it
before acceptance. Never drop production/public schemas or glob schema names.
Evaluation evidence contains opaque query/corpus IDs, fingerprints, scores and
counts, not user text, raw vector arrays, tokens or completions.

### 7. Deploy one small always-on app and control every diagnostic surface

Add an owning MCP Dockerfile/build command and app layer/backend key depending
on the registration inputs and migrations. Use the existing MCP identity,
Consumption environment, registry, PostgreSQL and model outputs. Initially set
one replica (min=max=1), 0.25 vCPU/0.5 GiB, explicit startup/liveness/readiness
checks, verified HTTPS ingress and the digest-pinned image.

Derive the canonical resource URL and allowed host from the actual ACA
environment/app hostname, not arbitrary Host/X-Forwarded headers. If the hostname
is available only after app creation, use an explicit in-place configuration step;
until auth/resource settings are complete the app serves health only and fails
closed for MCP. Allow only the actual service host and explicitly required
client origins. Reject unapproved Origin values and DNS-rebinding/Host inputs.
Do not disable transport protections or introduce a blanket CORS/proxy trust
exception to make a smoke request pass.

Health responses reveal only process/dependency readiness, not data, tenant
values or secrets. All MCP methods remain authenticated. Register only actual
approved redirect URIs; Entra app registration and directory consent are handled
separately from the workload identity's Azure RBAC permissions.

Reuse authenticated telemetry and shared safe dependency logging. Instrument
only allowlisted tool names, outcome/error categories, counts and latency.
Request IDs, client trace context, URLs/query strings, SDK validation exceptions
and framework access logs may contain user-controlled data: disable content
capture and scrub/drop unsafe attributes at export. No automatic SDK/HTTP/SQL
instrumentation may export tool arguments/results, search text, article fields,
headers or bearer tokens. Verify canaries through real HTTP success/error/
cancellation paths with in-memory exporters, not only application print helpers.

### 8. Separate delivery checks from user acceptance

After offline gates, apply reviewed registration/migration/app changes without
touching ingestion/enrichment schedules, identities, model capacities or data.
Verify live database reads and actual workload denials, then run the isolated
real-model retrieval study and verify cleanup.

Scripted HTTP/SDK probes with real scoped user credentials verify tool contracts,
negative tokens and independently read stored IDs/counts; do not log returned
news bodies as diagnostics. They do not replace end-user acceptance. The user
must connect the deployed URL in the installed VS Code harness, complete browser
Entra sign-in, see all four tools, and verify recent/detail/discovery plus
semantic/filtered search against live news. Use a private configuration file
with actual client/resource IDs and record only non-sensitive evidence.
Human interaction may be an explicit pause; do not mark it passed on deployment.

The approved private `newsloom-mcp verify-access` CLI runs only through the
operator's existing replica-exec authority, never HTTP tools/startup/scheduling.
The platform's `verify-mcp` helper passes configured model deployment names and
the retained evaluation run ID, validates numeric-only evidence, and records no
tokens or news fields. It independently compares stored records, probes actual
denied SQL operations with forced rollback, verifies embedding access and denied
model endpoints, and checks signed wrong-resource/app-only token rejection.
This packaged command replaces unreliable large inline console scripts without
new infrastructure, permissions, public methods or authentication bypasses.

## Risks / Trade-offs

- **Entra/VS Code interoperability:** pre-registration and actual PKCE flow are
  tested early. No assumed DCR, access-token copy/paste, proxy or secret fallback.
- **Directory access or consent unavailable:** preserve partial state and stop
  for the operator; do not broaden deployer privileges or guess existing objects.
- **Exact ranking may outgrow the corpus:** finite SQL budgets bound work.
  Record real latency and tune HNSW only in a later measured change.
- **Shared embedding quota:** use bounded retries and overload errors, not a
  metadata fallback, extra model capacity or success-shaped empty results.
- **Temporary evaluation access:** isolate the CLI, never expose relation
  selection publicly, track exact schema ownership and verify cleanup.
- **New always-on cost:** refresh real compute/embedding/log pricing before
  provisioning; one small replica is not free or a hard monthly cap.
- **Stored text remains untrusted:** read-only tools prevent it becoming SQL,
  permissions or configuration, but do not promise downstream client immunity.

## Migration Plan

1. Implement and test contracts, the read-only migration, token/transport boundary,
   repository/search, SDK integration, owning infrastructure and diagnostics.
   Run the primary local gate with disposable PostgreSQL and package builds.
2. Inventory registrations/consent and preserve existing resource/news/schedule
   baselines privately. Review/apply only the missing identity objects, additive
   migration and owning app through the persistent azd environment.
3. Verify actual identity privileges and matching endpoints/audience/scope.
   Execute the frozen real retrieval evaluation in the isolated schema and
   verify complete cleanup before acceptance.
4. Immediately run authorized/negative HTTP probes and independent database
   checks, then real VS Code browser sign-in and all four tools. Record failed
   cases and limits; do not substitute health/provisioning for user evidence.
5. On failure retain the additive read projection and all data, close/stop only
   the new app as needed or restore its compatible verified image. Remove only
   explicitly tracked temporary evaluation access. Do not delete adopted
   registrations, clear state, recreate shared resources or disable pipeline jobs.
6. After local/Azure/user acceptance, commit/push and verify exact-SHA CI, then
   persist final evidence/status separately with final-head CI. Do not archive
   unverified tasks or claim phase-wide acceptance from this slice alone.
