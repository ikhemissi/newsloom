# Spec Delta

## Purpose

Expose a discoverable, authenticated news-agent boundary with caller-isolated
A2A streaming and independently verified, state-preserving delivery.

## ADDED Requirements

### Requirement: Truthful A2A discovery
The service SHALL publish a standard agent card identifying its supported
protocol version, HTTPS interface, authentication requirements and implemented
skills. Public discovery MAY contain static service metadata, but MUST NOT
expose news, credentials or private task state. Unsupported research, push
notifications and UI transports MUST NOT be advertised.

#### Scenario: A compatible client discovers the service
- **WHEN** the client retrieves the standard agent card
- **THEN** the advertised endpoint and protocol work with the pinned client
- **AND** advertised streaming and skills correspond to actual server behavior

#### Scenario: The skeleton has not implemented full research
- **WHEN** a caller inspects its skills or requests an unsupported operation
- **THEN** discovery describes only the implemented demonstrator and invocation
  rejects unsupported work explicitly rather than pretending to perform research

### Requirement: Agent-specific delegated authorization
Every invocation and task operation SHALL require a signature-verified,
single-tenant Entra user access token for the agent's own audience and delegated
`agent.invoke` scope. Missing, expired, forged, wrong-tenant, wrong-audience,
ID and application-only tokens MUST fail before token exchange, tool access or
inference. Caller-controlled signing-key URLs MUST NOT be followed.

#### Scenario: The caller presents an intended delegated token
- **WHEN** signature, issuer, tenant, audience, lifetime and scope are valid
- **THEN** the request may enter the delegated MCP path
- **AND** the token does not itself authorize another resource

#### Scenario: A token is invalid or belongs to MCP instead
- **WHEN** any required token property is invalid or the audience is MCP
- **THEN** the server returns an explicit authentication/authorization failure
- **AND** no OBO, MCP or Foundry request occurs

### Requirement: Caller-isolated task lifetime
Messages, task retrieval, cancellation, streaming and any supported resubscription
SHALL remain bound to the verified caller. Caller-supplied context/task IDs MUST
NOT grant access to another caller's state. Transient state MUST be bounded and
nonpersistent; restarts or expiry MUST yield explicit unavailability/not-found
rather than fabricated recovered work.

#### Scenario: Two callers interleave requests
- **WHEN** one caller supplies the other's task or context identifier
- **THEN** it cannot read, continue, cancel or subscribe to that work
- **AND** messages, model history and delegated credentials do not cross callers

#### Scenario: A task no longer exists
- **WHEN** state has expired or the process restarted
- **THEN** the client receives an explicit protocol outcome without replaying
  inference or claiming that interrupted work completed

### Requirement: Real bounded recent-news streaming
The skeleton SHALL provide one documented recent-news demonstrator using a real
delegated MCP read and at most one bounded Foundry generation. Successful
nonempty demonstrations MUST stream actual model output through A2A. Empty
stored results MUST remain explicit, and model recollection or independent web
retrieval MUST NOT substitute for missing MCP data.

#### Scenario: The demonstrator receives stored news
- **WHEN** a signed-in client requests the documented operation and OBO succeeds
- **THEN** the existing read-only MCP tool supplies stored data and the model
  response is streamed with a correct terminal A2A outcome
- **AND** news strings remain untrusted data, not authority to change tools or access

#### Scenario: News is absent or a dependency fails
- **WHEN** MCP returns no news, denies access or is unavailable
- **THEN** absence is distinguished from failure without invented articles
- **AND** a failed read cannot become a successful model-only response

### Requirement: Bounded cancellable agent requests
The service SHALL enforce a documented finite profile for request bytes,
concurrency, transient tasks, model output and end-to-end duration. All
authentication, exchange, MCP and model work MUST consume that same request
deadline and stop on cancellation or authorization expiry. Overload and partial
stream failures MUST be explicit, never empty success.

#### Scenario: A boundary is reached
- **WHEN** an input, concurrency, state, output or time limit is reached
- **THEN** exact-boundary tests establish acceptance versus rejection and
  excess work is refused without resetting budgets

#### Scenario: A stream is interrupted
- **WHEN** the caller disconnects, cancels, loses valid authorization or a
  dependency fails after streaming begins
- **THEN** downstream work and resources are released within the request budget
- **AND** partial output is not recorded as a completed answer

### Requirement: Content-free agent diagnostics
Agent and dependency diagnostics SHALL expose only allowlisted operations,
outcomes, counts, durations and safe categories through authenticated telemetry.
User messages, news fields, prompts, completions, tokens, assertions and raw
upstream errors MUST NOT enter logs, spans or evidence. A2A/model automatic
instrumentation MUST obey the same boundary.

#### Scenario: Success and failure instrumentation is exercised
- **WHEN** HTTP, token exchange, MCP, model, overload and cancellation paths run
- **THEN** diagnostic canaries are absent while safe outcomes remain observable
- **AND** a model/framework integration cannot silently reenable content capture

### Requirement: Independently verified state-preserving agent delivery
The agent SHALL deploy an immutable image in the retained ACA environment using
its own identity and owning infrastructure layers. Existing MCP registration,
images, model deployments, schedules and data MUST remain unchanged. Acceptance
MUST include actual signed-in A2A invocation, streaming, cancellation, telemetry
and exact-revision local/CI evidence.

#### Scenario: The owning slice is released
- **WHEN** local checks, the live OBO gate and reviewed owning previews pass
- **THEN** the deployed image/configuration is independently verified with a
  real signed-in client and traceable outcomes
- **AND** health checks or configured discovery alone do not complete acceptance
