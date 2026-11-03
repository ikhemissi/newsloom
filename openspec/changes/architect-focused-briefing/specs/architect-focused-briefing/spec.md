# Spec Delta

## Purpose

Help AI solution architects identify concrete changes worth acting on, without
generic trend prose, forced reading length or operational clutter.

## ADDED Requirements

### Requirement: Reader-first briefing presentation
A healthy published briefing SHALL show only its browser-local generation
timestamp before its TL;DR. Explanatory scope prose, ready status, expected cutoff,
window/count metadata and read/cache diagnostics MUST NOT precede or clutter
the briefing. Concise stale/failure/unavailable notices SHALL remain truthful.

#### Scenario: A healthy or exceptional briefing is displayed
- **WHEN** a current artifact is available without a read error
- **THEN** generation time is the only metadata displayed before the TL;DR
- **AND** full briefing/citations remain collapsed by default
- **WHEN** freshness or availability has a problem
- **THEN** a concise exceptional notice and necessary read-only recovery action
  remain, without a verbose diagnostic block

### Requirement: Remove redundant browse badges
The main-page applied-filter badge row SHALL be removed for default and selected
filters, including its reserved spacing. Explicit draft/Apply/Search/Reset
behavior MUST remain unchanged. Research-context snapshots associated with
submitted questions and answers SHALL remain visible and immutable.

#### Scenario: Filters change while a research answer exists
- **WHEN** the reader edits or applies main-page filters
- **THEN** no second browse badge row appears beneath the controls
- **AND** unsent edits still dispatch nothing
- **AND** the existing answer retains the filters actually submitted with it

### Requirement: Select material architectural signals
All eligible stored news SHALL be considered, but output SHALL prioritize
concrete changes affecting AI architecture choices, implementation, operations,
cost, safety or integration. Routine promotion, funding without practical
impact, vague trend commentary and unchanged capabilities MUST NOT be included
merely to fill space. Repeated reporting of the same change SHALL be consolidated.

#### Scenario: A corpus mixes significant changes and routine news
- **WHEN** evidence contains a breaking API change, a materially different
  deployment option and unrelated promotional or routine updates
- **THEN** the architectural changes are prioritized and routine items omitted
- **AND** multiple articles about one announcement support one consolidated item
- **AND** selection is not driven solely by recency, vendor hype or source volume

### Requirement: Preserve specifics and separate implication from fact
Selected items SHALL name the product or capability, state the supported change
and explain why it matters for an architect. Available release status, versions,
numbers and caveats SHALL be preserved when supplied. Missing details MUST NOT
be invented. Architectural implications MUST be distinguishable from reported
facts and conditional when evidence does not establish a guarantee.

#### Scenario: A preview announcement includes a concrete capability and limits
- **WHEN** stored evidence specifies a product, a new capability, preview status
  and a deployment limitation
- **THEN** the briefing retains those specifics and the limitation with citations
- **AND** it does not call the feature generally available or recommend replacing
  production infrastructure without support

#### Scenario: A claimed improvement lacks a supported baseline
- **WHEN** the source does not supply a prior version, benchmark or price comparison
- **THEN** the briefing does not invent a before/after delta, measured improvement
  or savings figure
- **AND** unknown availability or quantitative details stay unknown or are omitted

### Requirement: Five-minute ceiling without a prose minimum
The briefing SHALL have no minimum word count. Its TL;DR and summary narrative
together MUST contain at most 1,000 words, excluding headings/citations, using
200 words per minute as an estimated five-minute ceiling. Fewer significant
changes SHALL produce shorter output. Reading-time cues MUST reflect actual
content length rather than always claiming five minutes.

#### Scenario: A week contains one worthwhile change or output exceeds the ceiling
- **WHEN** only one meaningful change is supported
- **THEN** a concise, specific briefing below 900 words is valid
- **AND** no generic overview or business-as-usual text is added to reach a target
- **WHEN** combined TL;DR/narrative length is 1,000 or 1,001 words
- **THEN** the former meets the ceiling and the latter fails length validation

### Requirement: Honest no-material-change result
A reviewed nonempty corpus with no qualifying architectural signal SHALL
produce a concise no-material-change notice, not padded prose or irrelevant
citations. It MUST remain distinct from an empty news window, unavailable data
and failed generation. The notice MUST describe what was identified in stored
reporting, not claim that no real-world AI changes occurred.

#### Scenario: Every eligible article is routine
- **WHEN** stored news exists but none supports a meaningful architectural change
- **THEN** the reader sees a no-material-change result without a fabricated summary
- **AND** the system does not disguise it as no stored news or a service error

### Requirement: TLDR summarizes the selected changes
For a meaningful briefing, the visible TL;DR SHALL be one concise paragraph
derived from the completed selected summary in the same run. It SHALL lead with
the highest-impact concrete changes and why they matter, not generic statements
about the AI industry. Both parts MUST publish atomically with validated citations.

#### Scenario: The selected briefing describes concrete architectural changes
- **WHEN** its TL;DR is generated
- **THEN** the paragraph names the important changes rather than saying only
  that agents, governance or AI adoption are evolving
- **AND** every factual claim is supported by the completed summary

### Requirement: Preserve the delivered execution boundary
Daily 05:00 UTC shared seven-day windows, delegated news.read, authorization
before cached reads, source-ID constraints, audited operator retries and
content-free accounting SHALL remain. Reads and expansion MUST NOT generate
or alter research. Previously valid published artifacts SHALL remain readable
during the transition; no new cloud authority or spending cap is introduced.

#### Scenario: New editorial behavior is rolled out
- **WHEN** a new result type or length policy is enabled
- **THEN** its API/shared/browser consumers already accept it
- **AND** old artifacts, failed-attempt history and usage remain intact
- **AND** missing quality/scheduled/signed-in acceptance is not labelled complete
