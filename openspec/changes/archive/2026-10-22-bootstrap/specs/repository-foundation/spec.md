## Purpose

Provide reproducible repository tooling, durable planning documents, offline
quality gates, and a verified secretless Azure state foundation for Newsloom.

## ADDED Requirements

### Requirement: Reproducible typed Python workspace
The repository SHALL provide a locked uv workspace on stable Python 3.15 with a
shared package and independently packaged ingestion, enrichment, and MCP boundaries.
It MUST NOT expose fake job success or unauthenticated placeholder services.

#### Scenario: Developer installs workspace
- **WHEN** a developer runs the documented locked installation and build commands
- **THEN** all four packages install, build, and import without cloud credentials

### Requirement: Permanent planning input
The repository SHALL preserve phase PRDs, capabilities and user stories, ADRs,
platform notes, and the ordered delivery workflow in standalone documentation.
It MUST NOT require or retain a duplicate full copy of the planning input.

#### Scenario: Temporary input is removed
- **WHEN** the temporary input and its full-copy document are deleted
- **THEN** the standalone documentation, feed catalogue, tests, and tools remain
  usable without references to the deleted documents

### Requirement: Validated initial feed catalogue
The repository SHALL contain all 42 initial feed sources and their category
allowlists. Offline validation MUST reject malformed shapes, unsupported kinds,
unknown fields, duplicate IDs/URLs, credential-bearing or non-HTTPS URLs, and empty
category filters without making network requests.

#### Scenario: Initial catalogue is checked
- **WHEN** the feed-validation command loads the committed catalogue
- **THEN** it reports 42 valid sources without contacting publishers

#### Scenario: Invalid configuration is supplied
- **WHEN** a catalogue violates its schema or contains duplicate identifiers
- **THEN** validation fails explicitly rather than silently omitting entries

### Requirement: Cloud-credential-free quality gates
The repository SHALL run Ruff, strict mypy, pytest, feed validation, an identifier
guard, OpenSpec validation, and backend-disabled Terraform validation locally and
in CI without Azure credentials.

#### Scenario: Deployment identifiers are present
- **WHEN** a tracked or untracked non-ignored file contains a GUID-like identifier
- **THEN** the identifier check fails with its path and line but not its value

#### Scenario: Local validation runs
- **WHEN** the documented check script runs after dependency installation
- **THEN** every gate runs without contacting Azure or retrieving feeds

### Requirement: Secretless remote-state bootstrap
The repository SHALL provide an azd Terraform root configured for Entra-authenticated
remote state and a separate one-off state-bootstrap root. Shared-key access and
anonymous blobs MUST be disabled. State infrastructure MUST resist accidental
destruction, and configuration MUST NOT contain committed deployment identifiers.

#### Scenario: Authorized operator provisions and tests state
- **WHEN** the selected operator reviews `azd provision bootstrap --preview`
  and runs `azd provision bootstrap`
- **THEN** the operator can read, write, lease, and delete a probe blob using Entra
  RBAC only, and the persistent state account has shared-key access disabled

### Requirement: Native azd provisioning
Both Terraform roots MUST be provisioned through native azd layers in one
persistent environment, with the application layer depending on bootstrap.

#### Scenario: Existing bootstrap state is adopted
- **WHEN** existing direct-Terraform bootstrap state is moved into the same azd
  environment's bootstrap state location before provisioning
- **THEN** azd manages the existing resources without duplication or replacement

### Requirement: Honest ordered delivery
Each change SHALL record local, CI, and Azure acceptance evidence before being
considered complete and archived. The bootstrap SHALL NOT provision future product
resources or select the agent UI framework.

#### Scenario: Cloud checks have not run
- **WHEN** only local scaffold validation has succeeded
- **THEN** CI and Azure tasks remain unchecked and the bootstrap change stays active
