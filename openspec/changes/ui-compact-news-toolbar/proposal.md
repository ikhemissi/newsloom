# Proposal

## Why

The news view's eyebrow, large heading and introductory paragraph consume
vertical space without helping the reader. The user requested their removal
and an inline Refresh action beside the filters.

## What Changes

- Remove the visible news-view hero block, including its eyebrow, large title,
  description and dedicated spacing; leave article-detail titles unchanged.
- Place Refresh in the existing filter toolbar alongside Apply/Reset. Preserve
  the current Clear search action in that same position when search is active.
- Retain a visually hidden semantic heading/focus target and compact submitted-
  search context, without recreating a space-consuming hero.
- Keep all HTTP filtering, refresh/search semantics, pagination, detail history,
  A2A context, lofi and responsive/accessibility behavior unchanged.

## Capabilities

### New Capabilities

- `browser-news-toolbar`: Compact news-view controls with inline refresh and
  preserved accessible orientation and action semantics.

### Modified Capabilities

None in main specs. Existing active browser navigation/filter contracts are
preserved; this is a bounded visual refinement, not a transport or API change.

## Impact

Owns a small [PRD-3](../../../docs/prd-3.md) UI refinement after the deployed
HTTP catalogue. Affects App news header/toolbar markup, directly related CSS,
component/browser assertions and a short owning UI runbook note.

No dependency, resource, identity, permission, model, backend or configuration
change is planned. No new regional capacity or cost decision is needed; any
rollout is an independently reviewed immutable UI image only.

Out of scope: broader redesign, removing detail titles, changing search/filter/
refresh behavior, backend/cache changes, evaluation runs, automatic deployment
or closure/archival of existing unverified acceptance.
