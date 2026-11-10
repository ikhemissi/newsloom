# Spec Delta

## Purpose

Allow the web as an explicit, separate evidence source when enabled.

## MODIFIED Requirements

### Requirement: Explicit preference-aware research
The agent SHALL accept a research question, optional selected stored-item IDs,
filters, request-local presentation preferences and optional request-supplied
conversation history. Preferences MUST NOT alter evidence or access controls.
Unsupported, malformed or oversized inputs MUST fail explicitly before model or
tool work. The existing recent-news operation MUST remain unchanged. No
persistent preferences or server-side conversation memory is added.

#### Scenario: The caller requests deeper comparison
- **WHEN** a caller selects one or multiple stored items and supplies a question
  with audience, language, detail or focus preferences
- **THEN** the agent researches those items and tailors its presentation to the
  current request without importing another caller's preferences or history

#### Scenario: The request requires unavailable external context
- **WHEN** a caller asks for details that are absent from stored MCP records and
  web research is disabled, unavailable or not applicable
- **THEN** the answer states that limitation without claiming full-article,
  Work IQ or server-side memory access, and claims web access only when web
  results were actually used
