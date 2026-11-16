# Design

## Context

`EvidenceState.web_offered` checks only discovery mode, the search count and the
evidence budget. The `conversation` JSON artifact carries `follow_ups` and
`cited_item_ids`; the web app validates it with a strict schema.

## Decisions

- **Constraint check in `web_offered`:** discovery and no source, category, tags,
  `from` or `to` in the request filters. `authorize` already rejects
  `search_web` when not offered (`research_web_not_offered`), so a planned search
  fails before dispatch.
- **`ResearchResult.web`:** the controller returns the cited `WebResult`s in the
  order `render_answer` numbers them (first citation order), so the artifact's
  numbers match the `[Wn]` markers. Serving adds
  `web_results: [{number, title, url, snippet}]` to the artifact; always present
  (possibly empty) so callers see one shape.
- **Web app:** `web_results` is an optional array in the strict schema, bounded
  to 10, and not displayed.
- **Rollout:** web app first, then the agent.

## Risks

- **Fewer web answers:** constrained questions about recent changes no longer
  reach the web. Callers can drop the constraint to allow it.
- **Larger artifact:** at most 10 snippets of at most 1,000 characters, within
  the existing response limits.
