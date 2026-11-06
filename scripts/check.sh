#!/usr/bin/env bash
# Repository checks. Usage:
#   bash scripts/check.sh            run checks for what changed since the base (default origin/main)
#   bash scripts/check.sh --all      run every check (CI on ready PRs and main)
#   bash scripts/check.sh --reuse    skip if this exact source already passed (azd hooks)
# CHECK_BASE overrides the comparison base.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

mode=changed
reuse=false
for argument in "$@"; do
  case "$argument" in
    --all) mode=all ;;
    --reuse) reuse=true ;;
    *) printf '%s\n' "unknown argument: $argument" >&2; exit 2 ;;
  esac
done

# Fingerprint every tracked or new, non-ignored file plus the options that change
# which suites run.
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
if [[ "$reuse" == true && -f "$stamp" ]]; then
  printf '%s\n' "checks already passed for this exact source; skipping (${stamp##*/})"
  exit 0
fi

stage_name=""
stage_start=$SECONDS
timings=()
stage() {
  [[ -n "$stage_name" ]] && timings+=("$(printf '%5ss  %s' $((SECONDS - stage_start)) "$stage_name")")
  stage_name="$*"
  stage_start=$SECONDS
  printf '\n== %s\n' "$*"
}

uv sync --locked --all-packages
if [[ "$mode" == all ]]; then
  eval "$(uv run --locked python scripts/check_plan.py --all --shell)"
else
  base="${CHECK_BASE:-$(git merge-base HEAD origin/main 2>/dev/null || echo HEAD)}"
  eval "$(uv run --locked python scripts/check_plan.py --base "$base" --shell)"
fi
printf 'mode=%s changed=%s everything=%s evaluation=%s web=%s python_test_files=%s terraform_layers=%s\n' \
  "$mode" "$CHANGED" "$EVERYTHING" "$EVALUATION" "$WEB" \
  "$(wc -w <<< "$PYTHON_TESTS")" "$(wc -w <<< "$TERRAFORM")"

stage "always: lint, types, startup, config, specs"
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --isolated --locked --no-dev --package newsloom-agent newsloom-agent check-runtime
uv run --isolated --locked --no-dev --package newsloom-briefing python -c \
  'import asyncio; import newsloom_briefing.cli; from azure.identity.aio import ManagedIdentityCredential; credential = ManagedIdentityCredential(); asyncio.run(credential.close())'
uv run --isolated --locked --no-dev --package newsloom-enrichment python -c \
  'import asyncio; import newsloom_enrichment.cli; from azure.identity.aio import ManagedIdentityCredential; credential = ManagedIdentityCredential(); asyncio.run(credential.close())'
uv run --isolated --locked --no-dev --package newsloom-mcp python -c \
  'import newsloom_mcp.cli; from mcp.server.lowlevel import Server'
uv run --locked newsloom-validate-feeds config/feeds.json
uv run --locked python scripts/check_identifiers.py
npm run spec:check
terraform fmt -check -recursive infra

if [[ "$EVALUATION" == 1 ]]; then
  stage "evaluation tooling"
  # Tests that spawn real processes have tight deadlines: run them serially so parallel
  # workers cannot starve them. The slowest privacy files run on full checks only.
  process=(tests/test_baseline_capture_admission.py tests/test_baseline_cli.py
    tests/test_baseline_inputs.py tests/test_baseline_ipc.py tests/test_compatibility.py
    tests/test_runner.py)
  slow=(tests/test_baseline_privacy.py tests/test_baseline_workflow.py tests/test_privacy.py)
  deselect=()
  for file in "${process[@]}" "${slow[@]}"; do deselect+=(--deselect "$file"); done
  serial=("${process[@]}")
  [[ "$mode" == all ]] && serial+=("${slow[@]}")
  EVALUATION_PYTEST_ARGS="-n auto -p no:cacheprovider ${deselect[*]}" \
    bash scripts/check-agent-evaluation.sh
  uv run --directory tools/agent-evaluation --locked pytest -q -p no:cacheprovider "${serial[@]}"
fi

if [[ -n "$PYTHON_TESTS" ]]; then
  stage "python tests ($(wc -w <<< "$PYTHON_TESTS") files)"
  read -ra files <<< "$PYTHON_TESTS"
  # Temporary files must stay outside the repository (some tests reject repo paths).
  scratch="$(mktemp -d)"
  uv run --locked pytest -q -p no:cacheprovider --basetemp "$scratch" "${files[@]}"
  rm -rf "$scratch"
fi

if [[ "$WEB" == 1 ]]; then
  stage "web"
  npm run -w services/web lint
  npm run -w services/web typecheck
  npm run -w services/web test
  npm run -w services/web build
  bash scripts/check-ui-browser.sh
fi

if [[ -n "$TERRAFORM" ]]; then
  stage "terraform ($(wc -w <<< "$TERRAFORM") layers)"
  export TF_PLUGIN_CACHE_DIR="$PWD/.cache/terraform-plugins"
  mkdir -p "$TF_PLUGIN_CACHE_DIR"
  for directory in $TERRAFORM; do
    terraform -chdir="$directory" init -backend=false -input=false -lockfile=readonly > /dev/null
    terraform -chdir="$directory" validate > /dev/null
    terraform -chdir="$directory" test
  done
fi

stage "done"
mkdir -p .cache/checks && touch "$stamp"
printf '\n%s\n' "checks passed (mode=$mode) in ${SECONDS}s"
printf '%s\n' "${timings[@]}"
