# Design

## Context

The MCP app serves the HTTP news API and MCP tools through `Services`, whose
stores (`NewsRepository`, `RadarStore`, briefing reader, `FeedbackStore`) open a
database connection per request. With the server stopped every request waits
for the 10-second connect timeout and fails; readiness fails too, so the app
loses traffic.

## Decisions

- **Snapshot model** (`newsloom_mcp.snapshot`): `as_of`, `items` (news detail
  with announcements), `cards` (radar cards, published in the last 30 days,
  without reader state), `products` (`ProductDetail` for every product on those
  cards), `stacks` and `stack_entries` (reader key → followed entity IDs, and
  the entities), `states` (reader key → announcement → state and snooze end),
  `briefing` (`BriefingRead` at snapshot time). Gzip JSON, validated with the
  same Pydantic contracts on load; a few MB.
- **Builder:** `newsloom-mcp snapshot` reads in one repeatable-read, read-only
  transaction as `newsloom_mcp` and uploads `latest.json.gz` (overwritten) to the
  `snapshots` container. Scheduled `45 22 * * *` UTC in the `mcp` layer, after
  the last ingestion run and before the 23:00 stop.
- **Stores:** `SnapshotNews` (browse/recent/detail/sources in memory with the
  same filters and newest-first continuation; search raises `ReadOnly`),
  `SnapshotRadar` (applies the reader's states and stack to cards, then the
  existing `rank()`; product pages from the snapshot; writes and entity search
  raise `ReadOnly`), briefing from the snapshot, feedback raises `ReadOnly`.
- **Fallback:** a `Fallback` object in the runtime remembers a database
  connection failure for 5 minutes. Each store factory tries the database unless
  the failure is remembered; on a connection error it records the failure and
  yields the snapshot store. The snapshot is downloaded on first need and
  re-read when its ETag changes (checked at most every 10 minutes).
- **Readiness:** ready if the database answers within 4 seconds, else if a
  snapshot is loaded.
- **HTTP:** `ReadOnly` → `503 {"error":{"code":"read_only"}}`. While the fallback
  is active every API response carries `X-Newsloom-Read-Only` with the snapshot
  time, exposed to the browser through CORS.
- **Browser:** `guardedFetch` reports the header to a small read-only store and
  maps a 503 carrying it to a `read_only` failure. The app shows one line and
  hides search, the research panel and Ask buttons, feedback, card actions,
  follow toggles and stack editing while read-only.

## Risks

- The snapshot is up to 8 hours old at 07:00; the line states its time.
- If the snapshot job fails, the API has no fallback and shows errors overnight
  as today; the job failure is visible in its logs.
