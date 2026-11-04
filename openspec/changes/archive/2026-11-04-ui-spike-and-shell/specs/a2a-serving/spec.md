# Spec Delta

## ADDED Requirements

### Requirement: Exact-origin browser preflight
The agent SHALL support browser preflight only for explicitly allowed origins
and the existing discovery/research paths. Allowed methods and request headers
MUST be fixed, without wildcard origins or credentialed CORS. Preflight MUST NOT
consume authentication, request admission, token exchange, tool or model work.

#### Scenario: An allowed UI preflights research
- **WHEN** its exact origin requests POST `/a2a` with only Authorization, Content-Type, A2A-Version and Accept headers
- **THEN** preflight succeeds with that exact origin, a fixed method/header allowlist and bounded max age
- **AND** no application request capacity, authentication or downstream operation is consumed

#### Scenario: Discovery is preflighted
- **WHEN** an allowed origin requests GET `/.well-known/agent-card.json`
- **THEN** the public discovery preflight succeeds without a bearer token
- **AND** only the existing public metadata can be retrieved

#### Scenario: A browser requests an unsupported boundary
- **WHEN** the origin is duplicated or unallowlisted, or its preflight path, method or headers are unsupported
- **THEN** preflight fails explicitly without downstream work
- **AND** it does not grant access to additional headers, methods or origins

### Requirement: CORS preserves existing authorization and response visibility
Allowed-origin responses SHALL include exact-origin CORS headers and correct
cache variation on success, errors and stream startup. Actual invocations MUST
retain existing token, protocol, caller-isolation and budget checks.
Requests without Origin MUST retain their current behavior.

#### Scenario: A browser receives a success or failure
- **WHEN** an allowed-origin request succeeds, fails authorization or reaches capacity/deadline limits
- **THEN** the browser can observe its real status and permitted response
- **AND** Access-Control-Allow-Credentials is absent and Vary includes Origin
- **AND** partial stream failure is not converted to successful completion

#### Scenario: An allowed origin supplies an invalid token
- **WHEN** the browser sends a missing, invalid or wrong-audience bearer token
- **THEN** the existing authentication failure occurs before token exchange or inference
- **AND** CORS does not authorize research on the basis of origin alone

#### Scenario: Existing native clients invoke the agent
- **WHEN** a current authorized client sends no Origin header
- **THEN** discovery, invocation, task reads and cancellation retain their existing contracts
- **AND** no browser authorization prerequisite is imposed
