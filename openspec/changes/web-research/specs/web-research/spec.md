# Spec Delta

## Purpose

Let research use the web when stored news is not enough, with web sources kept
separate from stored evidence.

## ADDED Requirements

### Requirement: Web research through a credential the agent never holds
Web search SHALL go through a Foundry project connection to Web IQ that the
agent calls with its managed identity; the Web IQ key MUST NOT appear in the
repository, azd environment, Terraform state, application settings or logs.
Web research MUST be disabled unless explicitly enabled.

#### Scenario: Web research is disabled
- **WHEN** `WEB_RESEARCH_ENABLED` is false
- **THEN** the planner is not offered `search_web` and answers are unchanged

### Requirement: Agent-decided, bounded web searches
In discovery mode the planner MAY call `search_web` at most twice per request
when stored evidence is missing or may be out of date. Web results SHALL be
untrusted data, at most 5 per search, and count within the existing tool and
evidence budgets. Selected-item requests MUST NOT use the web.

#### Scenario: Stored news only points to the change
- **WHEN** the stored item says new features were announced without listing them
- **THEN** the agent may search the web and cite web sources for the details

#### Scenario: The web cannot be reached
- **WHEN** a web search fails or returns malformed results
- **THEN** the answer uses stored evidence only and states the web was not reached

### Requirement: Separate web citations
Claims supported by web results SHALL be rendered under "From the web" with
`[Wn]` citations to the result URLs, after stored-news claims, and the answer
SHALL state whether the web was used.

#### Scenario: An answer uses both
- **WHEN** an answer has stored and web claims
- **THEN** stored claims cite `[n]`, web claims cite `[Wn]`, and both citation
  lists are present
