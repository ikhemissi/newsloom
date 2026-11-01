#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
engine="${NEWSLOOM_BROWSER_ENGINE:-}"
if [[ -z "$engine" ]]; then
  exec npm run -w services/web e2e:local
fi
if [[ "$engine" != "podman" && "$engine" != "docker" ]]; then
  printf '%s\n' 'ui_browser_engine_invalid' >&2
  exit 1
fi
image="localhost/newsloom-ui-browser:${BASHPID}-$(date +%s)"
cleanup() {
  "$engine" image rm "$image" >/dev/null
}
"$engine" build --target browser-check -f services/web/Dockerfile -t "$image" .
trap cleanup EXIT
"$engine" run --rm --ipc=private "$image"
