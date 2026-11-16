# Proposal

## Why

Requests with explicit source, category, tag or date constraints ask for stored
news within those limits, yet the agent may still search the web for them, which
relaxes the caller's constraints. Evaluating web-backed answers also needs the
web results the agent actually used: today only their URLs reach the caller.
The user chose to fix both before versioning the agent quality baseline
(2026-11-16).

## What Changes

- **No web for constrained requests.** `search_web` is offered only in discovery
  mode without source, category, tag or date constraints. Selected-item requests
  stay stored-news only, as today.
- **Used web results in the conversation artifact.** For callers that accept
  JSON, the `conversation` artifact adds `web_results`: the cited web results in
  `[Wn]` order, each with number, title, URL and snippet (the same bounded fields
  the planner saw). The text answer and text-only callers are unchanged.
- **Web app** accepts the optional field and ignores it; it is deployed before
  the agent because its artifact parser is strict.

Owning slice: PRD-3 research experience; follows `web-research`, prerequisite of
the `agent-quality-baseline` version 2.

Out of scope: storing web results, showing snippets in the web app, new limits.

Decisions surfaced:
- **Constraints mean stored news.** A caller who names a source or date range
  asks about stored items; answering from the web would silently relax that.
- **Snippets are returned, not stored.** They are third-party data already sent
  to the model; the agent still stores nothing between requests.
