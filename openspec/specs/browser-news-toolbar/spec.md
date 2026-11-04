# browser-news-toolbar Specification

## Purpose
Use the main news view's vertical space for filters and reporting rather than
a decorative introductory block, without losing accessible orientation or
changing the meaning of browsing controls.

## Requirements

### Requirement: Compact main news layout
The main news view SHALL omit the visible eyebrow, large news heading,
introductory paragraph and their dedicated layout spacing. It SHALL retain an
accessible heading/focus target without a visible hero gap. Article-detail
titles and the top search/navigation SHALL remain unchanged.

#### Scenario: A reader opens the main news view
- **WHEN** latest or filtered news is displayed
- **THEN** the quoted introductory block is absent from visible layout
- **AND** filters/news are not preceded by an empty replacement hero
- **AND** the semantic heading remains available for assistive navigation and
  detail-to-news focus restoration

#### Scenario: A reader searches or opens detail
- **WHEN** search results are displayed
- **THEN** concise query/bounded-result context remains without a large hero
- **WHEN** an article-detail page is displayed
- **THEN** its visible article title and navigation are preserved

### Requirement: Refresh belongs to the filter toolbar
The existing Refresh action SHALL occupy the same toolbar as source/category/
date and Apply/Reset controls. Active search SHALL retain its existing Clear
search action in that toolbar. Actions MUST remain keyboard-accessible and
wrap without clipping on narrow screens.

#### Scenario: A reader refreshes with unsent filter edits
- **WHEN** Refresh is selected
- **THEN** it reloads the applied browse snapshot, not draft filters
- **AND** it does not accidentally submit Apply, run semantic search or invoke A2A

#### Scenario: A reader clears search or uses a narrow viewport
- **WHEN** Clear search is selected
- **THEN** the submitted query clears while applied filters remain, as before
- **WHEN** the viewport cannot fit one row
- **THEN** the toolbar wraps naturally with labelled, operable controls and no
  horizontal clipping or separate hero-sized refresh row
