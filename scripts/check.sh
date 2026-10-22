#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

uv sync --locked --all-packages
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest
uv run --locked newsloom-validate-feeds config/feeds.json
uv run --locked python scripts/check_identifiers.py
npm run spec:check
terraform fmt -check -recursive infra
for directory in infra infra/bootstrap; do
  terraform -chdir="$directory" init -backend=false -input=false -lockfile=readonly
  terraform -chdir="$directory" validate
done
terraform -chdir=infra/bootstrap test
