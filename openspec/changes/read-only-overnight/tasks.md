# Tasks

## 1. API

- [x] 1.1 Snapshot model, builder query and `newsloom-mcp snapshot` command; tests against the local database (contents, no embeddings, round trip).
- [x] 1.2 Snapshot stores (news, radar, briefing, feedback) with tests that compare them with the database stores on the same data.
- [x] 1.3 Fallback in the runtime (remembered failure, ETag reload, readiness), `ReadOnly` → `503 read_only`, read-only header with CORS exposure; tests.

## 2. Infrastructure

- [x] 2.1 `snapshots` container (7-day lifecycle) and the MCP identity's blob grant; the snapshot job (`45 22 * * *`) and app settings in the `mcp` layer; Terraform tests.

## 3. Web

- [x] 3.1 Read-only store fed by `guardedFetch`, `read_only` failure, the one-line notice and hidden actions; component and browser tests.

## 4. Deliver

- [x] 4.1 Update `docs/operations.md`, `docs/news-api.md`, `docs/ui.md`; run `bash scripts/check.sh --all` and `npm run spec:check`.
- [ ] 4.2 Deploy through azd previews; run the snapshot job; check the site with the database stopped (manual stop/start); user checks at night.
