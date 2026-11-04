# Spec Delta

## Purpose

Give readers a usable, authenticated browser journey to the existing research
agent without weakening delegated access or overstating evaluation acceptance.

## ADDED Requirements

### Requirement: Stable delegated browser sign-in
The UI SHALL use a single-tenant Entra SPA sign-in with a stable HTTPS callback.
Requests MUST use the signed-in user's agent-audience token and `news.agent`
scope. The UI MUST NOT introduce secrets, standing application research access,
or reuse native loopback callbacks.

#### Scenario: A reader signs in
- **WHEN** a reader completes browser sign-in from the deployed UI
- **THEN** the browser returns to the registered UI callback and can invoke the agent
- **AND** the existing agent-to-MCP OBO path remains user-preserving

#### Scenario: Authorization is absent or expires
- **WHEN** an intended delegated token cannot be obtained or the agent rejects it
- **THEN** the UI displays a sign-in or access-denied state
- **AND** it does not substitute an operator, application or MCP-audience token
- **AND** it does not automatically resend a research question after a redirect

### Requirement: Validated deployment configuration
The UI SHALL validate deployment-supplied public configuration before sign-in
or agent access. Trusted HTTPS authority, endpoint and scope values MUST NOT
come from questions, URL parameters or agent-card redirection. Real deployment
identifiers MUST remain outside committed files.

#### Scenario: Configuration is malformed
- **WHEN** runtime configuration is missing, invalid or inconsistent
- **THEN** an explicit configuration-error screen appears before authentication or research
- **AND** the UI does not silently choose a default endpoint or tenant

#### Scenario: Discovery advertises an unexpected endpoint
- **WHEN** the agent card differs from the configured endpoint, protocol or authorization contract
- **THEN** the UI rejects the integration without sending the bearer token to that endpoint

### Requirement: Bounded progress-then-answer research
The UI SHALL submit a bounded research request to the existing A2A interface,
show its progress and accept an answer only after successful terminal completion.
It MUST NOT invent draft streaming, research history, outcome labels or citations.
Only one research request per UI session SHALL be in flight.

#### Scenario: A question completes successfully
- **WHEN** a signed-in reader submits a valid question
- **THEN** the UI shows retrieving, planning, synthesizing and validating events as received
- **AND** it displays the validated final text answer after successful completion

#### Scenario: Completed-task parity is verified
- **WHEN** deployed acceptance checks a successfully completed research question
- **THEN** its final text is compared without retaining content in test evidence
- **AND** a same-caller completed-task readback matches the streamed answer

#### Scenario: Input reaches its bound
- **WHEN** a nonblank question is at the agent's 8192-byte UTF-8 bound
- **THEN** it is accepted locally
- **AND** a larger or blank question is rejected with visible validation before dispatch

#### Scenario: The response is incomplete or invalid
- **WHEN** the stream fails, exceeds its bound, violates its contract or lacks successful completion
- **THEN** the UI shows an explicit failure rather than a completed partial answer
- **AND** it does not automatically replay the generation request

#### Scenario: No evidence supports an answer
- **WHEN** a completed agent response states no match, refusal or limitations
- **THEN** that response remains visible without fabricated claims or a success-quality badge

### Requirement: Safe visible citations
The UI SHALL render agent text inertly and make supplied citation URLs visible
and navigable. Only validated credential-free HTTPS links SHALL be clickable.
Unrecognized text and limitations MUST remain visible; citation mapping MUST NOT
invent titles, sources or factual validation.

#### Scenario: A cited answer is displayed
- **WHEN** a completed answer contains the existing trailing numbered citation lines
- **THEN** the UI displays those references and safe links to the supplied original URLs
- **AND** citation controls associate markers with the corresponding reference
- **AND** the stored-summary evidence limitation remains visible

#### Scenario: Hostile text or an unsafe URL is received
- **WHEN** text contains HTML, scripts, markdown links or a non-HTTPS or credential-bearing URL
- **THEN** it cannot execute markup or navigate through that unsafe URL
- **AND** unsupported text is retained as inert text rather than silently discarded

### Requirement: Accessible explicit request states
The UI SHALL provide labelled controls, visible focus, keyboard sign-in/chat/
citation operation, progress announcements and visible error states.
Stopping, signing out or losing the stream MUST NOT claim unconfirmed server
cancellation or retain a completed partial answer.

#### Scenario: A keyboard user operates research
- **WHEN** the reader navigates without a pointer
- **THEN** sign-in, question submission, stop and citation controls are operable
- **AND** progress and failures are announced without moving focus unexpectedly

#### Scenario: The reader stops or signs out
- **WHEN** a request is active
- **THEN** the UI closes its stream and attempts same-caller cancellation when a task ID is known
- **AND** it distinguishes an unconfirmed stop from confirmed server cancellation
- **AND** sign-out clears in-memory questions, answers and authorization state

### Requirement: Content-free early-access operation
The UI SHALL label research early access while PRD-2 quality acceptance remains
open. Questions, answers, news, tokens and raw upstream errors MUST NOT enter
logs, telemetry, URLs, persisted chat or verification artifacts.
Browser authorization cache MUST be confined to the authentication SDK's
necessary session flow, never exported as test evidence.

#### Scenario: A browser journey is verified
- **WHEN** acceptance checks exercise live research and errors
- **THEN** durable evidence contains only safe outcomes, counts and source/configuration provenance
- **AND** browser traces, HARs, screenshots and storage-state files do not retain live content or credentials

#### Scenario: Early-access UI acceptance passes
- **WHEN** this slice's local, Azure and exact-source CI gates pass
- **THEN** only this UI slice can be marked complete
- **AND** PRD-2 evaluations and unimplemented PRD-3 capabilities remain explicitly pending

### Requirement: Verified secretless ACA delivery
The UI SHALL run on ACA in the retained environment/region with immutable assets
and owning Terraform/azd deployment. Its workload authority MUST be limited to
its own registry pull. Acceptance MUST exercise the deployed browser journey,
not only health, discovery, mocks or an empty shell.

#### Scenario: The first usable UI is delivered
- **WHEN** a signed-in user asks a question from the deployed HTTPS UI
- **THEN** real progress, a completed research answer and a navigable original citation are observed
- **AND** deployed keyboard/accessibility checks pass
- **AND** existing backend resources, grants, data and evaluation receipts remain preserved

#### Scenario: Hosting or deployment fails
- **WHEN** configuration, image readback, sign-in or the browser journey cannot be verified
- **THEN** acceptance remains unchecked with the failure recorded safely
- **AND** no deployment key or unrelated infrastructure replacement is used as fallback
