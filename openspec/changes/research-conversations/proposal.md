# Proposal

## Why

The user's review found that a research answer appears below the search box
and out of view, that there is no way to refine a question, and that the agent
panel sits at the bottom on narrow screens. The agent treats every question as
new, so "and what about AWS?" loses its meaning.

## What Changes

- **Agent memory of the conversation (user decision 2026-11-09).** A research
  request may carry up to the last 3 turns of the same conversation (question,
  answer text and cited item IDs), at most 12 KiB in total. The agent uses them
  to interpret the new question and may re-read the earlier cited items through
  the existing MCP tools; earlier answer text is context, never evidence.
  The client keeps the conversation; the agent stores nothing between requests.
- **Suggested follow-ups.** Each answer may end with up to 3 short suggested
  follow-up questions, returned as a separate JSON artifact only to clients
  that accept `application/json`; text-only clients are unchanged.
- **Conversation panel.** A panel on the right on desktop and a full-height
  sheet on narrow screens shows the thread, keeps the latest answer in view,
  offers the suggestions as buttons and starts a new conversation on demand.
  "Ask about this" on a card or item starts a thread with that item selected.
  Threads live in the browser tab (session storage) and are cleared on sign-out.

Owning slice: PRD-3 research experience; follows `architect-radar-home`.

Out of scope: server-side conversation storage or sharing, web search (Web IQ
change), changing tool access, budgets per request beyond the token accounting
for history.

Decisions surfaced:
- **Client-carried history** rather than server-side memory: no new storage or
  identity, works across agent replicas and restarts, and the caller can only
  supply their own previous turns. History is untrusted input like the question.
- **Cost:** up to about 3k extra input tokens per follow-up question; measured
  in acceptance.
- **Compatibility:** requests without history and text-only clients behave as today.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `news-research`: bounded request-supplied conversation history; suggested follow-ups.
- `browser-research-ui`: conversation panel layout, threads and suggestions.

## Impact

- `services/agent` (request model, planning/synthesis context, follow-up
  artifact, accepted output modes), agent tests and evaluation fixtures.
- `services/web` (research client, panel, session storage), UI tests.
- Docs: `docs/agent.md`, `docs/ui.md`, PRD-3 capabilities.
