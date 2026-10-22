# Newsloom

Curated AI news for MCP clients, research agents, and people.

**Status: bootstrap only.**
- Available: Python workspace, 42-feed catalogue, local/CI checks, and Terraform state-bootstrap tooling.
- Planned: ingestion, enrichment, MCP service, research agent, and browser UI.

## Planned architecture

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

Once [platform-skeleton](docs/prd-1.md#delivery-plan) is implemented, deploy into the existing environment:

```bash
azd env select dev
azd up
```

**Today, `azd up` does not deploy news services:** application resources and service/image deployment hooks are not implemented yet.
The bootstrap layer runs before the application layer in the same environment.

## Useful commands

| Task | Command |
| --- | --- |
| All local checks | `bash scripts/check.sh` |
| Python tests | `uv run pytest` |
| Validate feed configuration | `uv run newsloom-validate-feeds config/feeds.json` |
| List OpenSpec changes | `npm run spec:list` |

## Delivery workflow

```mermaid
flowchart LR
    Local["Local checks"] --> Deploy["azd deployment"]
    Deploy --> Verify["Azure verification"]
    Verify --> Commit["Commit"]
    Commit --> Archive["OpenSpec archive"]
```

See the [development guide](docs/development.md) for workflow details and
[bootstrap tasks](openspec/changes/bootstrap/tasks.md) for outstanding acceptance checks.

## Documentation

| Topic | Links |
| --- | --- |
| Phase 1: MCP platform | [PRD](docs/prd-1.md) / [Capabilities](docs/prd-1-capabilities.md) |
| Phase 2: Research agent | [PRD](docs/prd-2.md) / [Capabilities](docs/prd-2-capabilities.md) |
| Phase 3: Browser UI | [PRD](docs/prd-3.md) / [Capabilities](docs/prd-3-capabilities.md) |
| Architecture and operations | [ADRs](docs/adrs.md) / [Platform notes](docs/platform-notes.md) |
| AI contributor instructions | [AGENTS.md](AGENTS.md) |
