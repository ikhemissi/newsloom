# web-research Specification

## Purpose
Let research use the web when stored news is not enough, with web sources kept
separate from stored evidence.

## Requirements

### Requirement: Web research with the agent's managed identity
Web search SHALL call Web IQ with an Entra token for the agent's managed
identity. No Web IQ key MUST exist in the repository, azd environment,
Terraform state, application settings, Foundry connections or logs. Web research
MUST be disabled unless explicitly enabled.

#### Scenario: Web research is disabled
- **WHEN** `WEB_RESEARCH_ENABLED` is false
- **THEN** the planner is not offered `search_web` and answers are unchanged

### Requirement: Agent-decided, bounded web searches
In discovery mode without source, category, tag or date constraints the planner
MAY call `search_web` at most twice per request when stored evidence is missing
or may be out of date. Web results SHALL be untrusted data, at most 5 per search,
and count within the existing tool and evidence budgets. Selected-item requests
and constrained requests MUST NOT use the web.

#### Scenario: Stored news only points to the change
- **WHEN** the stored item says new features were announced without listing them
- **THEN** the agent may search the web and cite web sources for the details

#### Scenario: The web cannot be reached
- **WHEN** a web search fails or returns malformed results
- **THEN** the answer uses stored evidence only and states the web was not reached

#### Scenario: The caller constrains the request
- **WHEN** a discovery request has a source, category, tag or date constraint
- **THEN** `search_web` is not offered and a planned web search fails before dispatch

### Requirement: Separate web citations
Claims supported by web results SHALL be rendered under "From the web" with
`[Wn]` citations to the result URLs, after stored-news claims, and the answer
SHALL state whether the web was used.

#### Scenario: An answer uses both
- **WHEN** an answer has stored and web claims
- **THEN** stored claims cite `[n]`, web claims cite `[Wn]`, and both citation
  lists are present

### Requirement: Used web results for JSON callers
For callers that accept JSON, the `conversation` artifact SHALL list the web
results cited in the answer, in `[Wn]` order, with number, title, URL and
snippet. Text-only callers and the text answer MUST be unchanged, and the agent
MUST NOT store the results.

#### Scenario: An answer cites the web
- **WHEN** a JSON-accepting caller receives an answer citing `[W1]` and `[W2]`
- **THEN** `web_results` holds exactly those two results, numbered 1 and 2

#### Scenario: An answer cites no web result
- **WHEN** an answer has no `[Wn]` citation
- **THEN** `web_results` is empty
