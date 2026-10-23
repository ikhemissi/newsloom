# persistent-azure-platform Specification

## Purpose

Provide the persistent shared Azure services that Newsloom workloads need,
with usable database/model access and observable, state-preserving deployment.

## Requirements

### Requirement: Provisioned application foundation
The platform SHALL expose a dedicated application resource group containing its
registry, Container Apps environment, PostgreSQL 18 database service, one
AIServices account with configured enrichment, embedding, and decision model
deployments, and connected Log Analytics/Application Insights resources.
Application resources MUST remain separate from state-bootstrap resources.

#### Scenario: First platform deployment succeeds
- **WHEN** the operator completes the reviewed application deployment
- **THEN** the expected services exist in the configured application group and
  region, and their actual resource IDs are recorded in the verification inventory
- **AND** a state-only or empty application deployment does not satisfy acceptance

### Requirement: Stable environment and data
Repeated platform deployments SHALL preserve the existing environment, database
contents, and shared resource identities unless an explicit replacement or
migration is approved. A failed or partial deployment MUST retain usable state
and report what succeeded and failed.

#### Scenario: Unchanged platform is deployed again
- **WHEN** the operator repeats deployment without changing configuration
- **THEN** shared resource IDs remain stable, no database is replaced, and the
  subsequent preview contains no unintended infrastructure changes

#### Scenario: Capacity or permissions block deployment
- **WHEN** provisioning encounters unavailable capacity or denied access
- **THEN** deployment fails visibly without enabling keys, silently changing
  region/SKU, recreating the database, or declaring the platform ready

### Requirement: Vector-capable database readiness
The application database SHALL run PostgreSQL 18 and have pgvector installed by
versioned migrations. Initialization MUST be repeatable without creating domain
tables or seeding news data before their owning delivery slices.

#### Scenario: Initial migration completes
- **WHEN** the platform initialization job finishes successfully
- **THEN** a database probe confirms PostgreSQL 18, the installed vector extension,
  and a successful 1536-dimensional vector operation using synthetic data
- **AND** no feed, queue, quarantine, or news tables have been introduced

#### Scenario: Migration is repeated or fails
- **WHEN** the same migrations run again or encounter an invalid identity mapping
- **THEN** completed work is not duplicated, and invalid work causes a failed
  execution with a safe diagnostic rather than a success-shaped result

### Requirement: Usable model deployment contracts
The platform SHALL provide working configured enrichment, embedding, and decision
deployments through its AIServices account. Model names, versions, SKUs, and
capacities MUST be explicit configuration supported by the selected region;
unsupported or retired configurations MUST NOT be replaced silently.

#### Scenario: Synthetic model probes succeed
- **WHEN** authorized verification executions call the configured deployments
- **THEN** enrichment returns a valid requested structured result, embeddings
  requested at 1536 dimensions contain exactly 1536 finite numbers, and the
  decision API returns a finite probability between 0 and 1 for a typed `noul`
  question
- **AND** none of these checks claims scanner calibration or news-processing readiness

#### Scenario: Required deployment cannot serve its contract
- **WHEN** a configured model is unavailable, unauthorized, retired, or returns
  an incompatible response
- **THEN** platform verification fails with the deployment and safe failure
  category identified, without switching models or logging input/output content

### Requirement: Discoverable platform configuration
Operators and later workload slices SHALL obtain the actual application group,
registry endpoint, Container Apps environment, database host/name, model
endpoint/deployment names, workload identity references, and telemetry routing
configuration from deployment outputs rather than state-storage names or guesses.

#### Scenario: Operator inspects a successful deployment
- **WHEN** the operator reads the selected environment's deployment outputs
- **THEN** those outputs identify the real provisioned application resources and
  match the Azure inventory without including authentication secrets

### Requirement: Evidence-based foundation readiness
The platform SHALL be accepted only after real Azure checks demonstrate resource
readiness, database migrations, model contracts, workload access boundaries, and
authenticated telemetry. A successful foundation deployment MUST NOT be
represented as a deployed ingestion, enrichment, or MCP business service.

#### Scenario: Foundation acceptance is reported
- **WHEN** the operator reviews platform-skeleton acceptance evidence
- **THEN** each check records its observed outcome and resource/execution reference,
  while the unimplemented runtime services remain explicitly pending
