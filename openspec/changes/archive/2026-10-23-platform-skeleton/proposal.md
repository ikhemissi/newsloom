# Proposal

## Why

Bootstrap now provides verified state storage, tooling, and native azd layers,
but no Newsloom application infrastructure exists. PRD-1 Step 1.1 needs a real,
persistent Azure foundation before ingestion, enrichment, and MCP can be delivered.

## What Changes

- Own the foundations of PRD-1 capabilities P1-C08, P1-C09, and P1-C10.
  Prerequisite: the accepted, archived bootstrap change and its existing `dev`
  azd environment, RBAC backend, and local state.
- Provision the application resource group, ACR, Container Apps environment,
  PostgreSQL 18 database, one Foundry AIServices account with the three required
  model deployments, Log Analytics, and Application Insights.
- Create distinct ingestion, enrichment, and MCP managed identities with
  resource-scoped grants, plus a separate migration identity and a real,
  manually triggered database migration job.
- Initialize pgvector and workload database principals through that migration
  job, not Terraform SQL provisioners or application startup. Domain tables,
  queue logic, and their later data-access grants stay with their owning slices.
- Export discoverable application outputs and add an Azure smoke check that
  verifies Newsloom's resources, identity boundaries, model contracts, and telemetry
  rather than testing azd internals.
- Keep all provisioning behind native azd in the existing environment. Preserve
  state and existing resource IDs; continue passing common tags through variables.
  The current tenant's two policy-control tags remain deployment configuration,
  not product requirements.

Out of scope: scheduled ingestion/enrichment workloads, the MCP HTTP service,
user sign-in implementation, scanner calibration, domain schema and news data,
Phase 2/3 services, private networking, and a UI. No fake application containers
or successful placeholder jobs are introduced.

## Capabilities

### New Capabilities

- `persistent-azure-platform`: provisioned shared Azure resources, usable database
  and model deployments, discoverable configuration, and safe incremental updates.
- `workload-access`: Entra-only platform access, distinct workload identities,
  isolated migration authority, and an inspectable least-privilege grant inventory.
- `safe-telemetry`: operational sinks that require Entra authentication and accept
  only bounded, content-free platform verification telemetry.

### Modified Capabilities

None. The delivered repository-foundation contract remains unchanged.

## Impact

- Changes will primarily affect the application Terraform root, azd hooks/outputs,
  a minimal migration image and versioned migrations, Azure verification tooling,
  focused infrastructure tests, and the deployment documentation.
- Proposed application group: `rg-newsloom-dev`, distinct from state storage.
  Use France Central, where the required resource types, PostgreSQL 18/SKUs,
  models, and positive quotas were checked on 2026-10-22; refresh capacity before
  applying. These checks are not proof of actual application provisioning.
- Resolve the final PostgreSQL SKU and model capacities from current availability
  and an itemized cost estimate before deployment. B1ms is a low-cost candidate,
  not a requirement; do not silently select more expensive capacity or a new region.
- Establish the migration identity as the database administrator and validate
  the supported Foundry inference roles/scopes. Stop for missing provisioning
  permissions or unsupported privilege separation rather than enabling keys or
  granting broad subscription access.
- The scanner model's advertised inference retirement is 2027-02-04. Preserve
  the ADR-6 replacement risk; this change does not invent or deploy a substitute.
