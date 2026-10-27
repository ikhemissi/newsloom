#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

uv sync --locked --all-packages
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest
uv run --isolated --locked --no-dev --package newsloom-agent newsloom-agent check-runtime
uv run --isolated --locked --no-dev --package newsloom-enrichment python -c \
  'import asyncio; import newsloom_enrichment.cli; from azure.identity.aio import ManagedIdentityCredential; credential = ManagedIdentityCredential(); asyncio.run(credential.close())'
uv run --isolated --locked --no-dev --package newsloom-mcp python -c \
  'import newsloom_mcp.cli; from mcp.server.lowlevel import Server'
uv run --locked newsloom-validate-feeds config/feeds.json
uv run --locked python scripts/check_identifiers.py
npm run spec:check
terraform fmt -check -recursive infra
for directory in infra infra/bootstrap infra/migrations infra/ingestion infra/enrichment infra/mcp-identity infra/mcp infra/phase1-acceptance infra/agent-identity infra/agent; do
  terraform -chdir="$directory" init -backend=false -input=false -lockfile=readonly
  terraform -chdir="$directory" validate
done
terraform -chdir=infra test
terraform -chdir=infra/bootstrap test
terraform -chdir=infra/migrations test
terraform -chdir=infra/ingestion test
terraform -chdir=infra/enrichment test
terraform -chdir=infra/mcp-identity test
terraform -chdir=infra/mcp test
terraform -chdir=infra/phase1-acceptance test
terraform -chdir=infra/agent-identity test
terraform -chdir=infra/agent test
