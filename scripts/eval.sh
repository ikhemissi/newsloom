#!/usr/bin/env bash
# Offline evaluations. Usage:
#   bash scripts/eval.sh          replay evals: recorded model outputs, no Azure access, $0
#   bash scripts/eval.sh --live   also live model evals (Azure CLI sign-in; a few cents)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

live=false
[[ "${1:-}" == "--live" ]] && live=true

printf '%s\n' "== replay evals"
uv run --locked pytest -q -p no:cacheprovider tests/test_briefing_golden.py

if [[ "$live" == true ]]; then
  printf '%s\n' "== live evals"
  for name in MODEL_ENDPOINT BRIEFING_DEPLOYMENT; do
    if [[ -z "${!name:-}" ]]; then export "$name=$(azd env get-value "$name")"; fi
  done
  NEWSLOOM_LIVE_EVAL=1 uv run --locked pytest -q -p no:cacheprovider -rs \
    tests/test_briefing_live_eval.py
fi
