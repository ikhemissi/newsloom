# Proposal

## Why

On 2026-11-09 the tenant's governance automation stopped the PostgreSQL server
and removed the `CostControl`/`SecurityControl` tags from most resources, which
took the site down until an operator restarted the server. Reader state,
feedback, triage and extraction results and some article text cannot be rebuilt
from feeds. There is no copy of the data outside the server, and the server runs
around the clock although nobody reads Newsloom at night.

## What Changes

- **Daily database export (user decision 2026-11-10: daily, as soon as possible).**
  A nightly job streams a `pg_dump` custom-format archive of the application
  database to a dedicated storage account, with a manifest (size, SHA-256,
  row count per table). Blobs cannot be overwritten or deleted for 30 days;
  soft delete and a lifecycle rule keep about 60 days.
- **Hardening.** Delete locks on the PostgreSQL server and the backup storage
  account; built-in point-in-time backup retention raised from 7 to 35 days
  (applied 2026-11-10 as a configuration change).
- **Operating window (user decision 2026-11-10).** The nightly job takes the
  export at 23:00 UTC (00:00 Paris in winter) and then stops the server. A wake
  job at 07:00 UTC starts the server, then restores the two governance tags on
  resources that lost them. A manual-only job takes an export on demand. Ingestion and enrichment run every 30 minutes
  from 07:10 to 22:40 UTC; the briefing starts at 07:45 UTC and keeps its
  05:00 UTC slot and cutoff.
- **State storage repair (user decision 2026-11-10).** Governance also removes the
  tags from the Terraform state storage and disables its public network access,
  which blocks every deployment. The wake job also merges the tags onto the state
  resource group and re-enables public network access on the state account.
- **Restore drill.** An operator script restores the latest export into a local
  PostgreSQL container and compares row counts with the manifest.

Owning slice: platform operations (PRD-1 persistent platform).

Out of scope: serving cached data read-only while the database sleeps (separate
change, requested 2026-11-10); geo-redundant server backups (only selectable at
server creation); alerting.

Decisions surfaced:
- **Own export instead of a Backup vault:** gives a portable copy in our own
  storage account, restorable anywhere with standard tools.
- **One operations identity** with read-only database access, blob write on one
  container, start/stop/read on one server and tag write on the resource group.
  The tag grant only merges the two tags that every deployment already sets.
- **Cost:** about €1–2/month (ZRS storage, two short jobs); the server stops
  for 8 hours a night, which saves compute.
