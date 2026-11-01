# Spec Delta

## ADDED Requirements

### Requirement: Exact-origin modern MCP browser preflight
MCP SHALL permit browser preflight for POST `/mcp` from explicitly allowed
origins with a fixed header allowlist for authorization, content and protocol
metadata. Preflight MUST NOT consume authentication, tool capacity, data access
or inference. Wildcard origins and credentialed CORS MUST NOT be enabled.

#### Scenario: The UI preflights a modern MCP read
- **WHEN** its exact origin requests POST `/mcp` with Authorization, Content-Type, Accept, MCP-Protocol-Version, Mcp-Method and Mcp-Name
- **THEN** preflight succeeds with that exact origin and fixed method/header permission
- **AND** no token verification, database/tool work or model call occurs

#### Scenario: A browser attempts a different boundary
- **WHEN** the origin is missing from the allowlist or duplicated, or preflight requests unsupported headers, paths or methods
- **THEN** it fails explicitly without reflecting arbitrary origins or granting additional authority
- **AND** modern browser access does not enable legacy GET streams or protocol sessions

### Requirement: Browser CORS preserves MCP authorization and operational outcomes
Allowed-origin MCP responses SHALL expose the actual status through exact-origin
CORS and correct cache variation. Actual requests MUST retain existing token,
protocol and tool-budget validation. Existing callers without Origin MUST
remain compatible and browser errors MUST NOT become empty success.

#### Scenario: A browser read succeeds or fails
- **WHEN** an allowed-origin request succeeds, fails authorization, is malformed or reaches a service limit
- **THEN** the browser can observe its actual response with exact-origin CORS and Vary Origin
- **AND** Access-Control-Allow-Credentials is absent
- **AND** invalid authorization still fails before data access or embedding work

#### Scenario: An existing nonbrowser client connects
- **WHEN** the agent's OBO MCP client or an existing authorized VS Code client sends no Origin
- **THEN** discovery and all existing tools retain their authorization and protocol behavior
- **AND** the browser addition does not change grants, tool results or runtime budgets
