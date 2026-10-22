# Design

## Context

See [the proposal](proposal.md) for scope and capability ownership. The existing
application Terraform root contains only common tags and a location output.
Bootstrap is archived, its state is preserved under the persistent `dev` azd
environment, and application state already uses the Entra-authenticated blob
backend. No product resources or runtime implementations exist.

Azure preflight on 2026-10-22 advertised all required resource types in France
Central, PostgreSQL 18 and B1ms, and positive model capacity/quota. AzureRM 5.10.0
supports PostgreSQL 18, AIServices deployments with Microsoft/OpenAI model formats,
Azure Monitor as the ACA logs destination, and disabling local App Insights
authentication. Availability must still be checked at apply time.

## Goals / Non-Goals

**Goals:** make the shared services usable, not merely present in a Terraform
plan; preserve the environment; separate privileged database initialization from
future workload execution; distinguish ARM provisioning, migration success, and
data-plane smoke results.

**Non-Goals:** deliver a business service by substituting a placeholder image;
implement later slices' tables, data-access grants, user bearer-token validation,
model-provider interfaces, scanner decisions, or pipeline instrumentation.

## Decisions

### 1. Extend the existing azd application layer

Keep a flat Terraform resource layout until actual reuse warrants modules.
Derive stable resource names from the environment and use a deterministic suffix
only for globally unique names. Default the application group to
`rg-newsloom-dev`, separate from state infrastructure. Export `AZURE_RESOURCE_GROUP`
and explicit registry, ACA environment, database, model endpoint/deployment, and
telemetry configuration outputs; do not infer the application group from `RS_*`.

All taggable application resources receive the common variable-derived map.
Keep the current tenant's policy tags in ignored azd input values and deployment
templates, with no mandatory tag-name validation or tag-specific test suite.
Alternative rejected: duplicating tenant policies as product requirements.

### 2. Prefer small metered resources without silent capacity fallback

Use ACR Basic with its admin account disabled, a Consumption ACA environment,
workspace-based Application Insights, and a PostgreSQL 18 Flexible Server.
B1ms is the initial development candidate, subject to capacity and price review.
Select disk size, retention, model deployment capacities, and cost-control
settings explicitly in environment configuration before the first reviewed plan.
Do not add paid provisioned model throughput, HA replicas, or dedicated ACA
capacity by default.

Refresh PostgreSQL restrictions, model SKUs, subscription quota, and platform
capacity; report an itemized baseline and usage-sensitive cost estimate before
apply. A different region/SKU, increased spend, or replacement of a persisted
server requires an explicit decision. Do not change `AZURE_LOCATION` as an
automatic retry: the protected bootstrap resources also consume that value.

### 3. Keep PostgreSQL Entra-only and initialize it through a real migration job

Disable password authentication and omit administrator passwords. Use a distinct
migration managed identity as the configured Entra administrator; runtime
identities never receive that role. Keep the v1 public endpoint with the Azure-
services firewall exception and TLS-required clients, not an unrestricted
Internet client-address rule.

Allowlist `vector` through server configuration. A versioned migration then
creates the extension and workload principal mappings using explicit object IDs,
with an administrative migration ledger and serialized execution. Repeat runs
must converge; mismatched identity mappings or SQL errors fail the job. Do not
grant directory-wide Graph permissions merely to resolve a display name.
Create no news, queue, feed, or quarantine tables here. Later owning migrations
grant their DML privileges; this foundation verifies login mappings and absence
of unintended administrator/schema-creation privileges.

Alternative rejected: DDL in Terraform provisioners, application startup, or a
developer shell that bypasses the required migration-job boundary.

### 4. Build the migration image before provisioning its job

Add a small `migrations` Terraform layer after `application`, using a separate
environment-specific remote state key in the existing backend. Its preprovision
hook builds the real migration runner in ACR using a source/lock-derived immutable
image reference, then records that reference in azd. Its postprovision hook starts
the manual ACA migration job and checks the terminal execution result.

This avoids a nonexistent image, a dummy successful job, or recursive
`azd provision` calls inside hooks. The foundation layer provisions the registry
and environment first; migrations own only the actual initialization job.
Registry build and job start are actions invoked by azd hooks, not direct ARM/CLI
resource creation. A failed build, pull, migration, or terminal-status check must
fail the azd operation. Retain failed executions for diagnosis without logging SQL
parameters, tokens, or connection strings.

### 5. Pin model contracts and retain the scanner's distinct API

Use one key-disabled AIServices account with an Entra-compatible custom subdomain:

| Use | Model / version | Proposed deployment SKU |
| --- | --- | --- |
| Enrichment | `gpt-5.4-mini` / `2026-03-17` | `DataZoneStandard` |
| Embeddings | `text-embedding-3-large` / `1` | `Standard` |
| Screening | `Microsoft-Decision-1` / `1` | `DataZoneStandard` |

Store deployment names and capacity units as configuration. Read each model's
current scaling metadata rather than interpreting every capacity unit as TPM.
Azure smoke tests use synthetic inputs only: structured enrichment, an embedding
requested at exactly 1536 dimensions, and a typed `noul` question sent to
`POST <endpoint>/providers/microsoft/v1/systemone` with a finite probability in
the inclusive range 0 to 1. The scanner is not called through a chat client, and these
probes do not claim scanner calibration or final content-security acceptance.
Use native AzureRM deployments; introduce AzAPI only for a demonstrated provider
gap and document that gap.

### 6. Make workload grants explicit and test their boundary

Create separate ingestion, enrichment, and MCP user-assigned identities. Maintain
an inventory of principal, target scope, role/data actions, and rationale:

| Principal | Intended platform access |
| --- | --- |
| Ingestion | Registry pull, telemetry publish, scanner inference, its database login |
| Enrichment | Registry pull, telemetry publish, GPT/embedding inference, its database login |
| MCP | Registry pull, telemetry publish, embedding inference, its database login |
| Migration runner | Registry pull and database administration; no model inference or registry push |

Use the narrowest supported service scope and inference-only data roles.
Account-scoped Azure OpenAI User grants can cover every deployed model; do not
claim per-model isolation from a role name alone. Validate supported deployment
scopes/data actions and actual allow/deny results before accepting the grant
inventory. If the required boundary cannot be enforced with one account, stop
and surface the ADR/capability conflict instead of broadening access silently.
No runtime identity receives Owner, Contributor, key-listing permissions, or
database administrator membership.

Run bounded smoke executions under the actual workload identities, using
temporary manual verification jobs provisioned through azd when necessary.
Their image performs real checks, not business-workload simulation. Cleanup may
remove only these explicitly named verification resources; never delete or
recreate shared services to get a green check.

### 7. Use keyless telemetry paths and a content-free probe

Configure the ACA environment with `logs_destination = "azure-monitor"` and
diagnostic settings to Log Analytics, avoiding a workspace shared key in its
configuration. Disable local authentication on Application Insights and grant
only telemetry-publishing permissions to the emitting identities.

The Azure smoke probe emits a synthetic correlation identifier, outcome, and
counts, then verifies authenticated ingestion. Reject a credential-free attempt.
Never emit feed text, prompts, completions, tokens, connection strings, or
arbitrary exception payloads. Full application OpenTelemetry and pipeline
metric coverage arrive with the runtime slices.

## Risks / Trade-offs

- **B1ms is advertised but physical capacity can still fail** -> stop before
  choosing another SKU or region; preserve partially provisioned state for retry.
- **Model quota and role propagation are shared/eventually consistent** -> use
  bounded, visible retries for propagation only; report exhausted retries.
- **Scanner retirement on 2027-02-04** -> preserve ADR-6 and surface lifecycle
  evidence before deployment; require a separate approved replacement decision.
- **AAD-only database and model access need real permission evidence** -> verify
  with managed-identity executions, not Terraform role-assignment presence alone.
- **Public Azure-services firewall is broader than private networking** -> accept
  only the documented v1 exception; retain Entra-only authentication and TLS.
- **One extra layer is required for the real migration image/job dependency** ->
  keep it small, independently state-backed, and strictly dependent on application
  outputs rather than generalizing a new deployment framework.

## Migration Plan

1. Reuse the existing `dev` environment, subscription, region, and state. Confirm
   permissions, current capacity, selected SKU/capacities, and estimated cost.
2. Run credential-free checks of Newsloom configuration, infrastructure guards,
   migration behavior, and safe failure/reporting paths. Do not test azd internals.
3. Review `azd provision application --preview`; reject protected-state changes
   or unexpected resource replacement/deletion. Provision the application layer
   through azd.
4. Build and preview the migration layer against the real registry/environment;
   provision and execute it through azd. Verify extension readiness and mappings.
5. Run the identity, database, model, and telemetry smoke checks. Repeat migrations
   and provisioning to verify convergence, stable resource IDs, and retained state.
6. Run `azd up` as the end-to-end infrastructure entry point, record exact scope
   and evidence, confirm CI on the implementation commit, then archive the change.
   A successful foundation deploy must not be described as a working MCP service.

Rollback preserves the database, registry, state, and environment. Fix forward
after partial provisioning; use a reviewed compensating migration if necessary.
Do not use `azd down` or recreate PostgreSQL as recovery.
