# Tasks

## 1. Infrastructure

- [x] 1.1 Change the `snapshot` job cron in the `mcp` layer to `15,45 7-22 * * *` and update its Terraform test.

## 2. Deliver

- [x] 2.1 Update `docs/operations.md` and `docs/news-api.md`; run `bash scripts/check.sh` and `npm run spec:check`.
- [x] 2.2 Deploy the `mcp` layer through an azd preview showing only the cron change; record the next scheduled runs.
  - Evidence (2026-11-15): merged in #41 after local checks (`scripts/check.sh`, 14 mcp Terraform tests, `spec:check`) and green CI. The `mcp` preview showed 2 in-place changes: the snapshot cron `45 22 * * *` → `15,45 7-22 * * *` and the two governance tags the tenant policy had removed from the app; applied. Read back: the job cron is `15,45 7-22 * * *`; revision 13 is healthy with all traffic; `verify-mcp` succeeded. The first scheduled runs on the new cron are tomorrow from 07:15 UTC.
  - Scheduled runs (2026-11-16): 07:15, 07:45 and 08:15 UTC succeeded on the new cron (2,419–2,420 items, 1,315–1,316 cards, 941–942 products, about 1.29 MB each); the 22:15 and 22:45 runs of 11-15 also succeeded before the 23:00 stop.
