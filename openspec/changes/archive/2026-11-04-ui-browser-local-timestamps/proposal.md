# Proposal

## Why

The browser already converts timestamps locally, but omitting the timezone makes
future-dated publisher entries look like conversion errors. The reported item's
stored UTC midnight matches its publisher RSS date; the user chose explicit
browser timezone display and future-date labels rather than altered dates.

## What Changes

- Show browser-local date/time with its explicit UTC offset for publication
  timestamps on cards/details and for the latest-page-read timestamp.
- Label stored article dates later than the browser clock as "Future-dated",
  without claiming that the publisher scheduled the article.
- Re-evaluate display state on a bounded shared clock and browser resumption,
  without fetching news, reapplying filters or invoking research.
- Preserve original instants, machine-readable datetime values, server ordering,
  date-filter semantics, cache metadata and the compact toolbar.

## Capabilities

### New Capabilities

- `browser-news-timestamps`: Explicit browser-local instant presentation and
  truthful future-date indications across stored-news views.

### Modified Capabilities

None. Ingestion normalization, HTTP dates and existing calendar filters remain
unchanged; no main capability currently owns browser timestamp presentation.

## Impact

A small [PRD-3](../../../../docs/prd-3.md) UI slice after the compact toolbar.
Touches App timestamp rendering, directly related styling, focused temporal/
component/browser tests and the owning UI runbook.

No dependency, API, database, cache, identity, permission, model or resource
change. No new regional capacity or inference-cost decision is needed. A later
rollout is a fresh, reviewed immutable UI image only.

Out of scope: correcting publisher dates, hiding future articles, clamping to
now, re-ingestion, changing filter boundaries, backend clock synchronization,
evaluation runs or closing earlier unverified acceptance.
