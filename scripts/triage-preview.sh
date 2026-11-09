#!/usr/bin/env bash
# Local triage preview with the retained azd environment's model settings.
# Usage: bash scripts/triage-preview.sh [--replay]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
for name in MODEL_ENDPOINT ENRICHMENT_DEPLOYMENT; do
  export "$name=$(azd env get-value "$name")"
done
export INPUT_PRICE="$(azd env get-value BRIEFING_INPUT_PRICE_PER_MILLION)"
export OUTPUT_PRICE="$(azd env get-value BRIEFING_OUTPUT_PRICE_PER_MILLION)"
exec uv run --locked python scripts/triage_preview.py "$@"
