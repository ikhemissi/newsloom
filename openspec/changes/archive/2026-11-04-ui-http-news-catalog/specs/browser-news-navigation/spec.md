# Spec Delta

## Purpose

Let signed-in readers browse the HTTP news catalogue, explicitly continue
newest-first results and open shareable stored-item pages without changing
the agent's A2A interaction or weakening privacy and context boundaries.

## ADDED Requirements

### Requirement: Browser news access uses the authorized HTTP API
All browser catalogue/news/detail requests SHALL use the configured versioned
HTTP API and existing delegated `news.read`. Browser MCP protocol exchanges and
silent MCP fallback MUST be absent. Agent interactions SHALL remain A2A with
their separate audience; agent-side MCP tools MUST remain unchanged.

#### Scenario: A signed-in reader loads or searches news
- **WHEN** latest news, metadata filters, source choices or detail are requested
- **THEN** the browser calls the corresponding authorized HTTP GET route
- **WHEN** a semantic query is explicitly submitted
- **THEN** it calls POST search with typed query/filter fields
- **AND** browsing, detail, typing and opening panels dispatch no research or inference
- **AND** no MCP discovery/tool call or combined news/agent bearer token is used

#### Scenario: A service or response fails
- **WHEN** authorization, admission, deadline, transport or response validation fails
- **THEN** the UI displays the appropriate fixed failure and explicit recovery action
- **AND** it does not invent an empty success, retry automatically, choose an
  untrusted endpoint or fall back to MCP

### Requirement: Existing filtering and bounded search remain coherent
Draft source/category/date edits SHALL dispatch nothing. Apply/Search/Reset/
Clear SHALL preserve their delivered distinct semantics. Default news SHALL
have no hidden date cutoff. Semantic search SHALL retain relevance order,
at most 20 results and an explicit bounded-results description without paging.

#### Scenario: A reader applies or changes constraints
- **WHEN** Apply uses draft filters, Search submits draft text/filters, Reset
  removes metadata constraints or Clear removes the submitted query
- **THEN** the correct complete snapshot is sent and the old continuation is discarded
- **AND** local-calendar UTC mapping, exact IDs and no-inference metadata behavior remain intact
- **AND** semantic results have no Load more control or exhaustive-match claim

### Requirement: Explicit bounded newest-first continuation
Newest-first browsing and metadata filters SHALL initially show at most 20 items
and offer explicit Load more only with a server continuation. Each request SHALL
use the applied immutable filters and 20-item page size. At most 200 distinct
items SHALL be displayed. No background prefetch or semantic paging is allowed.

#### Scenario: A reader loads another browse page
- **WHEN** Load more is selected below the cap with a valid continuation
- **THEN** one request appends eligible items in server order without duplicate cards
- **AND** unsent draft edits cannot alter that page's query/filter snapshot
- **AND** repeated/stale continuations and malformed pages fail visibly instead
  of looping, clearing valid prior cards or silently restarting

#### Scenario: Paging ends, reaches its cap or fails
- **WHEN** the server returns no continuation
- **THEN** the UI shows that no more pages are currently available
- **WHEN** 200 items are displayed and a continuation still exists
- **THEN** the UI distinguishes its display cap from server exhaustion and offers
  an explicit restart using the same applied filters
- **WHEN** append fails or news changes during traversal
- **THEN** prior cards remain with a distinct error/live-data limitation and no
  complete-snapshot guarantee; refresh/restart can begin again

### Requirement: Shareable stored-item pages
The UI SHALL support `/news/<uuid>` through direct load, reload and browser
Back/Forward. Detail SHALL show only the stored public summary/metadata, with
Back to news, safe Open original and explicit Ask about this actions.
Malformed routes, absent items and authorization/transport errors MUST remain distinct.

#### Scenario: A reader opens or shares an item
- **WHEN** an item is opened from news or a valid detail URL is loaded
- **THEN** its exact stored UUID is requested through HTTP detail
- **AND** stored author/date origin/publisher categories are shown when available
- **AND** full publisher articles, arbitrary HTML and caller-selected endpoints
  are not fetched or interpreted
- **WHEN** an explicit sign-in is needed
- **THEN** only the validated same-origin item path can be restored after sign-in,
  without exporting credentials, persisting a question or sending research

#### Scenario: A reader returns or the item is absent
- **WHEN** Back to news or browser Back returns from a locally opened detail page
- **THEN** transient browse items, applied filters, continuation and scroll position
  are preserved within the signed-in view without replaying research
- **WHEN** a directly loaded item has no prior browse view
- **THEN** Back to news opens the normal initial news view
- **WHEN** detail returns 404
- **THEN** an explicit not-found page appears, not an unavailable or empty-news success

### Requirement: Detail and navigation preserve explicit research context
Detail navigation and paging MUST NOT submit A2A work. Ask about this SHALL select
the exact displayed item and open the agent composer without sending. In-flight
and completed research SHALL retain their submitted item/filter snapshot, not
be relabelled under later list/detail context.

#### Scenario: A reader chooses detail context or navigates while researching
- **WHEN** Ask about this is selected while no research is active
- **THEN** the visible item and applied filters describe the next explicit question
- **WHEN** browsing, page append or detail navigation changes after Send
- **THEN** the running request and answer retain their original labelled context
- **AND** no page of items, detail text or search query is secretly appended as instructions

### Requirement: Navigation is accessible, transient and bounded
New controls, detail/error states and pagination SHALL be keyboard-operable,
labelled and inert. Lofi, responsive layout, safe citations and independent agent
scrolling SHALL remain intact. Sign-out MUST cancel reads and clear transient
news/detail/cursor/context state; late responses MUST NOT restore it.

#### Scenario: Keyboard, hostile-content and sign-out journeys are exercised
- **WHEN** a reader opens detail, loads more, returns, signs out or cancels
- **THEN** focus/announcements/loading/error behavior remains usable without
  horizontal clipping or page-wide scrolling of a long agent answer
- **AND** hostile labels/URLs remain inert or disabled
- **AND** no persistent browse/chat store, trace/HAR, token export or content log is created

### Requirement: Explicit measured migration and rollback
The UI image/config/CSP/readback SHALL identify the HTTP endpoint and retained
news scope without changing consent, backend images, models or schedules.
Rollback MUST restore a matching reviewed image/configuration, not silently
switch transport. Missing signed-in Azure evidence SHALL remain explicitly open.

#### Scenario: The UI transport is rolled out
- **WHEN** local contract/browser/accessibility and primary gates pass and the
  immutable UI-only plan is freshly approved
- **THEN** deployed readback verifies the HTTP config/CSP/image and preserved
  identity/backend authority with exact-source implementation/status CI
- **AND** actual regular-browser HTTP/detail/paging/A2A/cache observations are
  distinguished from authored fixtures and unavailable automation
- **AND** no prior UI/API acceptance task is checked without its actual evidence
