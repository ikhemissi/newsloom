# Design

## Context

See [proposal](proposal.md). App currently renders a news-heading row containing
the eyebrow, h1, description and Refresh/Clear search, followed by a separate
flex-wrapped filter form. The heading ref is also a Back-to-news focus fallback.
Existing component/browser tests locate it by accessible role.

## Goals / Non-Goals

**Goals:** Remove the visible header's vertical cost and integrate its action
with filters while retaining semantics and focus behavior.

**Non-Goals:** New controls, changes to HTTP/A2A requests, detail layout, theme,
pagination, search/filter state, configuration or infrastructure.

## Decisions

- Replace the visible news-heading wrapper with an sr-only h1 retaining its ref,
  dynamic accessible name and programmatic focus target. Remove the eyebrow and
  intro, not merely their text inside a still-sized wrapper.
- Move the existing conditional Refresh/Clear search action into filter-bar next
  to Apply/Reset. Set `type="button"` explicitly so the form does not submit
  draft filters inadvertently; keep existing handlers/loading rules.
- Retain search's submitted query/relevance/bound information as one compact
  conditional line. Do not retain a large visible search heading as a substitute.
- Reuse existing flex-wrap styling; remove only directly unused header spacing
  rules. Keep detail h1s visible and independently scrollable agent layout intact.
- Test desktop toolbar containment/alignment and absence of hero geometry, plus
  narrow wrapping, accessible heading/focus and actual request arguments. A
  source-string deletion alone is not proof of recovered space.

## Risks / Trade-offs

- Hidden heading breaks Back focus -> keep its ref/tabIndex and existing
  navigation regression; distinguish semantic presence from visible layout.
- Moving buttons into a form changes behavior -> explicit non-submit types and
  draft-versus-applied component assertions.
- Toolbar becomes too wide -> reuse wrapping and test at the existing mobile
  viewport rather than adding an extra persistent row.

## Migration Plan

Run focused UI/browser/axe checks and the repository gate before a reviewed
immutable UI-image-only rollout. Verify unchanged configuration/backends and
record actual layout/CI evidence. Preserve unrelated work and open acceptance
ledgers; do not inherit an acceptance exception or archive automatically.
Rollback is the matching retained UI image through a fresh reviewed owning plan.
