#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

application_lock="$(sha256sum uv.lock)"
uv sync --directory tools/agent-evaluation --locked
if [[ "$(sha256sum uv.lock)" != "$application_lock" ]]; then
  printf '%s\n' 'evaluation_application_lock_changed' >&2
  exit 1
fi
uv run --directory tools/agent-evaluation --locked ruff check .
uv run --directory tools/agent-evaluation --locked ruff format --check .
uv run --directory tools/agent-evaluation --locked mypy
uv run --directory tools/agent-evaluation --locked pytest
if [[ "$(sha256sum uv.lock)" != "$application_lock" ]]; then
  printf '%s\n' 'evaluation_application_lock_changed' >&2
  exit 1
fi
