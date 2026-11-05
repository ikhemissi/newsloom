# repository-foundation Specification

## Purpose

Provide reproducible repository tooling, durable planning documents, offline
quality gates, and a verified secretless Azure state foundation for Newsloom.

## Requirements

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
The repository SHALL retain 41 unique active feed sources and their category
allowlists after removing the broken Solo.io feed and retaining the existing
agentgateway feed. Offline validation MUST reject malformed shapes, unsupported
kinds, unknown fields, duplicate IDs/URLs, credential-bearing or non-HTTPS URLs,
and empty category filters without making network requests.

#### Scenario: Initial catalogue is checked
- **WHEN** the feed-validation command loads the committed catalogue
- **THEN** it reports 41 valid sources without contacting publishers

#### Scenario: Invalid configuration is supplied
- **WHEN** a catalogue violates its schema or contains duplicate identifiers
- **THEN** validation fails explicitly rather than silently omitting entries

#### Scenario: The broken publisher entry is retired
- **WHEN** the approved catalogue update is applied
- **THEN** `solo-io-blog` is absent and `agentgateway-blog` occurs exactly once
- **AND** the other source definitions and category allowlists remain unchanged
- **AND** historical source, queue and quarantine records are not deleted

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
A change SHALL be complete only after local checks and CI pass and, when it changes
deployed behavior, its Azure deployment is verified. A check that cannot run SHALL
be recorded as a known gap, never reported as passed. The bootstrap SHALL NOT
provision future product resources or select the agent UI framework.

#### Scenario: Cloud checks have not run
- **WHEN** only local scaffold validation has succeeded
- **THEN** CI and Azure tasks remain unchecked and the bootstrap change stays active

#### Scenario: An acceptance check cannot run
- **WHEN** a remaining check needs conditions automation cannot provide, such as a
  signed-in regular-browser session
- **THEN** it is recorded in the known-gaps register with its change and reason
- **AND** the change may be archived without marking that check as passed

### Requirement: Lightweight delivery track
Tuning, prompt, bug-fix, documentation and operational changes that add no new
capability, resource, identity, permission, dependency or data contract SHALL NOT
require an OpenSpec change. They SHALL still pass local checks and CI, deploy
through azd when deployed behavior changes, and update the owning runbook.

#### Scenario: A prompt or ranking change is delivered
- **WHEN** a change only adjusts existing behavior within existing contracts
- **THEN** it ships as a commit with a descriptive message and a runbook update
- **AND** no proposal, spec, design or task artifacts are required

#### Scenario: A change adds a resource or permission
- **WHEN** a change introduces a cloud resource, identity, grant or data contract
- **THEN** it uses an OpenSpec change before implementation

### Requirement: Single check run per source
Deployment hooks SHALL reuse a passing full check for an identical source
fingerprint instead of rerunning it, and any source change SHALL invalidate that
result. CI SHALL always run the full suite.

#### Scenario: Several layers deploy the same commit
- **WHEN** the full check passed for the current source and another layer deploys
- **THEN** the hook reports the reused result and skips the suite
- **WHEN** any tracked or new source file changes
- **THEN** the next hook runs the full suite again
