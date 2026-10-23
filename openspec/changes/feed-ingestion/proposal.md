# Proposal

## Why

The shared Azure platform is verified, but no job retrieves or stores feed entries.
Deliver one working ingestion path, test its logic locally on one RSS and one Atom
feed, then start it immediately in Azure against the full catalogue.

## What Changes

- Own PRD-1 Steps 1.2 and 1.3 together, as explicitly approved: source curation,
  safe retrieval/normalization, durable ingestion, real content screening,
  quarantine, and ingestion/scanner instrumentation. Prerequisite: the
  [accepted platform](../archive/2026-10-23-platform-skeleton/tasks.md#acceptance-evidence).
  Update the phase delivery assignments during implementation to reflect this
  combined slice rather than leave a duplicate future scanner delivery.
- Implement the existing ingestion package as an async ACA job. Read the existing
  catalogue, support explicit source selection and `--force`, and retain the
  approved `*/30 * * * *` UTC schedule plus immediate manual execution.
- Add versioned migrations for `feed_sources`, `ingestion_queue`, and `quarantine`
  in the existing database, with only the ingestion identity's required grants.
  Accepted entries become pending work; rejected entries are retained separately.
  Scanner failures remain distinguishable from rejections and retryable.
- Call the existing Microsoft-Decision-1 deployment through a small typed scanner
  interface; calibrate its threshold with labelled examples before live acceptance.
  There is no deployed no-op scanner, bypass flag, or success fallback.
- Reuse the existing registry, identities, model account, database migration job,
  telemetry, and azd build/execution helpers. Add only the real ingestion job and
  its minimal dependent Terraform layer; preserve shared resources and state.
- Validate using fixtures and a disposable local PostgreSQL database. The local
  live smoke test retrieves only one configured RSS and one configured Atom feed;
  do not scan the full catalogue locally or in CI.
- After deployment, manually start the Azure job immediately on the full
  catalogue. Verify terminal status and actual database rows/counts, then repeat
  with forced retrieval to verify idempotency. A healthy-looking log or a cron
  schedule alone is not acceptance.

Out of scope: GPT summaries/categories/tags, embeddings, enrichment queue claims
and leases, the `news` table, MCP, UI, additional cloud services, and Phase 1-wide
acceptance. Test doubles are limited to automated tests.

## Capabilities

### New Capabilities

- `feed-ingestion`: bounded RSS/Atom retrieval and normalization, configuration
  filters, durable source state and entry deduplication, real scheduled/manual
  execution, safe diagnostics, and evidence of database persistence.
- `content-screening`: real Decision-model admission, calibrated decisions,
  fail-closed retries, retained quarantine, and no runtime screening bypass.

### Modified Capabilities

None. This adds runtime behavior on top of the delivered platform, access, and
telemetry contracts without weakening their authentication or preservation rules.

## Impact

- Extend `services/ingestion`, the existing core feed types where shared, platform
  migrations/operator helpers, focused tests/fixtures, image context, azd/Terraform,
  and directly related runbooks/phase documentation.
- Add only dependencies needed for async protected retrieval, safe XML parsing,
  managed identity, and PostgreSQL access. Keep Python 3.15 and the locked workspace.
- Use the persistent `dev` environment in France Central and existing
  ingestion/migration identities. No new administrator, developer database role,
  network exception, keys, or tenant tag requirements.
- Preserve the approved operating budgets in the design. Refresh actual Decision
  availability/quota/lifecycle before use; keep its existing capacity and
  configured rate limit. Its advertised retirement is 2027-02-04; do not substitute
  a model or increase capacity silently.
- Threshold selection remains an empirical implementation gate, not an invented
  value in this proposal. Record labelled calibration/validation results and
  observed model/ACA usage; no new fixed-cost service is proposed.
