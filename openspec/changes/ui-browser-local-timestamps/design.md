# Design

## Context

See [proposal](proposal.md). App has three separate local `toLocaleString`
render sites: article cards, detail and read metadata. HTTP DTOs already
require offset-aware timestamps. Existing date-filter tests cover local-calendar
DST boundaries, but browser tests do not set a timezone or freeze the clock.

## Goals / Non-Goals

**Goals:** Share consistent instant presentation and a low-cost display clock.
**Non-Goals:** Timestamp normalization, source correction, clock synchronization,
new network work, filter changes or a timezone preference/settings subsystem.

## Decisions

- Use native Intl formatting with the browser's locale/default timezone and
  `timeZoneName: "shortOffset"`; retain the existing date/time detail. Do not set
  UTC, hardcode a region or add/subtract an offset before formatting. Recreate
  the shared formatter when display state refreshes so timezone changes apply.
- Reuse a small timestamp presentation helper/component at all three sites.
  Keep the raw ISO datetime; show a separate inert textual future badge only
  for article dates, not read metadata. Do not infer publication intent.
- Compare epoch instants against one shared App clock, not formatted dates.
  Refresh once per minute and on window focus/visible-document resumption;
  clean up timers/listeners on teardown. No per-card timers or fetch effects.
- Keep server ordering, microsecond-bearing timestamp strings, date shortcuts,
  response cache-age values and immutable A2A snapshots unchanged.
- Test controlled locales/zones and clocks. Include Paris/New York midnight,
  DST, a fractional offset, equal/past/future instants, clock crossing,
  resumption, no extra requests and the existing compact/mobile/axe journey.

## Risks / Trade-offs

- Incorrect device clock can misclassify future dates -> label relative to the
  browser clock; do not claim a publisher error or silently correct the data.
- Locale/ICU punctuation varies -> assert meaningful date/offset parts rather
  than hardcoding one host's formatting everywhere.
- Hidden tabs throttle timers -> resumption re-evaluates; active changes can
  lag up to one minute, avoiding a second-by-second render of up to 200 cards.

## Migration Plan

Run local/browser/primary checks and update the owning UI runbook, then prepare
a fresh reviewed UI-image-only rollout. Preserve existing configuration and
backends; verify pinned assets and actual available Azure behavior. Missing
signed-in acceptance requires its own explicit record/approval, not an inherited
exception. Rollback uses the retained matching UI image through native azd.
