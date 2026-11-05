# Proposal

## Why

There is no way for a reader to say "this briefing or answer was wrong or useful".
Quality problems surface only when someone notices and reports them in a chat, and
the evals cannot learn from real usage. A lightweight thumbs up/down with an optional
comment, stored with enough context to reproduce the case, closes that loop.

## What Changes

- Thumbs up/down with an optional short comment on the daily briefing (TL;DR and
  full briefing) and on each agent research answer.
- Feedback is stored in PostgreSQL through the existing browser API, under a new
  delegated `feedback.write` scope and an insert-only database grant.
- Keep every published briefing (TL;DR and full briefing) in an append-only history.
  Today only the latest is kept: each publish overwrites one row, so older briefings
  and their versions are lost unless a guarded refresh audited them. Backfill the
  current briefing and the audited prior versions.
- Briefing feedback references a briefing version from that history.
  Research feedback stores a snapshot of the question, answer, citations and filters
  only when the reader submits feedback; answers are otherwise still not persisted.
- Readers are pseudonymous: a one-way hash of their Entra object ID allows
  deduplication ("latest vote wins") without storing who they are.
- A reviewer-only page lists feedback and exports thumbs-down items for triage.
  A local script turns reviewed exports into eval regression cases kept out of git.

## Capabilities

### New Capabilities

- `user-feedback`: capture, storage, review and export of reader feedback on
  briefings and research answers.
- `briefing-history`: retention of every published briefing for evaluation.

### Modified Capabilities

None. New endpoints extend the browser API without changing existing behavior.

## Impact

[PRD-3](../../../docs/prd-3.md) phase, after the delivered briefing and research UI.
Touches the UI, the MCP app's HTTP API, a new migration, the MCP and UI Entra app
registrations (new delegated scope and admin consent, a `Feedback.Reviewer` app
role) and a local triage script. No new Azure resource, model, region or cost
beyond negligible storage.

Identity decision surfaced here: the new scope and app role change the MCP/UI app
registrations and need tenant admin consent, applied through the existing identity
layers. Out of scope: automatic upload to Foundry datasets, feedback on news search
results, notifications, and editing others' feedback.
