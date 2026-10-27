# Newsloom

Curated AI news for MCP clients, research agents, and people.

**Status: Phase 1 complete and verified.**
- Available: Python workspace, 41-feed catalogue, local/CI checks, azd-managed Azure infrastructure, managed-identity migrations, RSS/Atom ingestion with real Decision-model screening, and durable queue/quarantine storage. Enrichment produces validated summaries, one of 11 categories, tags, and 1536-dimensional embeddings in PostgreSQL. The deployed MCP service provides four read-only browsing/search tools with verified Entra browser sign-in.
- The [phase acceptance matrix](docs/phase1-acceptance.md#verified-phase-acceptance-matrix) links real federated integration, exact cleanup, failure/cancellation drills, separate quality/native-client studies and passing implementation/status CI. Phase 1 changes are archived with their delivered contracts in the [main specs](openspec/specs/). [Phase 2 Step 2.1](docs/prd-2.md) has verified local and Azure runtime acceptance: signed-in user-preserving MCP access, real Foundry streaming, cancellation, private telemetry and workload denials. The [agent runbook](docs/agent.md) records the exact deployed revision and preserved workloads/data. Its implementation is published with passing exact-SHA CI; the separate final status receipt/CI is pending. Full research and the browser UI remain future work.

## Architecture

```mermaid
flowchart LR
    Feeds["RSS / Atom feeds"] --> Ingestion["Ingestion job"]
    Ingestion --> Queue[("PostgreSQL queue")]
    Ingestion --> Quarantine[("Quarantine")]
    Queue --> Enrichment["Enrichment job"]
    Enrichment --> News[("News + pgvector")]
    News --> MCP["MCP server"]
    MCP --> Clients["MCP clients"]
    MCP --> Agent["A2A agent - Phase 2"]
    Agent --> UI["Browser UI - Phase 3"]
```

## Local development

| Tool | Requirement |
| --- | --- |
| uv | 0.13.5+; downloads the pinned Python 3.15.1 runtime |
| Node.js | 20.19+; 24 LTS recommended |
| Terraform | 1.15.8+ |
| Azure CLI + azd 1.36.0+ | Required only for Azure setup and deployment |

Git and Bash are also required.

```bash
uv sync --locked --all-packages
npm ci --no-audit --no-fund
uv run pre-commit install
bash scripts/check.sh
```

Checks need no cloud credentials or Docker daemon; the first run downloads dependencies.
Database integration tests also run in CI and can be enabled against an explicitly
started local PostgreSQL 18/pgvector instance.

## Deploy to Azure

### 1. One-time state setup

Follow the [state-bootstrap runbook](docs/azure-bootstrap.md) for permissions,
provider registration, and azd environment inputs. Provisioning always runs
through azd, which invokes Terraform internally.

```bash
az login
az account set --subscription "<subscription-id>"
azd config set auth.useAzCliAuth true
```

After configuring the environment, **review the preview before provisioning**:

```bash
azd provision bootstrap --preview
azd provision bootstrap
```

Complete the runbook's RBAC verification before continuing. Keep the bootstrap
state; existing direct-Terraform state must be adopted before the first azd run.

### 2. Application deployment - from Step 1.1

The shared platform is provisioned and verified in the persistent development
environment. See the [delivery plan](docs/prd-1.md#delivery-plan) and follow the
[platform runbook](docs/azure-platform.md) for reviewed inputs and per-layer previews.
Deploy incremental changes into the existing environment:

```bash
azd env select dev
azd up
```

The foundation includes verified migration and identity/model/telemetry checks.
The real ingestion job adds screened pending work, not summaries or an MCP HTTP
service. Follow the [ingestion runbook](docs/ingestion.md) for calibration,
immediate execution, independent database readback, and schedule enablement.
The separate [enrichment job](docs/enrichment.md) processes accepted work into
stored news using the existing managed identity and model deployments, with
bounded claims, atomic completion and lease recovery. The independently deployed
[MCP app](docs/mcp.md) serves committed news through Entra-protected HTTP tools.
Its owning identity/app layers reuse the existing platform and preserve both
pipeline jobs. Both runtime schedules continue in Azure independently of the
developer laptop. Follow the MCP runbook for registration, private client
configuration, isolated retrieval evaluation and operator verification.

## Useful commands

| Task | Command |
| --- | --- |
| All local checks | `bash scripts/check.sh` |
| Python tests | `uv run pytest` |
| Validate feed configuration | `uv run newsloom-validate-feeds config/feeds.json` |
| Start Azure ingestion immediately | `uv run --locked newsloom-platform execute-ingestion` |
| Read actual ingestion database counts | `uv run --locked newsloom-platform read-ingestion` |
| Start a bounded Azure enrichment run | `uv run --locked newsloom-platform execute-enrichment --limit 10` |
| Read actual enrichment/news database counts | `uv run --locked newsloom-platform read-enrichment` |
| Verify deployed MCP workload access | `uv run --locked newsloom-platform verify-mcp` |
| Run the isolated frozen retrieval study | `uv run --locked newsloom-platform evaluate-mcp` |
| List OpenSpec changes | `npm run spec:list` |

## Delivery workflow

```mermaid
flowchart LR
    Local["Local checks"] --> Deploy["azd deployment"]
    Deploy --> Verify["Azure verification"]
    Verify --> Commit["Commit"]
    Commit --> Archive["OpenSpec archive"]
```

See the [development guide](docs/development.md) for workflow details,
[bootstrap acceptance](openspec/changes/archive/2026-10-22-bootstrap/tasks.md) for state setup,
and [platform evidence](openspec/changes/archive/2026-10-23-platform-skeleton/tasks.md#acceptance-evidence) for Azure checks.
Delivered platform contracts are maintained in the
[platform](openspec/specs/persistent-azure-platform/spec.md),
[workload access](openspec/specs/workload-access/spec.md), and
[telemetry](openspec/specs/safe-telemetry/spec.md) main specs.
Delivered product contracts cover
[enrichment](openspec/specs/news-enrichment/spec.md),
[MCP serving](openspec/specs/mcp-serving/spec.md),
[news search](openspec/specs/news-search/spec.md), and
[phase acceptance](openspec/specs/phase1-acceptance/spec.md).

## Documentation

| Topic | Links |
| --- | --- |
| Phase 1: MCP platform | [PRD](docs/prd-1.md) / [Capabilities](docs/prd-1-capabilities.md) |
| Phase 2: Research agent | [PRD](docs/prd-2.md) / [Capabilities](docs/prd-2-capabilities.md) |
| Phase 3: Browser UI | [PRD](docs/prd-3.md) / [Capabilities](docs/prd-3-capabilities.md) |
| Architecture and operations | [ADRs](docs/adrs.md) / [Platform notes](docs/platform-notes.md) |
| Azure platform deployment | [Platform runbook](docs/azure-platform.md) |
| Feed ingestion and real screening | [Ingestion runbook](docs/ingestion.md) |
| Structured news enrichment and embeddings | [Enrichment runbook](docs/enrichment.md) |
| Authenticated MCP browsing/search | [MCP runbook](docs/mcp.md) |
| AI contributor instructions | [AGENTS.md](AGENTS.md) |
