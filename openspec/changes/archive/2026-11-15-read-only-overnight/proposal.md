# Proposal

## Why

The database now sleeps from 23:00 to 07:00 UTC (`nightly-operations`), and the
site shows errors overnight. The user asked to keep serving data read-only from
a cache instead (2026-11-10).

## What Changes

- **Nightly snapshot (user decision 2026-11-10: once, just before the stop).**
  A scheduled job runs the API's own image and identity at 22:45 UTC and writes
  one compressed snapshot to a `snapshots` container: every news item with its
  detail and announcements, radar cards of the last 30 days, product pages for
  those cards, the current briefing and, per pseudonymous reader key, the
  followed stack and card states. No embeddings, tokens or article bodies.
- **Read-only serving.** When the database cannot be reached, the API serves
  the radar, briefing, news list and filters, item detail, sources and product
  pages from the latest snapshot, computing each reader's radar with the same
  ranking code. A failed connection is remembered for five minutes so requests
  do not wait for timeouts, and readiness stays green while a snapshot is
  loaded. Responses from the snapshot carry `X-Newsloom-Read-Only: <as-of>`.
- **Unavailable overnight (user decision):** search, research, feedback, and
  follow/snooze/done/stack edits return `503 read_only`.
- **Browser.** One line, "Read-only until 08:00 · data as of 23:45", and the
  actions above are hidden while it shows.

Owning slice: PRD-3 product experience; extends `nightly-operations`.

Out of scope: refreshing the snapshot during the day; serving research from
the snapshot; queuing overnight writes for replay.

Decisions surfaced:
- **Snapshot in blob storage, loaded by the API**, rather than an always-on
  database or a per-replica response cache: survives restarts and scale-out and
  needs no new compute.
- **Grants:** the MCP identity gains Storage Blob Data Contributor on the new
  `snapshots` container only. The container has no immutability and keeps
  snapshots 7 days.
- **Cost:** negligible (one short job, a few MB of storage).
