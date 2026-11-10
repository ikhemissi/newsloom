#!/usr/bin/env bash
# Restore the latest database export into a throwaway local PostgreSQL and
# compare row counts with its manifest. Downloaded data is deleted on exit.
set -euo pipefail

engine="${NEWSLOOM_CONTAINER_ENGINE:-podman}"
image="docker.io/pgvector/pgvector:pg18"
name="newsloom-restore-drill"
work="$(mktemp -d "${TMPDIR:-/tmp}/newsloom-restore.XXXXXX")"
cleanup() {
  "$engine" rm -f "$name" > /dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT

account_url="$(azd env get-value BACKUP_ACCOUNT_URL)"
container="$(azd env get-value BACKUP_CONTAINER)"
account="${account_url#https://}"
account="${account%%.*}"

manifest="${1:-}"
if [[ -z "$manifest" ]]; then
  manifest="$(az storage blob list --auth-mode login --account-name "$account" \
    --container-name "$container" --prefix postgres/ --query "[?ends_with(name, '.json')].name" \
    -o tsv | sort | tail -n 1)"
fi
[[ -n "$manifest" ]] || { echo '{"event":"restore_drill","outcome":"failed","category":"no_export"}'; exit 1; }

az storage blob download --auth-mode login --account-name "$account" --container-name "$container" \
  --name "$manifest" --file "$work/manifest.json" --no-progress -o none
dump="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["dump"])' "$work/manifest.json")"
az storage blob download --auth-mode login --account-name "$account" --container-name "$container" \
  --name "$dump" --file "$work/newsloom.dump" --no-progress -o none

"$engine" run -d --rm --name "$name" -e POSTGRES_HOST_AUTH_METHOD=trust "$image" > /dev/null
for _ in $(seq 1 30); do
  "$engine" exec "$name" pg_isready -U postgres -q && break
  sleep 1
done
"$engine" cp "$work/newsloom.dump" "$name:/tmp/newsloom.dump"
"$engine" exec "$name" createdb -U postgres newsloom
"$engine" exec "$name" pg_restore -U postgres -d newsloom --no-owner --no-privileges --clean --if-exists \
  --exit-on-error /tmp/newsloom.dump
"$engine" exec "$name" psql -U postgres -d newsloom -At -F ' ' -c "
  SELECT schemaname || '.' || tablename,
         (xpath('/row/c/text()', query_to_xml(
           format('SELECT count(*) AS c FROM %I.%I', schemaname, tablename), false, true, '')))[1]::text
  FROM pg_tables WHERE schemaname IN ('public', 'newsloom_admin')" > "$work/restored.txt"

python3 - "$work/manifest.json" "$work/newsloom.dump" "$work/restored.txt" "$manifest" <<'PY'
import hashlib, json, sys
manifest = json.load(open(sys.argv[1]))
digest = hashlib.sha256(open(sys.argv[2], "rb").read()).hexdigest()
restored = dict(line.split(" ") for line in open(sys.argv[3]).read().split("\n") if line)
restored = {table: int(count) for table, count in restored.items()}
expected = manifest["tables"]
result = {
    "event": "restore_drill",
    "export": sys.argv[4],
    "checksum_match": digest == manifest["sha256"],
    "tables": len(expected),
    "rows": sum(expected.values()),
    "mismatched_tables": sorted(t for t in expected if restored.get(t) != expected[t]),
}
result["outcome"] = "success" if result["checksum_match"] and not result["mismatched_tables"] else "failed"
print(json.dumps(result))
sys.exit(result["outcome"] != "success")
PY
