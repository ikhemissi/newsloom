# browser-news-filters Specification

## Purpose
Let readers deliberately constrain stored-news browsing and optional research
by source, category and calendar dates without losing visible context or privacy.

## Requirements

### Requirement: Discoverable source and category controls
The UI SHALL offer source/category controls from the authorized stored-news
catalogue, with unrestricted defaults. Values sent downstream MUST use exact
stable IDs, not display labels. Catalogue failures MUST appear explicitly and
MUST NOT silently substitute fabricated choices or relax applied constraints.

#### Scenario: The catalogue loads
- **WHEN** the authorized source/category catalogue is valid
- **THEN** represented sources and category labels populate the controls
- **AND** unrestricted choices remain available without a hidden default constraint

#### Scenario: Catalogue access fails
- **WHEN** authorization, transport or catalogue validation fails
- **THEN** unavailable controls show an explicit error/retry state
- **AND** existing browsing is not presented as having applied an unavailable filter

### Requirement: Explicit coherent browsing filters
Editing a source/category/date control SHALL change only draft state.
Apply and Search SHALL submit a validated snapshot of the selected constraints.
Metadata-only filtering MUST make no embedding or agent call. Combined semantic
search MUST preserve all active constraints and use only existing MCP search.

#### Scenario: A reader applies metadata constraints
- **WHEN** Apply is chosen without a semantic query
- **THEN** one query-less metadata search returns at most 20 eligible items in newest-first order
- **AND** every displayed item satisfies all applied constraints
- **AND** no model or A2A request is dispatched

#### Scenario: A reader edits or searches
- **WHEN** draft controls are edited
- **THEN** no query, embedding or research is automatically dispatched
- **WHEN** Search or Apply is explicitly submitted with a semantic query
- **THEN** relevance-ranked results satisfy the same submitted constraints
- **AND** the UI visibly distinguishes applied filters from unsent draft edits

#### Scenario: Filters are reset or incompatible
- **WHEN** Reset clears filters
- **THEN** a still-submitted semantic query remains active unless separately cleared
- **AND** clearing search retains applied metadata constraints
- **WHEN** a valid source/category combination has no eligible news
- **THEN** an explicit empty result appears without silently broadening or substituting constraints

### Requirement: Precise calendar-date boundaries
The UI SHALL offer Any time, Today, Last 7 days, Last 30 days and a custom
inclusive calendar range. Calendar choices MUST use the reader's local timezone
and translate to UTC-aware inclusive lower/exclusive upper timestamps.
Invalid or reversed ranges MUST fail visibly before dispatch.

#### Scenario: A calendar period is selected
- **WHEN** Today, Last 7 days or Last 30 days is applied
- **THEN** the lower bound is local midnight at the selected first calendar day
- **AND** the upper bound is the next local midnight after today
- **AND** equivalent UTC timestamps include the first boundary and exclude the upper boundary
- **AND** daylight-saving transitions do not turn calendar-day arithmetic into fixed-hour arithmetic

#### Scenario: A custom range is applied
- **WHEN** both valid dates are present and start is no later than end
- **THEN** the first date is included and the end date's next local midnight is exclusive
- **WHEN** a date is missing, invalid or reversed
- **THEN** the UI shows a validation error without a tool or model call

#### Scenario: Any time is selected
- **WHEN** the date restriction is cleared
- **THEN** downstream requests omit both date bounds rather than inventing a recency cutoff

### Requirement: Visible filters constrain explicit research
The agent panel SHALL show the applied source/category/date constraints alongside
any current-news selection. Explicit A2A submission MUST include that validated
context snapshot. Draft changes MUST NOT alter an in-flight request or relabel
its answer; filters MUST NOT cause automatic research.

#### Scenario: A reader sends a research question
- **WHEN** applied metadata constraints and an optional selected story are visible
- **THEN** A2A receives those exact filter fields and selected item ID
- **AND** neither top search text nor publisher content becomes endpoint/tool authority
- **AND** the usual stored-summary/citation limitations remain visible

#### Scenario: Context changes during research
- **WHEN** draft or browsing context changes after Send
- **THEN** the running question retains its immutable displayed snapshot
- **AND** its result is not described as satisfying newly applied constraints
- **AND** no automatic replay or additional generation occurs

### Requirement: Accessible private filter delivery
Filter controls, errors and applied context SHALL be inert, labelled and
keyboard-operable. Deployed verification MUST preserve delegated audiences
and expose only safe outcomes/counts/provenance. Questions, news, credentials
and conversation data MUST NOT become logs or exported browser state.

#### Scenario: The filter journey is verified
- **WHEN** a signed-in reader filters news and explicitly researches a selected item
- **THEN** source/category/date boundaries and visible A2A context are verified
- **AND** keyboard/accessibility and hostile-label checks pass
- **AND** manual regular-browser observations are distinguished from automated Azure evidence

#### Scenario: Verification remains incomplete
- **WHEN** a local, Azure, CI or publication obligation lacks actual evidence
- **THEN** its task remains open and the change is not archived
- **AND** no new test-browser sign-in or credential export bypasses the user's regular-browser workflow
