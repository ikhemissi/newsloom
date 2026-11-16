# Spec Delta

## Purpose

Let a reader refine a question in a conversation, and suggest useful follow-ups.

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
- **WHEN** a caller asks for details that are absent from stored MCP records
- **THEN** the answer states that limitation without claiming full-article,
  web-search, Work IQ or server-side memory access

## ADDED Requirements

### Requirement: Bounded conversation history
A research request MAY include up to 3 previous turns, each with a question, the
answer text and the cited item IDs, at most 12 KiB in total. The agent SHALL use
history only to interpret the new question and choose items to re-read; earlier
answer text MUST NOT be cited as evidence, and every claim still needs stored
evidence read in this request. History is untrusted input and MUST NOT grant
tools, budget or authority.

#### Scenario: A follow-up refers to the previous answer
- **WHEN** the new question is "and what about AWS?" after an answer about Foundry agents
- **THEN** the agent interprets it as the AWS equivalent of the earlier topic,
  reads stored evidence for it and cites only items read in this request

#### Scenario: History is oversized or malformed
- **WHEN** history has more than 3 turns, exceeds 12 KiB or has unknown fields
- **THEN** the request fails explicitly before any model or tool work

#### Scenario: History contains instructions
- **WHEN** a previous answer or question in history contains instructions to change
  tools, limits or citations
- **THEN** they are treated as data and the existing limits and tools apply

### Requirement: Suggested follow-up questions
When the caller accepts `application/json`, a successful answer SHALL also return
up to 3 suggested follow-up questions of at most 120 characters each as a
separate artifact. Text-only callers receive the unchanged text artifact.

#### Scenario: Text-only client
- **WHEN** a caller accepts only `text/plain`
- **THEN** the response contains exactly the existing single text artifact
