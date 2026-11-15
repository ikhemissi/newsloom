# Design

## Context

The `snapshot` job in the `mcp` layer runs `newsloom-mcp snapshot` at
`45 22 * * *`. Ingestion and enrichment run at `10,40 7-22 * * *`; the database
stops at 23:00 and wakes at 07:00 UTC. While the API serves from the snapshot it
re-checks the blob ETag every 10 minutes and reloads it when it changed.

## Decisions

- **Cron `15,45 7-22 * * *`** on the existing job. Container Apps cron has one
  expression and no time zone; this one keeps the 22:45 final run and never
  starts before the 07:00 wake. `:25/:55` was rejected: its last run (22:55) can
  overlap the 23:00 stop and lose the 22:40 data.
- **No code change.** The builder already reads in one repeatable-read,
  read-only transaction, retries once after 60 s on a connection failure and
  overwrites `latest.json.gz`; overlapping runs are impossible because a run takes
  about 40 s.
- **No new resource or grant.** The lifecycle rule (delete after 7 days without
  update) keeps working because each run updates the blob.

## Risks

- **A failed daytime run** leaves the previous snapshot in place; the next run
  replaces it. Failures appear in the job history like today's nightly failures.
- **Database load:** a 40 s read every 30 minutes; acceptable for the current
  server. Revisit if snapshot runs grow beyond a few minutes.
