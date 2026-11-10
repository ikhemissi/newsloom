# Nightly operations runbook

Status: in delivery through the
[owning change](../openspec/changes/nightly-operations/proposal.md). It protects
the data against loss and runs the database only during the day.

## What runs when

All schedules are UTC because Container Apps cron has no time zone. In summer
every time moves one hour later in Paris.

| UTC | Paris (winter) | Job |
| --- | --- | --- |
| 07:00 | 08:00 | `wake`: start PostgreSQL, then put back the governance tags |
| 07:10–22:40, every 30 min | 08:10–23:40 | ingestion and enrichment |
| 07:45 | 08:45 | briefing for the 05:00 UTC slot ([briefing runbook](briefing.md)) |
| 23:00 | 00:00 | `nightly`: export the database, then stop PostgreSQL |

While the server is stopped the web app and API return errors; a read-only
overnight mode is a [known gap](known-gaps.md).

## Exports

The `nightly` job runs `pg_dump --format=custom` of the `public` and
`newsloom_admin` schemas (with the `vector` extension) as the read-only
`newsloom_operations` role. It streams the archive to the `postgres` container
of the backup storage account as `postgres/YYYY/MM/DD/newsloom-<time>.dump` and
then writes `<same name>.json`: the byte size, SHA-256 and the row count per
table, counted in the same database snapshot as the dump. A failed dump never
writes a manifest, and the server is stopped anyway.

- Blobs cannot be overwritten or deleted for 30 days (unlocked time-based
  immutability policy); a lifecycle rule deletes them after 60 days.
- The account accepts Entra only (no shared keys) and no anonymous access.
- PostgreSQL keeps its own point-in-time backups for 35 days
  (`POSTGRES_BACKUP_DAYS`).
- `CanNotDelete` locks protect the server and the backup account. Remove a
  lock deliberately, through the owning layer, before any planned deletion.

## Governance tags

The tenant's governance automation stops resources and removes the
`CostControl`/`SecurityControl` tags when it considers them unexempted (see
[platform notes](platform-notes.md#governance-automation-2026-11-10)). The
`wake` job merges both tags back onto the resource group and every resource in
it that lacks them, using Tag Contributor on the resource group; it never
removes or changes other tags. It starts the server first, because tagging a
stopped server fails.

## Deploy

Provision in this order, reviewing every preview:

```bash
azd provision operations-identity --preview   # identity, storage, roles, locks
azd provision operations-identity
azd provision migrations --preview            # adds the operations principal and grants
azd provision migrations
uv run --locked newsloom-platform build-operations
azd provision operations --preview            # nightly and wake jobs
azd provision operations
```

The migration job re-applies the read-only grants on every run, so tables added
by later migrations are exported without further changes.

## Run now

The manual-only `backup` job exports without stopping the server; the
scheduled jobs can also be started by hand (`wake` repairs a server that
governance stopped during the day):

```bash
az containerapp job start -g "$(azd env get-value AZURE_RESOURCE_GROUP)" \
  -n "$(azd env get-value OPERATIONS_BACKUP_JOB_NAME)"   # or ..._WAKE_JOB_NAME
```

Each step logs one content-free event: `database_backup`
(bytes, tables, rows), `database_power` or `governance_tags` (resources,
tagged, failed), and a final `operations` outcome.

## Restore drill

```bash
bash scripts/restore-drill.sh            # latest export
bash scripts/restore-drill.sh <manifest> # a given postgres/.../*.json
```

The script downloads the export with the operator's Entra sign-in (Storage Blob
Data Reader on the container, granted to the deploying operator), checks the
SHA-256, restores it into a throwaway `pgvector/pgvector:pg18` container with
`pg_restore --no-owner --no-privileges --clean --if-exists` and compares every
table's row count with the manifest. It deletes the downloaded data on exit and
prints one `restore_drill` result.

To restore into Azure, create a new server or database, enable the `vector`
extension and run the same `pg_restore`; then rerun migrations so roles and
grants are recreated.
