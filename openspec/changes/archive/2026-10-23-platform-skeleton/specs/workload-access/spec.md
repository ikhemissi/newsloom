## Purpose

Give each Newsloom workload a distinct Entra identity and only its approved
platform permissions, while isolating privileged database initialization.

## ADDED Requirements

### Requirement: Distinct workload identities
The platform SHALL provide separate managed identities for ingestion, enrichment,
and MCP, plus a distinct migration identity. A runtime workload MUST NOT inherit
another workload's identity or database administrator privileges.

#### Scenario: Identity inventory is inspected
- **WHEN** the operator inspects the deployed workload identities
- **THEN** all four principals are distinct and the grant inventory identifies
  each principal's intended purpose and target scopes

### Requirement: Entra-only platform authentication
The database and model services SHALL require Entra authentication, and registry
access SHALL use Entra/managed identity rather than an enabled registry admin
account. Deployment MUST NOT introduce passwords, client secrets, or key-based
fallbacks when authentication or permission checks fail.

#### Scenario: Managed-identity access succeeds
- **WHEN** a verification execution uses a workload identity for an approved operation
- **THEN** the service accepts its Entra credential without a password or account key

#### Scenario: Local authentication is inspected
- **WHEN** the operator checks database, Foundry, and registry authentication settings
- **THEN** PostgreSQL password authentication, Foundry local-key authentication,
  and the registry admin account are disabled

### Requirement: Isolated migration authority
Only the designated migration principal SHALL administer the application
database for platform initialization. Versioned migrations MUST establish
workload login mappings without making runtime identities administrators or
granting privileges on domain tables that do not exist yet.

#### Scenario: Migration job runs with its own identity
- **WHEN** the real migration job initializes the database
- **THEN** it authenticates as the designated administrator, applies the recorded
  migrations, and creates the intended workload mappings without shared credentials

#### Scenario: Runtime identity attempts privileged database work
- **WHEN** a runtime identity attempts database administration or ungranted schema creation
- **THEN** the operation is denied while its approved login remains usable

### Requirement: Explicit least-privilege grant inventory
Every workload grant SHALL identify its principal, resource scope, permitted
operations, and rationale. Runtime identities MUST NOT receive Owner, Contributor,
registry-push, key-management, or unrelated service permissions. Model inference
grants MUST respect the approved workload access matrix and supported service scopes.

#### Scenario: Approved and forbidden operations are exercised
- **WHEN** Azure checks run under the actual workload identities
- **THEN** approved inference, registry-pull, and telemetry operations succeed,
  and tested out-of-scope management or database operations are denied
- **AND** the inventory agrees with both role assignments and observed access

#### Scenario: Service scope cannot enforce the intended boundary
- **WHEN** the service's supported RBAC scopes cannot express the approved access matrix
- **THEN** implementation stops and reports the mismatch for an explicit decision,
  rather than silently granting broader access or claiming unverified isolation

### Requirement: Authenticated public database access
The v1 database SHALL require encrypted, authenticated client connections while
using the explicitly accepted Azure-services firewall exception. It MUST NOT
expose an unrestricted client-address firewall range to make verification pass.

#### Scenario: Database networking is verified
- **WHEN** the operator inspects network rules and runs the Azure connection probe
- **THEN** only the intended Azure-services exception is present, the authorized
  encrypted connection succeeds, and access without valid credentials is rejected
