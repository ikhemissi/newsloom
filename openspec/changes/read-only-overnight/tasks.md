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
  - Evidence (2026-11-10): `operations-identity` preview added the `snapshots` container and grant and only appended the snapshot lifecycle rule (read back: exports 60 days after creation, snapshots 7 days after modification). `mcp` preview: image, `SNAPSHOT_URL` and the new job; revision 11 ready, `verify-mcp` succeeded. Web revision 18, `verify-ui` succeeded. Manual snapshot `snapshot-newsloom-dev-dwygk5e`: 2,311 items, 1,163 cards, 839 products, briefing included, 1,132,672 bytes. With the server stopped by the operator, `/health/ready` answered 200 in about 0.1 s and the user confirmed the read-only line, readable radar, briefing, news, item and product pages and hidden actions; the server was then started again.
  - Open: observe the scheduled 22:45 UTC snapshot and the site during the scheduled night stop.
