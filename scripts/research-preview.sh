#!/usr/bin/env bash
# Local research-conversation preview with the retained azd environment's model settings.
# Usage: bash scripts/research-preview.sh [--replay]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
for name in MODEL_ENDPOINT ENRICHMENT_DEPLOYMENT; do
  export "$name=$(azd env get-value "$name")"
done
exec uv run --locked python scripts/research_preview.py "$@"
