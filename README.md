# Newsloom

Curated AI news for MCP clients, a research agent, and eventually a browser UI.

**Status: Step 0 bootstrap.** The Python workspace, 42-feed catalogue, local/CI checks,
OpenSpec workflow, and secretless Terraform state-bootstrap configuration are present.
The service packages are boundaries only, not running ingestion, enrichment, or MCP services.
No Azure resources are created by installing the project.

## Quick start

Requirements: Python 3.15.1 (downloaded by uv), uv 0.13.5+, Node.js 20.19+ (24 LTS
recommended), Terraform 1.15.8+, Git, and Bash. Azure CLI and azd are needed only for
Azure verification and later deployment.

```bash
uv sync --locked --all-packages
npm ci --no-audit --no-fund
uv run pre-commit install
bash scripts/check.sh
```

If uv reports an unsupported version, update it using the installation method you
originally used (for the standalone installer: `uv self update`).

The script implements the
[OpenSpec quality gates](openspec/changes/bootstrap/specs/repository-foundation/spec.md#requirement-cloud-credential-free-quality-gates).
The first run downloads packages and Terraform providers; state-infrastructure
assertions use a mocked provider.

```bash
uv run pytest
uv run mypy
uv run newsloom-validate-feeds config/feeds.json
npm run spec:list
```

## Layout

| Path | Purpose |
| --- | --- |
| [packages/newsloom-core](packages/newsloom-core/) | Shared typed foundations; currently feed-configuration validation |
| [services/ingestion](services/ingestion/) | Future independently deployed ACA ingestion job |
| [services/enrichment](services/enrichment/) | Future independently deployed ACA enrichment job |
| [services/mcp](services/mcp/) | Future independently deployed, authenticated MCP app |
| [config/feeds.json](config/feeds.json) | Initial 42 RSS/Atom sources and publisher category filters |
| [infra](infra/) | azd Terraform project; application resources arrive in Step 1.1 |
| [infra/bootstrap](infra/bootstrap/) | One-off persistent RBAC-only state infrastructure |
| [openspec](openspec/) | Change proposals, acceptance scenarios, and verified archived specs |
| [tests](tests/) | Offline bootstrap tests |

## Requirements and delivery

- [Architecture decisions](docs/adrs.md)
- [Platform planning notes](docs/platform-notes.md)
- [Development and OpenSpec workflow](docs/development.md)
- [Azure state bootstrap and verification](docs/azure-bootstrap.md)
- [PRD-1: MCP news platform](docs/prd-1.md) and [capabilities](docs/prd-1-capabilities.md)
- [PRD-2: A2A research agent](docs/prd-2.md) and [capabilities](docs/prd-2-capabilities.md)
- [PRD-3: Agent UI](docs/prd-3.md) and [capabilities](docs/prd-3-capabilities.md)

The phase PRDs own phase status, prerequisites, and ordered delivery assignments;
their capability documents own product behavior, user stories, and acceptance criteria.
Architecture decisions and platform notes provide supporting context without
retaining a duplicate full specification.

## Delivery boundary

Release and archival gates are defined in the
[OpenSpec delivery contract](openspec/changes/bootstrap/specs/repository-foundation/spec.md#requirement-honest-ordered-delivery).
See the [bootstrap tasks](openspec/changes/bootstrap/tasks.md) for outstanding
acceptance checks, then follow the [Phase 1 delivery plan](docs/prd-1.md#delivery-plan).
