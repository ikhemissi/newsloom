# Spec Delta

## Purpose

Turn selected or discovered stored news into question-specific explanations and
comparisons, with request-local preferences, delegated read-only tools and
explicitly bounded, cited evidence.

## ADDED Requirements

### Requirement: Explicit preference-aware research
The agent SHALL accept a research question, optional selected stored-item IDs,
filters and request-local presentation preferences. Preferences MUST NOT alter
evidence or access controls. Unsupported, malformed or oversized inputs MUST
fail explicitly before model or tool work. The existing recent-news operation
MUST remain unchanged. No persistent preferences or conversation memory is added.

#### Scenario: The caller requests deeper comparison
- **WHEN** a caller selects one or multiple stored items and supplies a question
  with audience, language, detail or focus preferences
- **THEN** the agent researches those items and tailors its presentation to the
  current request without importing another caller's preferences or history

#### Scenario: The request requires unavailable external context
- **WHEN** a caller asks for details that are absent from stored MCP records
- **THEN** the answer states that limitation without claiming full-article,
  web-search, Work IQ or memory access

### Requirement: Explicit content precedes presentation
Explicit content and quotation requirements in the question MUST take precedence
over presentation preferences, without changing evidence availability or any
authority or budget limit.

#### Scenario: Explicit content conflicts with brevity
- **WHEN** a caller explicitly requests the complete verbatim stored summary and
  also supplies a brief presentation preference
- **THEN** the answer preserves that explicit complete-quotation requirement
  rather than silently returning an excerpt or paraphrase
- **AND** unavailable evidence or an existing limit still produces an explicit
  limitation or failure, never invented content or a widened budget

### Requirement: Bounded user-preserving research tools
Research SHALL use only the existing four read-only MCP tools under the
originating user's validated delegated identity. All tool and model calls MUST
consume one authorization-clamped deadline and shared finite call/byte/token
budgets. The agent MUST NOT gain direct database, embedding, management, external
web or application-only MCP authority.

#### Scenario: Research needs several operations
- **WHEN** discovery, recent browsing, filtered search or stored-item inspection
  is selected within the request budget
- **THEN** typed arguments and structured results are validated for each call
- **AND** every call uses the same verified caller with request-owned credentials

#### Scenario: A limit or authorization boundary is reached
- **WHEN** an eighth MCP call or fourth model call has completed, the shared
  120-second deadline expires, or authorization expires
- **THEN** no further corresponding work is admitted
- **AND** unfinished work fails explicitly rather than resetting budgets,
  retrying through another identity or reporting a partial failure as success

### Requirement: State-constrained planning
Each planning schema and independent whole-plan validation SHALL share frozen
application-owned request, evidence and budget state. Detail IDs MUST be known
before the turn; dependent reads MUST use later turns. Synthesis MUST require
detail evidence, except stopping after healthy empty retrieval for
controller-generated no-match. Invalid plans MUST fail before any dispatch.
Existing guards and budgets MUST remain intact; substitution, repair and retries
are forbidden.

#### Scenario: Discovery reveals an item for inspection
- **WHEN** a planning turn begins without known detail IDs and discovery returns
  relevant metadata
- **THEN** its schema omits detail lookup and the next turn may select the
  returned IDs for inspection
- **AND** synthesis becomes available only after detail evidence is retrieved

#### Scenario: Metadata alone cannot justify synthesis
- **WHEN** relevant metadata exists but no detail evidence is available
- **THEN** the planning schema excludes synthesis and a returned synthesis plan
  fails independent validation
- **AND** exhausted budgets produce an explicit failure, not a metadata-only answer

#### Scenario: Healthy retrieval finds no evidence
- **WHEN** a healthy retrieval leaves no news evidence
- **THEN** stopping is permitted and the controller reports no-match without
  final generation
- **AND** a source listing alone is not treated as an empty news retrieval

#### Scenario: Independent calls share one planning turn
- **WHEN** every call in a bounded batch is legal against the turn's starting
  state and within its remaining budgets
- **THEN** the complete plan is validated before its calls execute sequentially
- **AND** one call cannot depend on an ID another call has yet to discover

#### Scenario: A later call in the plan is invalid
- **WHEN** an earlier call is valid but a later call violates the frozen scope
- **THEN** the complete plan fails before any call from it is dispatched
- **AND** no partial batch, substituted ID or unbudgeted repair is executed

### Requirement: Immutable caller selection and filters
Caller-selected items and source/category/tag/date constraints SHALL remain
authoritative throughout research. Model choices MUST NOT broaden or discard
them. Tool responses MUST be checked against the requested constraints.
Missing items and incomplete selection coverage MUST be reported explicitly;
not-found MUST remain distinct from tool failure.

#### Scenario: A model tries to relax a filter
- **WHEN** a planned call changes a source, drops required tags, expands the
  date interval or substitutes an unselected item in selected-item mode
- **THEN** the call is refused before execution with a safe explicit outcome
- **AND** no broader read substitutes for the constrained request

#### Scenario: Some selected items are missing
- **WHEN** valid selected IDs return both stored records and explicit not-found
- **THEN** the response identifies incomplete coverage to the caller
- **AND** it does not invent the missing items or describe the comparison as complete

### Requirement: Evidence-bounded synthesis and absence
Research answers SHALL use only validated MCP evidence from the current request.
The agent MUST distinguish a supported comparison, limited evidence and no match.
Stored summary/metadata detail MUST NOT be represented as full-article access.
Tool or model failure MUST NOT become a successful model-recollection answer.

#### Scenario: Multiple items support an answer
- **WHEN** stored summaries contain evidence relevant to the question
- **THEN** the response distinguishes supported agreements, differences and limits
- **AND** similarity scores are not described as factual confidence or probability

#### Scenario: Evidence is empty, insufficient or unavailable
- **WHEN** tools return no matching evidence, evidence lacks the requested detail,
  or a required tool operation fails
- **THEN** absence/insufficiency is explicit, and operational failure remains failure
- **AND** neither missing evidence nor a failed read is repaired by invented news

### Requirement: Validated citation provenance
Every returned news claim SHALL reference supporting item IDs from the current
validated evidence set. Citation URLs MUST be resolved from those records, not
accepted from model-authored URLs. Unknown references, unsafe URLs and malformed
answer structures MUST fail validation before answer text is exposed.
Structural validation MUST NOT be reported as proof of semantic groundedness.

#### Scenario: The final answer cites retrieved items
- **WHEN** a claim references one or multiple current evidence IDs
- **THEN** its rendered citations use the exact corresponding stored URLs
- **AND** focused acceptance separately checks that the cited evidence supports the claim

#### Scenario: The model invents or misuses a citation
- **WHEN** the answer cites an unseen ID, supplies a replacement URL, uses an
  unsafe URL or omits support for a news claim
- **THEN** no answer text or fabricated citation is emitted
- **AND** the task fails explicitly without an unbudgeted repair generation

### Requirement: Progress before validated answer delivery
Research SHALL stream content-free progress while collecting and validating
evidence, then emit the validated final answer and citations through A2A.
Raw draft tokens, planning text and tool bodies MUST NOT be streamed as progress.
Discovery MUST distinguish this delivery mode from live unvalidated token output.
Cancellation, disconnect and authorization expiry MUST release request-owned work.

#### Scenario: Validation succeeds
- **WHEN** the bounded final answer passes structure and citation validation
- **THEN** emitted answer artifacts match completed task readback
- **AND** completion occurs only after successful validated delivery

#### Scenario: Work is cancelled or validation fails
- **WHEN** the caller cancels during a tool call, drafting, validation or emission,
  disconnects, or final validation fails
- **THEN** no completed answer is recorded and downstream work is awaited/closed
- **AND** already emitted progress never masquerades as a successful answer

### Requirement: Hostile content cannot select authority
Retrieved strings SHALL remain untrusted data, never instructions or authority.
Only fixed application-owned tool names, schemas, endpoints and budgets may
authorize execution. Research diagnostics MUST retain the existing content-free
allowlist, excluding preferences, questions, plans, news, drafts, citations,
credentials and raw errors from application and dependency telemetry.

#### Scenario: Stored content asks for another action
- **WHEN** hostile titles, summaries, metadata or tool results request data
  disclosure, a changed endpoint, web retrieval or a write/management operation
- **THEN** no unauthorized operation occurs and caller constraints remain intact
- **AND** diagnostic canaries are absent across success, refusal, error and cancellation

### Requirement: Independently verified research delivery
Research acceptance SHALL include focused multi-item, preference, no-match,
missing-detail, hostile-content, citation, failure and cancellation cases.
Local transport tests and actual signed-in Azure checks MUST be distinguished.
Delivery MUST preserve the existing runtime boundaries and retain exact
source/image/configuration, local, CI and measured Azure evidence.

#### Scenario: The research slice is released
- **WHEN** offline regressions, reviewed agent-only deployment and bounded actual
  signed-in multi-step research checks pass
- **THEN** source citations, user preservation, private telemetry and unchanged
  workload/grant/model/schedule/data boundaries are independently verified
- **AND** Step 2.3's frozen phase-wide evaluation baseline remains a separate gate
