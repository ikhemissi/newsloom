# MCP serving operations

Status: delivered with local, real-model retrieval, actual workload-denial
and warning-free VS Code/Copilot browser sign-in acceptance.
[Implementation CI](https://github.com/ikhemissi/newsloom/actions/runs/40133602862)
and [separate evidence-head CI](https://github.com/ikhemissi/newsloom/actions/runs/40133806766)
passed. The change is archived; [phase-wide acceptance](phase1-acceptance.md)
is also complete and verified.
See the [archived change](../openspec/changes/archive/2026-10-26-mcp-server/tasks.md)
for evidence and the delivered [serving](../openspec/specs/mcp-serving/spec.md)
and [search](../openspec/specs/news-search/spec.md) contracts for behavior.

## Read-only tools and public data

Four Streamable HTTP tools are implemented at `/mcp`: `get_recent_news`,
`get_news_item`, `list_sources`, and `search_news`.
Collection responses contain `items`; detail contains `found` and `item` (null
when a valid ID is absent). Invalid UUIDs are input errors, not not-found results.

Public fields are ID, title, summary, source ID, category ID, tags, published UTC
time and original URL. Detail also includes stored author/date origin/publisher
categories. Raw articles, publisher GUIDs, vectors, model settings and processing
state are not public results. Result strings remain untrusted source data.

Use IDs from discovery and the [category catalogue](../config/categories.json),
not display labels as filters. Discovery lists only sources/categories represented
in committed news. Empty matching sets are valid; service failures are not empty
successes.

Limits default to 10 and accept integers 1-50 (not booleans). All dates require
timezone-aware timestamps, normalized to UTC. `since`/`from` are inclusive;
`to` is exclusive. Search bounds must increase. Tags are lowercase/whitespace
normalized and match ALL supplied terms. Queries must be nonblank when supplied,
at most 2,048 characters; at most ten concise 48-character tags are accepted.

Metadata-only results are newest first with a stable ID tie-breaker and require
no embedding. Semantic search applies every filter in a materialized eligible
relation before exact pgvector cosine ordering and LIMIT. This avoids global
top-k filtering and selective HNSW underfill; the existing HNSW index remains
available for later measured tuning. Similarity is a finite cosine score, not a
relevance probability. Metadata-only similarity is null, not fabricated.

## Database boundary

Only versioned migrations grant the existing MCP role SELECT on required news
columns. Internal embedding/model columns support ranking/compatibility checks
but are not serialized to callers. The role cannot read queue/quarantine or
perform news writes, DDL or another workload's operations. Runtime startup never
runs migrations. User tokens are not database or model credentials.

## Authentication and protocol

The package pins the stable official Python MCP SDK and uses its typed low-level
handler registration plus supported Streamable HTTP app/auth integration.
This preserves the exact `from` wire name without Python reserved-keyword dispatch
workarounds. Inputs and outputs have explicit schemas; results are structured data.

The resource is a single-tenant Entra API, not an authorization server. Every
MCP request, including initialization and tool discovery, requires a signed,
unexpired token for the configured tenant/API audience. The delegated `news.read`
scope is mapped to its fully-qualified advertised scope. Wrong audience, tenant,
issuer, key, lifetime or scope fails before any repository/model use.

Only configured tenant JWKS are fetched over HTTPS, with a five-second/128-KiB
bound, a one-hour key cache and bounded unknown-key refresh. Token-supplied key
URLs, embedded keys and non-RS256 algorithms are rejected. Audience validation
uses the Entra application ID, not the MCP endpoint URL. The SDK's resource-URL
equality option is explicitly off because the verifier independently checks the
actual API audience; there is no unverified audience fallback.

The canonical HTTPS MCP URL must also be an **Application ID URI on that same
v2 API registration**, alongside its original `api://` identifier. This lets
Entra resolve the client's resource indicator and existing scope to the same
API; it does not change the GUID audience or permit other tokens.
[Microsoft's MCP/Entra guide](https://learn.microsoft.com/en-us/entra/agent-id/secure-mcp-server-with-entra-id#i-get-error-aadsts9010010-when-a-client-requests-a-token-for-my-mcp-server)
documents `AADSTS9010010` when these do not match.

Protected-resource metadata lives at `/.well-known/oauth-protected-resource/mcp`;
401 challenges advertise that route. The public VS Code/Copilot client requests
the Newsloom API scope with PKCE after reviewed registration/consent setup, not a
database/Foundry token. Actual sign-in and all four native tools are verified in
the [acceptance evidence](../openspec/changes/archive/2026-10-26-mcp-server/tasks.md#acceptance-evidence).

## Private VS Code/Copilot connection

For the Copilot harness, keep the server in its private user configuration:
`$COPILOT_HOME/mcp-config.json`, or `~/.copilot/mcp-config.json` when unset.
Use the home on the host running the agent; the verified session runs in WSL.
Do not commit the populated URL/client identifiers.

```json
{
  "mcpServers": {
    "newsloom-dev": {
      "type": "http",
      "url": "<canonical-mcp-url>",
      "oauthClientId": "<public-client-id>",
      "tools": ["*"]
    }
  }
}
```

Use the outputs `MCP_RESOURCE_URL` and `MCP_PUBLIC_CLIENT_ID`; these identify
the resource and pre-registered public client, not credentials. On Linux, keep
the private file mode 0600. No Authorization header, token or client secret
belongs in this configuration.

The legacy VS Code profile format uses `servers` and `oauth.clientId`, but the
Copilot forwarding path warns that it drops custom OAuth configuration.
Migrate only this server to the format above, verify the destination, then
remove its duplicate source entry. Preserve unrelated servers and OpenSpec
customizations. Reload/start a fresh Copilot session and complete browser sign-in.
Do not assume an existing token cache proves the migrated client configuration.

To inspect the tools in the Copilot harness, run **Chat: Open Customizations**,
select **Tools**, and filter for `newsloom`. **MCP Servers** manages connections;
the **Configure Tools** input picker belongs to the Local harness.
Output is client diagnostics, not a complete request trace. Safe authenticated
tool/latency evidence is in Application Insights; no arguments/results are logged.

Host and Origin allowlists remain enabled. The canonical `/mcp` route must not
redirect HTTPS to plain HTTP behind ingress. The SDK bounds message bodies to
64 KiB; tools admit at most four concurrent operations, wait at most one second
for admission and have 90-second overall deadlines. Database statements have a
five-second timeout. Invalid input consumes no model/database quota; cancellation
propagates and closes connections.

## Query inference

Query embeddings reuse the shared bounded Entra transport and strict vector
contract, with no generation call or user-token forwarding. Each vector must
have 1536 finite non-boolean numeric components and nonzero norm. Compatible
embedding model/version metadata is checked for all eligible news before ranking;
incompatible rows cause an explicit error, not silent omission.

Inference uses at most three 20-second transport attempts within the overall
request budget and honors Retry-After without sleeping past the deadline.
There is no cross-user query cache, model change, fabricated vector or silent
semantic-to-metadata fallback. Failed inference is not an empty successful query.

## Owning registration and app setup

`newsloom-platform prepare-mcp-identity` performs a read-only directory inventory
and writes only ignored azd inputs. It never creates directory objects or selects
an application by name: existing matching names require explicit configured API/
client IDs. Exact matches are checked for single-tenant/read-only scope, v2 API
tokens, public-client redirects and absence of client credentials. Terraform
import blocks adopt those exact object/principal IDs and preserve the existing
scope ID. Mismatches stop for review rather than overwrite an unrelated app.

The installed VS Code 1.143.0 build's client-registration prompt advertises
`http://127.0.0.1:33418` and `https://vscode.dev/redirect`, but the actual
post-reload browser flow used `http://localhost` with an ephemeral port.
Following an observed `AADSTS50011` and explicit approval, the public/native
client also registers exactly **`http://localhost`**.
[Entra's localhost matching rule](https://learn.microsoft.com/en-us/entra/identity-platform/reply-url#localhost-exceptions)
ignores the port, so do not register each temporary port, use a wildcard,
substitute `127.0.0.1` for `localhost`, or move this callback to the web/SPA
platform. Host and path restrictions still apply. The original two callbacks
are retained. Actual browser PKCE sign-in passed with this configuration.
The identity layer creates only missing API/public-client
registrations, their service principals and the API identifier URI. It creates
no passwords, client secrets, Graph permissions, broad directory role assignments
or all-user admin-consent grant. Tenant consent restrictions remain an explicit
operator prerequisite.

```bash
uv run --locked newsloom-platform prepare-mcp-identity
azd provision mcp-identity --preview
azd provision mcp-identity
uv run --locked newsloom-platform build-mcp
azd provision mcp --preview
azd provision mcp
```

The MCP read migration must be applied through the existing migration job before
the app can become ready. The owning app layer derives its canonical resource
URL from the actual existing Container Apps environment default domain; verify
the resulting app FQDN matches it. It uses one always-on Consumption replica,
0.25 vCPU/0.5 GiB, explicit probes, HTTPS ingress, its existing identity and an
immutable registry image. Existing pipeline jobs/schedules are not redeployed
or replaced to enable this service.

On a first deployment, the identity layer can create registrations before the
app URL is available. Once the app outputs `MCP_RESOURCE_URL`, rerun
`prepare-mcp-identity` and preview/apply **only `mcp-identity`** to add that exact
URL alias. Inventory preserves/adopts an already matching alias. No scope
replacement, proxy, token copying or service-image change is required.

All actual tenant/client/resource values stay in the ignored azd environment
and private VS Code configuration. Do not paste full configuration, tokens,
authorized result bodies or connection strings into logs/committed examples.
Rollback stops only the owning app or restores its compatible verified image;
retain data, migrations, adopted identity objects and shared state.

### Metered cost preflight

The 2026-10-24 [Azure Retail Prices API](https://prices.azure.com/api/retail/prices)
readback for France Central gives Standard Consumption active/idle vCPU rates
of USD 0.000024/0.000003 per second, and memory of USD 0.000003 per GiB-second
in either state. At 730 hours, one 0.25-vCPU/0.5-GiB replica is approximately
**USD 5.91 if entirely idle or USD 19.71 if entirely active**, before shared
free grants. These are scenarios, not a monthly spending cap or a guarantee
that background work qualifies for idle billing.

Requests above shared allowances, logs, network and embeddings add usage charges.
The existing regional Standard `text-embedding-3-large` meter is USD 0.000158
per 1,000 input tokens (USD 0.158 per million). No new deployment or capacity
increase is planned; the MCP query path shares the existing enrichment quota.
Refresh rates and actual subscription usage before applying the app preview.

## Isolated retrieval evaluation

The frozen authored corpus has 22 projections spanning all 11 categories and
20 labelled queries: ten filtered, ten unfiltered, with separate development
examples. At least six filtered cases have more than five eligible candidates,
so ranking must distinguish distractors rather than pass from filtering alone.
Other cases exercise selective category/tag/date boundaries.
Each query has 1-5 relevant eligible IDs. For each group, require mean
recall@5 >=0.80 and zero filter violations; missing/error cases cannot be omitted
or assigned perfect scores. Deterministic local vectors prove SQL mechanics,
not actual model relevance.

With the user's explicit approval, the migration identity creates one exact-named
temporary schema with authored projections and a manifest. The MCP identity gets
temporary usage/SELECT only. The evaluation-only command in the existing app
computes corpus/query vectors in memory and supplies corpus vectors as bounded
SQL parameters through the same eligible-relation ranking path. It does not write
production news, query queue/quarantine, or obtain temporary write/DDL authority.
Public tools cannot select the fixture schema or a different relation.

```bash
uv run --locked newsloom-platform evaluate-mcp
```

Run this from an interactive terminal: native Azure CLI replica exec requires a
TTY. In the noninteractive Linux automation harness, the existing `script`
utility supplied a local terminal without adding any cloud resource:

```bash
script --quiet --return --command \
  'uv run --locked newsloom-platform evaluate-mcp' /dev/null
```

The first deployed study measured recall@5 1.00 separately for both ten-case
groups, zero errors/filter violations and successful exact-schema cleanup.
See the [acceptance evidence](../openspec/changes/archive/2026-10-26-mcp-server/tasks.md#acceptance-evidence)
for scope and remaining verification; this does not replace actual VS Code
sign-in or workload-denial tests.

The controller records the exact run ID privately, prepares through the migration
job, uses native app-replica execution, validates all 20 reported cases and group
gates, and removes the exact schema/grant in `finally` on success or failure.
Private per-case evidence is stored under the ignored environment directory,
not emitted as raw vectors or text. If an interrupted host prevents automatic
cleanup, resume with `newsloom-platform cleanup-mcp-evaluation` using the retained
run ID, verify removal and do not claim acceptance until cleanup is complete.
Never drop `public`, production tables, a root schema or a wildcard schema.

The explicit `prepare-mcp-evaluation`/`cleanup-mcp-evaluation` commands are
operator recovery tools, not public MCP methods or runtime startup work.

## Operator-only access verification

After local checks and deployment of the MCP image, run from an interactive
terminal (or use the local terminal wrapper shown above):

```bash
uv run --locked newsloom-platform verify-mcp
```

The helper starts the packaged `newsloom-mcp verify-access` command inside the
existing MCP replica using the operator's Azure execution authority. The command
uses only the existing MCP managed identity for data/model access. It compares
stored news results independently, tests real queue/quarantine/private-column/
write/DDL/role denials, confirms embeddings and denied generation/scanning, and
rejects signed wrong-resource/app-only API tokens. A retained evaluation run ID
also checks that its exact schema is absent.

SQL probes use zero-row statements or forced-rollback transactions, including
when a grant unexpectedly permits an operation. Errors such as bad input,
missing objects, network failure or HTTP 400/404 do not count as authorization
denial. Output contains numeric counts and safe status/categories only.

This is an explicit operator command, not a fifth tool, endpoint, worker,
schedule or startup action. It adds no grants and cannot replace actual
delegated VS Code browser sign-in. Runtime/inference failures fail the command.

The deployed verifier passed all five read/search checks and ten SQL denials,
plus embedding, model-denial and signed wrong-resource/app-only token checks.
The [acceptance evidence](../openspec/changes/archive/2026-10-26-mcp-server/tasks.md#acceptance-evidence)
separates these results from synthetic-token tests and actual user acceptance.

## Instrumentation

Authenticated metrics report fixed tool/surface/outcome names, latency and
cumulative embedding input-token/call totals. Model latency is explicitly a mean.
Tool calls/duration and HTTP calls/duration are separate metric series; do not
sum them as a single request count. Cancellation is an explicit outcome.
SDK spans pass through a restrictive exporter that removes request IDs, exception
events/descriptions, links, client trace-state strings, URLs,
query/argument/result bodies and non-allowlisted
attributes before Azure export. Framework access logs are disabled and dependency
messages use shared content-free logging.

Actual HTTP canary tests cover returned article/query/request-ID/credential data,
authorization failures, invalid inputs, Host/Origin rejection, body limits,
overload and cancellation. Safe failures remain distinguishable from empty
successful results; no raw completions or search strings are logged.
