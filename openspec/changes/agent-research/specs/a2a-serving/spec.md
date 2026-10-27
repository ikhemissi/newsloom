# Spec Delta

## MODIFIED Requirements

### Requirement: Truthful A2A discovery
The service SHALL publish a standard agent card identifying its supported
protocol version, HTTPS interface, authentication requirements and implemented
skills. Public discovery MAY contain static service metadata, but MUST NOT
expose news, credentials or private task state. Research MUST be advertised only
when implemented and enabled. Unsupported operations, push notifications and UI
transports MUST NOT be advertised.

#### Scenario: A compatible client discovers the service
- **WHEN** the client retrieves the standard agent card
- **THEN** the advertised endpoint and protocol work with the pinned client
- **AND** advertised streaming and skills correspond to actual server behavior

#### Scenario: The skeleton has not implemented full research
- **WHEN** research is unavailable and a caller inspects its skills or requests
  an unsupported operation
- **THEN** discovery describes only the implemented demonstrator and invocation
  rejects unsupported work explicitly rather than pretending to perform research

#### Scenario: Bounded research is enabled
- **WHEN** the deployed service enables the implemented research operation
- **THEN** discovery adds its request contract and progress-then-validated-answer
  delivery mode alongside the unchanged recent-news skill
- **AND** it does not claim external web search, persistent memory, Work IQ or
  completed phase-wide quality evaluations

#### Scenario: Research is disabled
- **WHEN** the research feature is not enabled
- **THEN** the existing recent-news card/operation remains usable
- **AND** research requests are explicitly unsupported before model or tool work
