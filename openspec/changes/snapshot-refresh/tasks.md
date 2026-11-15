# Tasks

## 1. Infrastructure

- [ ] 1.1 Change the `snapshot` job cron in the `mcp` layer to `15,45 7-22 * * *` and update its Terraform test.

## 2. Deliver

- [ ] 2.1 Update `docs/operations.md` and `docs/news-api.md`; run `bash scripts/check.sh` and `npm run spec:check`.
- [ ] 2.2 Deploy the `mcp` layer through an azd preview showing only the cron change; record the next scheduled runs.
