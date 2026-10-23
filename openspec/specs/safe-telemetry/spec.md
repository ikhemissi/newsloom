# safe-telemetry Specification

## Purpose

Make platform health observable through authenticated Azure telemetry while
preventing diagnostics from exposing content or authentication material.

## Requirements

### Requirement: Connected operational sinks
The platform SHALL provide Log Analytics and workspace-based Application Insights,
with Container Apps environment diagnostics routed to the intended workspace.
Operational log routing MUST NOT require a workspace shared key in workload
configuration.

#### Scenario: Telemetry infrastructure is inspected
- **WHEN** the operator inspects the deployed telemetry resources and diagnostic routing
- **THEN** Application Insights references the intended workspace and Container Apps
  diagnostics are configured for that workspace without a workload-held shared key

### Requirement: Authenticated telemetry ingestion
Application Insights SHALL require Entra authentication for ingestion. Emitting
identities MUST receive only the scoped publishing permissions needed for their
telemetry rather than credentials or resource-management privileges.

#### Scenario: Authorized synthetic event is ingested
- **WHEN** a permitted managed identity emits a uniquely correlated synthetic event
- **THEN** the event becomes queryable in the configured sink with its expected
  correlation identifier and outcome

#### Scenario: Unauthenticated ingestion is attempted
- **WHEN** a probe submits telemetry without a valid Entra credential
- **THEN** ingestion is rejected even if the caller knows the routing identifier

### Requirement: Content-free platform diagnostics
Platform migration and verification diagnostics SHALL contain only allowlisted
identifiers, outcomes, counts, and timings. Tokens, credentials, connection strings,
article text, prompts, model completions, and arbitrary upstream error bodies
MUST NOT appear in emitted telemetry or captured job output.

#### Scenario: Successful and failing probes emit diagnostics
- **WHEN** platform verification exercises both success and service-error paths
- **THEN** recorded diagnostics contain only the approved fields and exclude
  synthetic canaries representing content and credentials
- **AND** failures retain a safe error category and correlation identifier
  sufficient to locate the failed execution

### Requirement: Honest instrumentation coverage
Platform telemetry acceptance SHALL cover the initialized foundation and its
verification executions only. Unimplemented feed, queue, enrichment, and MCP
metrics MUST remain explicitly pending until their runtime slices exist.

#### Scenario: Platform observability evidence is reported
- **WHEN** the operator records the platform's telemetry checks
- **THEN** the evidence names the observed foundation events without claiming
  unimplemented pipeline metrics or end-to-end news correlation
