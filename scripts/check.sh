#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Fingerprint every tracked or new, non-ignored file plus the options that change
# which suites run. azd hooks pass --reuse to skip a re-run for an identical source.
fingerprint() {
  {
    printf 'db=%s browser=%s\n' "${NEWSLOOM_TEST_POSTGRES_DSN:+set}" "${NEWSLOOM_BROWSER_ENGINE:-}"
    git ls-files -z --cached --others --exclude-standard | sort -z |
      while IFS= read -r -d '' file; do
        [[ -f "$file" ]] || continue
        printf '%s  %s\n' "$(sha256sum < "$file" | cut -d' ' -f1)" "$file"
      done
  } | sha256sum | cut -d' ' -f1
}
stamp=".cache/checks/$(fingerprint)"
if [[ "${1:-}" == "--reuse" && -f "$stamp" ]]; then
  printf '%s\n' "checks already passed for this exact source; skipping (${stamp##*/})"
  exit 0
fi

uv sync --locked --all-packages
bash scripts/check-agent-evaluation.sh || {
  printf "%s\n" "evaluator suite failed; retrying once for known timing flakes" >&2
  bash scripts/check-agent-evaluation.sh
}
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest
uv run --isolated --locked --no-dev --package newsloom-agent newsloom-agent check-runtime
uv run --isolated --locked --no-dev --package newsloom-briefing python -c \
  'import asyncio; import newsloom_briefing.cli; from azure.identity.aio import ManagedIdentityCredential; credential = ManagedIdentityCredential(); asyncio.run(credential.close())'
uv run --isolated --locked --no-dev --package newsloom-enrichment python -c \
  'import asyncio; import newsloom_enrichment.cli; from azure.identity.aio import ManagedIdentityCredential; credential = ManagedIdentityCredential(); asyncio.run(credential.close())'
uv run --isolated --locked --no-dev --package newsloom-briefing python -c \
  'import newsloom_briefing.cli'
uv run --isolated --locked --no-dev --package newsloom-mcp python -c \
  'import newsloom_mcp.cli; from mcp.server.lowlevel import Server'
uv run --locked newsloom-validate-feeds config/feeds.json
uv run --locked python scripts/check_identifiers.py
npm run -w services/web lint
npm run -w services/web typecheck
npm run -w services/web test
npm run -w services/web build
bash scripts/check-ui-browser.sh
npm run spec:check
terraform fmt -check -recursive infra
for directory in infra infra/bootstrap infra/migrations infra/ingestion infra/enrichment infra/mcp-identity infra/mcp infra/phase1-acceptance infra/agent-identity infra/agent infra/agent-evaluation infra/ui-identity infra/ui infra/briefing-identity infra/briefing; do
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
terraform -chdir=infra/agent-evaluation test
terraform -chdir=infra/ui-identity test
terraform -chdir=infra/ui test
terraform -chdir=infra/briefing-identity test
terraform -chdir=infra/briefing test
mkdir -p .cache/checks && touch "$stamp"
