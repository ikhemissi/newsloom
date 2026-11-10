# Tasks

## 1. Service

- [x] 1.1 Add `services/operations` (`newsloom-operations`): `backup`, `stop-database`, `start-database`, `restore-tags`, `nightly`, `wake`; image with `postgresql-client-18`; unit tests with fake Azure and a real local dump against the test database.

## 2. Infrastructure

- [x] 2.1 Add the `operations-identity` layer (identity, roles, storage with immutability and lifecycle, locks) and the `operations` layer (nightly and wake jobs) with Terraform tests; platform build and prepare commands.
- [x] 2.2 Migrations: create the operations principal and re-apply read-only grants on every run; tests.
- [x] 2.3 New schedules for ingestion, enrichment and the briefing, with tests and readbacks updated.

## 3. Deliver

- [ ] 3.1 Add `docs/operations.md` (backup, restore drill, operating window), update the platform runbook and briefing docs; `scripts/restore-drill.sh`; run `bash scripts/check.sh --all` and `npm run spec:check`.
- [ ] 3.2 Deploy through azd previews; run the first backup manually and the restore drill; record evidence; confirm one nightly stop and morning wake.
