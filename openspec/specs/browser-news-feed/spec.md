# browser-news-feed Specification

## Purpose
Make stored-news browsing the default signed-in experience and keep agent
research an optional right-panel action on explicitly selected context,
with submitted news search through the existing read-only MCP boundary.

## Requirements

### Requirement: Latest stored news is the default landing view
After sign-in, the UI SHALL display up to 20 latest stored news items in the
server's newest-first deterministic order. It MUST NOT impose an undocumented
date cutoff, invent news or claim complete pagination. The feed SHALL show
title, summary, source/category, publication time and a safe original URL.

#### Scenario: A reader opens the application
- **WHEN** sign-in succeeds and stored news exists
- **THEN** the landing page retrieves the latest 20 items or all available items if fewer
- **AND** preserves publication order and the server's ID tie-breaker
- **AND** research is not the primary landing content

#### Scenario: Stored news is older or limited
- **WHEN** fewer than 20 items exist or the latest items fall outside seven days
- **THEN** available stored items remain visible without a hidden recency cutoff
- **AND** the UI describes a bounded latest-items view rather than a complete archive

### Requirement: Loading and refreshing news never invokes research
Feed loading and explicit refresh SHALL use only read-only recent-news access.
The UI MUST NOT invoke the agent, generation, embeddings or semantic search
when browsing. Only one feed load per browser view SHALL be in flight, and
stale responses MUST NOT overwrite a newer view or survive sign-out.

#### Scenario: The feed loads or refreshes
- **WHEN** the reader opens or explicitly refreshes the latest-news view
- **THEN** one bounded recent-news request supplies the items
- **AND** no A2A research or model/embedding call is dispatched

#### Scenario: The reader signs out during loading
- **WHEN** an unfinished feed request overlaps sign-out
- **THEN** it is cancelled and its result cannot repopulate the signed-out page
- **AND** in-memory news and selected research context are cleared

### Requirement: Top search uses explicit MCP semantic search
The UI SHALL provide a top search box that submits a nonblank query to MCP
`search_news` only when the reader explicitly submits it. Results MUST preserve
the server's relevance order, be bounded to 20 items and be labelled as search
results. Typing MUST NOT dispatch network work or agent research.

#### Scenario: A reader submits search
- **WHEN** a valid query of at most 2048 characters is explicitly submitted
- **THEN** one bounded MCP semantic-search request supplies relevance-ranked results
- **AND** no A2A agent request is dispatched
- **AND** the existing MCP embedding path is the only inference involved in search

#### Scenario: A reader edits or clears search
- **WHEN** text is merely edited
- **THEN** no search or research is automatically dispatched
- **WHEN** search is explicitly cleared or a blank query is submitted
- **THEN** the UI returns to the latest-news view using recent-news access without embeddings

#### Scenario: Search fails or returns no matches
- **WHEN** the result is valid and empty
- **THEN** an explicit no-search-matches state appears
- **WHEN** input, authorization, transport or response validation fails
- **THEN** a visible error appears rather than an invented result or successful empty list

### Requirement: Feed errors remain distinct from absence
The UI SHALL provide accessible loading, empty, failure and refresh states.
Authentication, overload and malformed/unavailable tool responses MUST NOT
be converted into successful empty lists or replaced by model-generated news.

#### Scenario: There is no stored news
- **WHEN** the authorized recent-news result is valid and empty
- **THEN** an explicit empty-news message and refresh action appear

#### Scenario: Access or the service fails
- **WHEN** authorization, capacity, transport or response validation fails
- **THEN** the reader receives a fixed appropriate failure and an explicit retry or sign-in action
- **AND** stale data is not presented as a successful fresh result

### Requirement: Research opens only when the reader requests it
The research composer SHALL occupy a closable right-hand panel on wide screens
and be collapsed by default. An item-level action SHALL open it with that
item's ID as visible removable context, without submitting a question.
General research SHALL remain explicitly accessible. Each submitted A2A
question MUST carry only its displayed current context.

#### Scenario: A reader asks about a news item
- **WHEN** the reader chooses "Ask about this"
- **THEN** the composer opens, receives keyboard focus and shows the selected item context
- **AND** no research is dispatched until the reader submits a question
- **AND** submission includes exactly that selected stored item ID

#### Scenario: Context is removed or replaced
- **WHEN** the reader clears context or selects another item while no research is active
- **THEN** the next submitted question reflects the displayed selection only
- **AND** removing context returns to general research without silent item constraints

#### Scenario: The reader opens or closes the agent panel
- **WHEN** the panel is opened through its explicit control
- **THEN** it appears to the right of news on wide screens without submitting research
- **WHEN** the panel is closed
- **THEN** news regains the available width and keyboard focus returns to its opener
- **AND** reopening retains transient panel state without replaying a request
- **AND** narrow screens expose the same controls without horizontal clipping

#### Scenario: The active news view changes
- **WHEN** a new search or latest-news view replaces the displayed items while no research is active
- **THEN** stale item context is cleared unless that item remains displayed
- **AND** the UI does not silently send the search query or all visible items as agent context
- **AND** an already-running research request retains its displayed immutable context

### Requirement: Browser news access preserves delegated audiences
News reads SHALL carry the signed-in user's MCP-audience delegated `news.read`
token through the existing MCP boundary. Agent requests MUST retain the
separate `news.agent` audience. Browser access MUST NOT introduce shared
credentials, application-only news access or direct database/model calls.

#### Scenario: The reader browses and then researches
- **WHEN** the existing browser account obtains authorization for each resource
- **THEN** MCP and agent calls each use only their intended audience-bound token
- **AND** an agent token is never forwarded to MCP or vice versa

#### Scenario: MCP consent is unavailable
- **WHEN** the SPA lacks the required delegated MCP consent
- **THEN** browsing fails explicitly with the required sign-in/consent action
- **AND** no operator token, proxy or broader permission substitutes

### Requirement: Inert accessible feed and private acceptance
News and search fields SHALL render as inert text and links SHALL use the existing
credential-free HTTPS policy. Keyboard users MUST be able to browse, refresh,
open research and follow citations. Live evidence MUST contain only safe
outcomes/counts/provenance, not news, questions, answers or credentials.

#### Scenario: A hostile stored title or URL appears
- **WHEN** data contains HTML/script syntax or an unsafe publisher URL
- **THEN** it cannot execute or navigate through that unsafe URL
- **AND** the text remains visible and labelled controls remain keyboard-operable

#### Scenario: The deployed feed is accepted
- **WHEN** a real signed-in browser loads news and explicitly requests item-context research
- **THEN** news, optional research and citation navigation work against existing Azure services
- **AND** deployed accessibility and no-automatic-inference checks pass
- **AND** submitted search uses MCP while item-context agent requests use A2A
- **AND** local mocks and user attestation are labelled separately from automated live evidence
