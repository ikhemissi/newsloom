# Tasks

## 1. Service

- [x] 1.1 Add `services/operations` (`newsloom-operations`): `backup`, `stop-database`, `start-database`, `restore-tags`, `nightly`, `wake`; image with `postgresql-client-18`; unit tests with fake Azure and a real local dump against the test database.

## 2. Infrastructure

- [x] 2.1 Add the `operations-identity` layer (identity, roles, storage with immutability and lifecycle, locks) and the `operations` layer (nightly and wake jobs) with Terraform tests; platform build and prepare commands.
- [x] 2.2 Migrations: create the operations principal and re-apply read-only grants on every run; tests.
- [x] 2.3 New schedules for ingestion, enrichment and the briefing, with tests and readbacks updated.

## 3. Deliver

- [x] 3.1 Add `docs/operations.md` (backup, restore drill, operating window), update the platform runbook and briefing docs; `scripts/restore-drill.sh`; run `bash scripts/check.sh --all` and `npm run spec:check`.
- [ ] 3.2 Deploy through azd previews; run the first backup manually and the restore drill; record evidence; confirm one nightly stop and morning wake.
  - Evidence so far (2026-11-10): `POSTGRES_BACKUP_DAYS` 7 → 35 applied through an application-layer preview showing only that change. `operations-identity` applied (13 additions, no changes); migrations created `newsloom_operations` (execution succeeded); `operations` applied (three jobs). The first live backup failed with a missing `aiohttp` (fixed in #23, now checked at image build). Manual backup `backup-newsloom-dev-favx0wt` succeeded: 25,856,765 bytes, 19 tables, 12,359 rows. Restore drill of `postgres/2026/11/10/newsloom-20261110T130543Z`: checksum match, 0 mismatched tables. Readback: ZRS, shared keys off, no anonymous access, 30-day unlocked immutability, both delete locks, retention 35 days. Schedules read back: ingest/enrich `10,40 7-22 * * *`, brief `45 7 * * *`, nightly `0 23 * * *`, wake `0 7 * * *`.
  - Open: observe the first nightly export and stop (23:00 UTC) and the morning wake (07:00 UTC).
