# Proposal

## Why

Newsloom's ingestion, enrichment and MCP slices are individually verified, but
[PRD-1 Step 1.6](../../../docs/prd-1.md#delivery-plan) still lacks a repeatable
federated Azure integration run tying their real processing paths together.
Phase 2 needs that evidence without injecting fixtures into production news or
disturbing the live schedules.

The conditional log-only correction is deployed and its dedicated-identity
boundary is verified, but the corrected workflow still failed. Its final report
arrived 271 seconds after emission, beyond the 240-second post-terminal
allowance; startup plus cleanup evidence also exceeded the recovery allowance.
The separate generic cleanup error does not establish its underlying cause.
The next correction concerns bounded evidence timing and safe diagnostics, not
broader permissions or repeated model tuning.

## What Changes

- Deliver [P1-C11](../../../docs/prd-1-capabilities.md#p1-c11-evidence-based-platform-acceptance)
  with a bounded, manually dispatched GitHub Actions workflow authenticated by
  OIDC, a dedicated acceptance identity and one manual Container Apps test job.
  The user explicitly approved this isolated scope during planning.
- Prepare an exact-named disposable database on the existing PostgreSQL server
  through the retained migration authority. Give the test identity access and
  cleanup ownership only there, never production database access, another
  workload's role, database-creation privileges or migration administration.
- Freeze a tiny authored RSS/Atom corpus: two benign items and two direct/
  indirect hostile items. Use the real parser, calibrated Decision scanner,
  durable repositories, enrichment/embedding adapters and MCP query path.
  Verify actual quarantine, duplicate-free replay, concurrent distinct claims,
  process-loss recovery using the natural lease, and final stored search results.
- Prove cleanup on success/failure/cancellation and retain content-free,
  fingerprinted per-stage evidence. No missing stage or cleanup failure may
  become a passing phase report.
- Use the deployed bounded, exact-execution Log Analytics query path and its
  one conditional Log Analytics Data Reader assignment at the existing workspace.
  Dedicated-identity tests proved the server-enforced table/job/environment
  boundary, including unfiltered and foreign-data queries. Workspace metadata
  reads are permitted, not unrelated log data; preserve the reviewed condition
  and absence of development-token/exec permissions.
- Plan one non-resettable controller deadline inside the unchanged 30-minute
  workflow. Accommodate measured checkpoint/report/cleanup delivery without
  increasing the 1,200-second job ceiling or shortening the natural lease.
  Keep all polling and read-only timeout retries inside the remaining budget.
  Use fixed privacy-safe transport/response categories; do not replay uncertain
  job starts or turn operator readbacks into automatic workflow proof.
- Reconcile phase acceptance against the already delivered local adversarial,
  scanner, enrichment, retrieval and native-user evidence. Keep those
  measurements distinct from this small integration corpus rather than
  relabelling a smoke test as a replacement quality study.
- Preserve the existing database, identities, model deployments, MCP service,
  schedules and quarantine/dead-letter history. Leave the completed enrichment
  and MCP changes unarchived unless separately requested.

Out of scope: Phase 2/OBO/agents, public test endpoints, new servers or models,
automatic cloud tests on pull requests, production fixtures, production fault
injection, data repair/releases, scanner/prompt/taxonomy tuning, privileged
GitHub deployment access, and broad firewall or consent changes.

Prerequisites are the delivered
[platform](../../specs/persistent-azure-platform/spec.md),
[ingestion](../archive/2026-10-23-feed-ingestion/tasks.md#acceptance-evidence),
[contextual screening](../archive/2026-10-23-contextual-content-screening/tasks.md),
[enrichment](../enrichment/tasks.md#acceptance-evidence), and
[MCP](../mcp-server/tasks.md#acceptance-evidence) acceptance. No prior result is
invented, reset or silently substituted by the new workflow.

## Capabilities

### New Capabilities

- `phase1-acceptance`: isolated, secretless, repeatable integration execution,
  bounded cross-stage fixture/recovery checks, verified cleanup and honest
  phase-readiness evidence.

### Modified Capabilities

None. Existing workload authentication, production isolation and safe telemetry
remain prerequisites; this slice adds test orchestration, not new business APIs
or relaxed production contracts.

## Impact

- Add a test-only harness/image and focused tests reusing existing service
  modules. Keep its orchestration and dependencies out of production startup;
  do not implement parallel scanner/enrichment/search logic.
- Extend owning platform operator helpers for explicit database preparation and
  recovery cleanup. Add separate acceptance bootstrap migrations; never replay
  the production principal migration or hard-coded production database grants
  against a test target.
- Add an opt-in owning azd/Terraform layer for the dedicated identity, exact
  GitHub federation, immutable manual test job and narrow grants. Reuse the
  existing registry, server, Container Apps environment and three model
  deployments. The planned log correction adds only one conditional reader
  assignment on the existing workspace and removes the unused job-logstream
  data grant. It adds no workspace, development-token/exec permission,
  unconditional log-data access or subscription/resource-group
  Contributor/Owner grant.
- Keep the repository private on the user's personal GitHub Free plan. Explicit
  manual dispatch is the operator approval; there is no separate environment
  reviewer gate. Bind OIDC to this repository's immutable owner/repository IDs
  and exact `main` branch using GitHub's current default subject format. Replace
  the obsolete name-only credential rather than retaining it as a fallback;
  do not change GitHub's OIDC policy or add another credential. Keep
  tenant/subscription/client/resource identifiers in repository-level variables
  and ignored local configuration, never committed code. Use no stored Azure
  credential or user bearer token.
- This lean policy was explicitly approved after confirming that required
  environment reviewers are unavailable for a private repository on this plan.
  Other refs, pull requests, forks and automatic cloud dispatch remain forbidden.
  Keep repository/main write access tightly limited; the policy is not
  independent two-person review and does not authenticate a workflow filename.
- GitHub requires a new manual workflow on the default branch before its first
  dispatch. The user explicitly approved a narrow, locally validated
  workflow/controller bootstrap commit before that first Azure run, with
  cloud/phase acceptance left unchecked. This is not permission to skip final
  Azure verification or commit unverified product behavior.
- Operator review must establish the exact OIDC trust, narrow job/query APIs,
  test-database ownership/cleanup under Azure PostgreSQL, model scope support,
  retained regional capacity/quota and metered cost before applying anything.
  Missing capabilities block acceptance; they do not authorize broader grants,
  password authentication, new model capacity or production-role inheritance.
- Azure Monitor must enforce the conditional log-data boundary independently of
  query text. Verify actual dedicated-identity access to its own records and
  denial of foreign-job/table data, including queries without client filters.
  Log-delivery latency must fit finite workflow/recovery budgets; missing or
  late evidence remains a failure, not a fallback to broader log access.
- The timing correction changes only the standalone launcher/workflow/tests and
  directly related documentation. It requires no new grant, resource, image,
  model, workspace policy or production change. Review exact timing in the
  design before implementation; the generic cleanup failure must not be
  retrospectively labelled as a proven timeout.
- Validate another isolated corrective bootstrap and its exact-SHA offline CI
  before dispatch. Preserve all three failed workflows and independent cleanup
  evidence. Use fresh prepared databases for acceptance and both negative
  drills; keep actual identity/processing/cleanup gates incomplete until proven.
- A database consumes shared server storage/CPU and model calls share quota.
  The manual job incurs compute only while running; retain no additional
  always-on app. Refresh actual rates/limits and verify existing services before
  deployment. Full local, reviewed azd, real federated-run and exact-commit CI
  evidence are required before declaring Step 1.6 complete.
