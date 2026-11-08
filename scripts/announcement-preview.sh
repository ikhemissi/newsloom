#!/usr/bin/env bash
# Local announcement-extraction preview with the retained azd environment's model settings.
# Usage: bash scripts/announcement-preview.sh [--days 7] [--replay]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
for name in MODEL_ENDPOINT ENRICHMENT_DEPLOYMENT; do
  export "$name=$(azd env get-value "$name")"
done
export INPUT_PRICE="$(azd env get-value BRIEFING_INPUT_PRICE_PER_MILLION)"
export OUTPUT_PRICE="$(azd env get-value BRIEFING_OUTPUT_PRICE_PER_MILLION)"
exec uv run --locked python scripts/announcement_preview.py "$@"
