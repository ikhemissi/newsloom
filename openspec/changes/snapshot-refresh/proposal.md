# Proposal

## Why

The read snapshot is written once a day at 22:45 UTC, so when the API has to
serve from it, it shows the state of the previous evening. The user asked for
the snapshot to be refreshed after each enrichment run so the read-only data
stays fresh whenever the database is unavailable, not only overnight
(2026-11-15).

## What Changes

- **Refresh after each enrichment run (user decision 2026-11-15: schedule the
  existing job rather than chain it to enrichment).** The existing
  `snapshot-newsloom-<env>` job runs at 07:15 UTC and then every 30 minutes until
  22:45 UTC (`15,45 7-22 * * *`), five minutes after each ingestion and
  enrichment start (`10,40 7-22 * * *`). The last refresh stays at 22:45, before
  the 23:00 stop.
- Nothing else changes: same image, identity, grant, contents, blob name and
  read-only behaviour. While serving from the snapshot the API already reloads
  it when its ETag changes (every 10 minutes), so a refresh reaches readers
  without a restart.

Owning slice: PRD-3 product experience; modifies `overnight-read-only`.

Out of scope: serving from the snapshot when the database is reachable but slow
(the fallback still starts on connection failures); chaining the snapshot to
the end of enrichment (needs a new storage grant for the enrichment identity).

Decisions surfaced:
- **Fixed offset rather than chaining:** enrichment took at most 71 s in its last
  100 runs (median about 30 s), so a five-minute offset normally captures the
  run that just finished. If a run is still going, the snapshot captures the
  previous state and the next refresh catches up.
- **Cost and load:** 32 runs a day instead of one, each about 40 s reading in
  one read-only transaction and writing about 1.3 MB to the same blob. Job
  compute stays within a few minutes a day; storage is unchanged.
