#!/usr/bin/env bash
# Non-publishing briefing preview with the retained azd environment's model settings.
# Usage: bash scripts/briefing-preview.sh --input news.json [--replay recording.jsonl] [...]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
for name in MODEL_ENDPOINT BRIEFING_DEPLOYMENT BRIEFING_INPUT_PRICE_PER_MILLION \
  BRIEFING_OUTPUT_PRICE_PER_MILLION; do
  export "$name=$(azd env get-value "$name")"
done
exec uv run --locked python -m newsloom_briefing.preview "$@"
