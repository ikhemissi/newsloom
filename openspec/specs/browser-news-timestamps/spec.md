# browser-news-timestamps Specification

## Purpose
Make stored-news timestamps unambiguous in the reader's browser timezone while
honestly identifying source dates later than the reader's current clock.

## Requirements

### Requirement: Explicit browser-local instant display
Article cards, stored-item detail and latest-page-read metadata SHALL display
their original instants in the browser's locale and timezone with a visible
UTC offset appropriate to each instant, including daylight-saving changes.
Machine-readable datetime values MUST preserve the original timestamp.
Existing timestamp-validation failures MUST remain errors, not fabricated dates.

#### Scenario: The same UTC instant appears in different browser zones
- **WHEN** `2026-11-03T00:00:00Z` is viewed in Europe/Paris or America/New_York
- **THEN** the local date/time is respectively November 3 at 01:00 or November 2
  at 19:00, with the corresponding +01:00 or -05:00 offset visibly represented
- **AND** card, detail and read metadata use consistent formatting

#### Scenario: Daylight-saving or fractional offsets apply
- **WHEN** an instant has a different daylight-saving offset or the browser
  uses a fractional-hour zone
- **THEN** the browser's rules determine its displayed time and offset without
  manually shifting the input or assuming whole-hour offsets

#### Scenario: An invalid timestamp is returned
- **WHEN** a catalogue response contains an invalid or offset-less timestamp
- **THEN** existing invalid-response handling rejects it rather than displaying
  an invented date, silently choosing a zone or showing successful empty news

### Requirement: Truthful future-date indication
Cards and detail SHALL show a textual "Future-dated" indication only when their
stored article instant is later than the browser clock. This MUST NOT claim a
scheduled publication, change the instant, hide an article or alter its order.
The indication SHALL be understandable without color or hover.

#### Scenario: Future, equal and past instants are distinguished
- **WHEN** an article instant is respectively after, equal to or before the
  current browser time
- **THEN** only the first receives the indication, regardless of local calendar
  date or equivalent timestamp offset representation
- **AND** the stored date and server-provided result order remain unchanged

### Requirement: Display state follows the current browser context
While active, the UI SHALL refresh time-dependent display state within one
minute and re-evaluate it on focus/visibility resumption. Clock or timezone
updates MUST NOT dispatch catalogue, search, pagination or research requests,
reapply filter drafts, or change server-reported cache-age values.

#### Scenario: A future instant becomes current or the browser zone changes
- **WHEN** the current clock reaches an article instant or the browser timezone
  changes while the page is open
- **THEN** the next display update removes the obsolete future indication or
  shows the new local time/offset
- **AND** resuming a backgrounded page re-evaluates immediately without a reload
- **AND** browse, filter, selected-item and answer context remain unchanged
