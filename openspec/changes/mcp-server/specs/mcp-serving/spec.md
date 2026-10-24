# Spec Delta

## Purpose

Let authorized MCP clients browse and discover stored enriched news through a
bounded, observable Streamable HTTP service without exposing processing data.

## ADDED Requirements

### Requirement: Authenticated Streamable HTTP tools
The service SHALL expose the four read-only tools `get_recent_news`,
`get_news_item`, `list_sources`, and `search_news` over Streamable HTTP with
published input/output schemas and structured results. Every protocol request
MUST be authenticated and authorized before tool execution or data/model access.
Unsupported methods and invalid arguments MUST fail explicitly.

#### Scenario: A client uses the deployed protocol
- **WHEN** an authorized compatible client connects and discovers tools
- **THEN** all four tool schemas are discoverable and calls return schema-valid
  structured results rather than a substitute REST-only service
- **AND** protocol negotiation and cancellation work for the verified client

#### Scenario: An unauthorized caller submits a protocol message
- **WHEN** a caller lacks valid authorization for initialization, discovery or a tool call
- **THEN** the request is rejected before any news query or embedding call
- **AND** an in-memory protocol test alone is not treated as HTTP authentication evidence

### Requirement: Scoped single-tenant authorization
User access SHALL require a verified Entra access-token signature, trusted
single-tenant issuer, intended Newsloom audience, valid lifetime and delegated
`news.read` scope. Missing, forged, expired, wrong-tenant, wrong-audience and
wrong-scope tokens MUST NOT read news. Tokens issued for another resource,
ID tokens and app-only tokens without the delegated scope MUST NOT substitute.

#### Scenario: A valid delegated news token is presented
- **WHEN** its trusted signature and all required claims are valid
- **THEN** the caller can use read-only news tools within the configured limits
- **AND** user identity or token content does not become a SQL filter or query instruction

#### Scenario: Token validation or trusted key discovery fails
- **WHEN** a required claim is invalid or no trusted signing key can verify the token
- **THEN** access fails closed with a content-free category and appropriate
  authentication/authorization response
- **AND** the service does not trust a caller-supplied key URL, bypass signature
  checks or accept a different audience to recover

### Requirement: Discoverable secretless VS Code sign-in
The endpoint SHALL advertise protected-resource authorization metadata and
authentication challenges usable by a pre-registered VS Code OAuth client.
Single-tenant Entra authorization-code/PKCE sign-in MUST work without dynamic
client registration, API keys or client secrets. Registration and consent changes
MUST be explicitly inventoried and reviewed before applying them.

#### Scenario: The user connects from VS Code
- **WHEN** the documented remote configuration uses the approved public OAuth client ID
- **THEN** the user completes Entra sign-in and consent and invokes live tools
  against the intended Azure endpoint
- **AND** actual IDs and tokens remain outside committed configuration and telemetry

#### Scenario: Registration or consent is unavailable
- **WHEN** the approved client cannot obtain the intended audience/scope or
  directory permissions are insufficient
- **THEN** end-user acceptance remains blocked with the specific limitation recorded
- **AND** no static token, auth proxy, anonymous endpoint or broader grant is introduced

### Requirement: Bounded recent-news browsing
`get_recent_news(limit, since?)` SHALL return only stored news, newest publication
first with a deterministic ID tie-breaker. Limit SHALL default to 10 and accept
integers 1-50 only. `since` SHALL be an inclusive timezone-aware UTC-normalized
publication lower bound. Missing `since` MUST NOT impose an undocumented
recency cutoff.

#### Scenario: A valid browsing request is made
- **WHEN** news exists at and after the requested lower bound
- **THEN** matching rows include the boundary, preserve stable order, and return
  at most the requested number without model inference
- **AND** an empty matching set is a valid empty result

#### Scenario: Limits or dates are invalid
- **WHEN** the caller supplies a boolean, out-of-range limit, malformed date or naive timestamp
- **THEN** the request reports a typed input error rather than silently clamping or guessing

### Requirement: Stored item detail and filter discovery
`get_news_item(id)` SHALL return a stored public-news record or an explicit
not-found result for a valid absent ID. `list_sources()` SHALL return source IDs
and categories represented in stored news, with usable catalogue category labels.
Public records MUST include ID, title, summary, source, category, tags, published
time and original URL, never raw articles, vectors, tokens or private processing fields.

#### Scenario: An item or available filter is requested
- **WHEN** an authorized caller requests a valid item ID or source/category discovery
- **THEN** results correspond to committed news and category IDs match their
  approved labels, including Governance distinct from Regulations
- **AND** newly committed news becomes discoverable without restarting the app

#### Scenario: An identifier is not a stored news item
- **WHEN** a valid UUID identifies only queue/quarantine work or no news row
- **THEN** detail returns not-found without exposing that processing state
- **AND** malformed IDs fail as invalid input rather than being interpolated into SQL

### Requirement: Read-only news and workload isolation
The runtime SHALL access only the permitted news projection using its existing
MCP managed identity. It MUST NOT read queue/quarantine tables, write news, run
DDL, fetch client URLs or possess another workload's role. User tokens MUST NOT
be forwarded to PostgreSQL, Foundry or diagnostic services.

#### Scenario: The runtime identity is exercised
- **WHEN** approved news reads and forbidden queue/quarantine/write/admin operations are tested
- **THEN** reads succeed and forbidden operations are denied under the actual identity
- **AND** migration replay preserves existing news, backlog and quarantine

#### Scenario: Explicit isolated retrieval evaluation is authorized
- **WHEN** the approved evaluation-only process uses a short-lived fixture schema
  prepared by the migration identity
- **THEN** its temporary permission is read-only, the serving endpoint remains
  hardwired to production news, and the schema/grant are removed after the test
- **AND** no caller parameter can select another relation, schema or query

#### Scenario: Returned content includes apparent instructions
- **WHEN** stored titles, summaries, tags or source strings contain instructions
- **THEN** they remain untrusted result data and cannot change SQL, tool schemas,
  endpoint configuration or authority

### Requirement: Private bounded service operations
Tool execution SHALL have finite request, concurrency, model and database
budgets, cancellation and safe failure responses. Metrics/traces SHALL report
only allowlisted tool/outcome names, counts, timings and safe categories.
User queries, article fields, tool bodies, access tokens and arbitrary exceptions
MUST NOT be emitted by application or dependency telemetry.

#### Scenario: Infrastructure or budget failure occurs
- **WHEN** database access, authentication keys or model capacity is unavailable,
  or a request is cancelled or exceeds its budget
- **THEN** the operation terminates explicitly without fabricated results,
  leaked request/response data or unbounded work
- **AND** a healthy empty query is distinguishable from an unavailable service

### Requirement: Independent state-preserving MCP delivery
The always-on app SHALL deploy an immutable image through the existing azd
environment with its existing identity, verified HTTPS public ingress and
explicit host/origin controls. It MUST preserve shared resources, stored data and
both existing schedules. Acceptance MUST include real signed-in VS Code browsing
and search, independent result checks and authenticated telemetry.

#### Scenario: The service is deployed and verified
- **WHEN** offline checks, real-model retrieval evaluation and the reviewed owning-slice preview pass
- **THEN** actual protocol calls return live committed news and a user completes
  browser sign-in plus all four tools in VS Code
- **AND** a configured URL, successful health probe, or scripted bearer-token
  request alone does not satisfy end-user acceptance
