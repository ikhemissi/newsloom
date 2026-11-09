#!/usr/bin/env bash
# Local radar mock-up on the private triage preview (.cache/triage-preview/radar-fixture.json).
# Usage: bash scripts/radar-mock.sh   then open http://127.0.0.1:5180/tests/radar-preview.html
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
fixture="$(pwd)/.cache/triage-preview/radar-fixture.json"
[[ -f "$fixture" ]] || { echo "Run bash scripts/triage-preview.sh first" >&2; exit 1; }
export VITE_RADAR_FIXTURE="$fixture"
exec npm run -w services/web dev -- --port 5180 --strictPort
