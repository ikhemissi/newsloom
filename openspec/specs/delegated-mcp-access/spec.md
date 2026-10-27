# delegated-mcp-access Specification

## Purpose

Let the agent call read-only MCP tools as the signed-in user through a secretless
middle-tier exchange, without standing application access or identity substitution.

## Requirements

### Requirement: Audience-separated delegated exchange
The agent SHALL exchange its validated caller token for an access token intended
for the existing MCP resource and delegated `news.read` permission. Only the
exchanged token may authorize the MCP request. The incoming token MUST NOT be
forwarded to MCP or inference, and no user token may be returned to the client,
placed in model context or sent to an arbitrary endpoint.

#### Scenario: A delegated MCP call is made
- **WHEN** an authorized agent request reaches its tool adapter
- **THEN** a real OBO exchange obtains the downstream MCP token and that token
  is used only in the approved MCP authorization channel
- **AND** the user's original token is used only for its intended middle-tier flow

#### Scenario: A caller or news item supplies an endpoint or token
- **WHEN** untrusted input attempts to select an authority, scope, resource,
  tool credential or downstream URL
- **THEN** trusted deployment configuration remains authoritative
- **AND** neither token is disclosed or redirected

### Requirement: Exact secretless middle-tier authentication
The middle-tier registration SHALL trust only its own user-assigned managed
identity through exact same-tenant issuer, principal subject and token-exchange
audience bindings. Only the required delegated MCP permission may be consented.
Client secrets, exported private keys, wildcard/additional federation and
application-only MCP grants MUST NOT be introduced.

#### Scenario: The deployed identity authenticates the middle tier
- **WHEN** it obtains a token-exchange assertion and exchanges the caller token
- **THEN** Entra validates the exact federated binding without a stored credential
- **AND** the resulting MCP access remains delegated to the user

#### Scenario: Federation or consent is unavailable
- **WHEN** the assertion, binding, tenant or delegated consent cannot authorize exchange
- **THEN** the request fails with a safe explicit category
- **AND** no credential, alternate identity or broader permission fallback occurs

### Requirement: Request-scoped delegated credentials
User assertions, downstream tokens and delegated MCP clients SHALL be confined
to the originating request and authorization lifetime. They MUST NOT persist to
disk, enter shared model history or become mutable global authorization headers.
Concurrent callers, failed exchange and cancellation MUST NOT reuse another
request's credentials or results.

#### Scenario: Calls overlap or a connection is reused
- **WHEN** different signed-in callers invoke the agent concurrently
- **THEN** each MCP call uses only its own caller's delegated authorization
- **AND** cached credentials, headers and task state cannot substitute a principal

#### Scenario: The request ends
- **WHEN** completion, failure, cancellation or token expiry ends the request
- **THEN** its credential/client resources are closed and no later request can
  inherit the user's token or unfinished execution

### Requirement: Fail-closed delegated access
Missing or denied user access, interaction-required consent, invalid exchange
responses and MCP rejection SHALL fail explicitly before generation.
The agent MUST NOT recover by forwarding the incoming token, acquiring app-only
MCP access, using an operator identity, querying PostgreSQL directly or producing
a model-only answer.

#### Scenario: The user cannot access MCP
- **WHEN** OBO or MCP rejects the delegated request
- **THEN** the client receives an explicit authorization or operational outcome
- **AND** no model generation or substitute data path is attempted

#### Scenario: A failure occurs after prior successful traffic
- **WHEN** a later caller's exchange fails
- **THEN** the prior caller's token or successful result is not reused
- **AND** diagnostic evidence preserves failure without raw identity-provider payloads

### Requirement: Isolated agent workload authority
The agent identity SHALL have only its owning registry-pull, authenticated
telemetry and chat-inference permissions on supported service scopes. It MUST
NOT receive MCP application access, a database role, another workload's identity,
embedding/screening authority or management privileges. Existing workload grants
and MCP authorization MUST remain unchanged.

#### Scenario: Actual workload permissions are exercised
- **WHEN** Azure verification runs under the deployed agent identity
- **THEN** approved operations succeed and direct nondelegated MCP,
  embedding/screening and privileged/data access remain denied
- **AND** grant inventory alone is not reported as observed denial evidence

### Requirement: Live user-preservation go-no-go gate
Before model-backed agent expansion, acceptance SHALL prove an actual signed-in
A2A request, secretless OBO and one real MCP tool response in Azure. Private
evidence MUST establish the same user across audience-bound tokens using tenant
and object identity, not audience-specific subjects. Reports MUST expose only
safe comparisons and provenance, never tokens or raw user identifiers.

#### Scenario: The gate succeeds
- **WHEN** a signed-in client invokes the deployed access path
- **THEN** MCP accepts the delegated token, the real read succeeds and private
  verification establishes user preservation with matching image/configuration
- **AND** only that measured gate may unblock the model-backed demonstrator

#### Scenario: Proof is incomplete or unavailable
- **WHEN** only local tests, an application token, provisioned resources or
  an unverified identity comparison is available
- **THEN** OBO acceptance stays incomplete and dependent model/research work stops
- **AND** no unchecked task or future Phase 2 quality gate is reported as passed
