# Design

## Context

PostgreSQL 18 Flexible Server with Entra-only authentication; the migrations
identity is the only administrator and applies checksum-tracked migrations.
Jobs run in the Container Apps environment and reach the server through the
`AllowAzureServices` firewall rule. Every layer is Terraform under azd with
remote state; tenant governance acts on resources that lack the two tags.

## Decisions

- **Service `newsloom-operations`** (Python 3.15, `postgresql-client-18` from
  the PostgreSQL apt repository). Commands:
  - `backup`: Entra token for the operations identity, `pg_dump --format=custom`
    streamed to a block blob while hashing; then a manifest blob with UTC time,
    server and client versions, byte size, SHA-256 and exact row counts per
    table. Blob names `postgres/YYYY/MM/DD/<timestamp>.dump` and `.json`.
    A failed dump never writes a manifest.
  - `stop-database` / `start-database`: Azure Resource Manager start/stop and
    wait for the target state; already in that state is a success.
  - `restore-tags`: merge `CostControl=Ignore` and `SecurityControl=Ignore`
    onto the resource group and every resource in it that lacks either; never
    removes or changes other tags.
  - `nightly` = `backup` then `stop-database` (stops even if the backup failed,
    and exits non-zero then); `wake` = `start-database` then `restore-tags`
    (tagging a stopped server fails). A manual-only `backup` job exports on
    demand with the same settings.
  Logs are content-free events (counts, sizes, outcomes).
- **Database access:** migrations create the principal and grant `CONNECT`,
  `USAGE` on `public`, `SELECT` on all tables and sequences, and default
  privileges for future tables created by the migrations role. The grants are
  re-applied on every migration run. Azure does not let the administrator grant
  `pg_read_all_data`.
- **Storage:** StorageV2, ZRS, shared keys disabled, TLS 1.2, no anonymous
  access; container `postgres` with an unlocked 30-day time-based immutability
  policy; blob and container soft delete 14 days; lifecycle delete after 60 days.
  Public network access stays enabled because the environment has no virtual
  network; access is Entra-only. The deploying operator receives Storage Blob
  Data Reader on the container for restore drills.
- **Layers:** `operations-identity` (identity, custom start/stop role, role
  assignments, storage, locks) → `migrations` (principal and grants) →
  `operations` (nightly and wake schedules, manual backup). Locks: `CanNotDelete` on the server and
  the storage account.
- **Schedules (UTC; Container Apps cron has no time zone):** nightly `0 23 * * *`,
  wake `0 7 * * *`, ingestion and enrichment `10,40 7-22 * * *`, briefing
  `45 7 * * *`. In summer every time moves one hour later in Paris.

## Risks

- A long dump could delay the stop; the job timeout is 60 minutes and the
  current database is small.
- While the server sleeps the web app shows errors; the read-only cache change
  addresses this.
- Governance may still stop the server or remove tags during the day; the next
  wake or a manual `wake` run repairs it.
