# Tasks

## 1. Agent

- [x] 1.1 Add bounded `history` to the research request with validation tests (limits, unknown fields, instruction-shaped content); pass it to planning and synthesis as untrusted context; allow history-cited IDs as detail targets within the existing budget.
- [x] 1.2 Add `follow_ups` to synthesis and the optional JSON artifact when accepted; keep text-only responses byte-identical; record history and follow-up token usage. Preview locally on real questions with record/replay before deploying.
  - Preview (2026-11-10, `scripts/research-preview.sh`, gpt-5.4-mini, recorded week, keyword search standing in for vector search): the first prompt left follow-ups empty and answered "and what about AWS?" from the earlier Foundry items; after adding the follow-up rule and the explicit history decision, later runs searched for AWS on the follow-up, re-read the earlier items for "which of these", and returned three reader-style follow-ups. Usage per turn was about 2–9k input and 70–460 output tokens (history adds roughly 1–3k). Misses seen across 9 turns came from existing planner behaviour, not history: a self-added category filter that the keyword stand-in could not match, one `research_repeated_tool` and one `research_citation_unknown` (validation rejected it). The live check with vector search remains part of 3.2.

## 2. Web

- [x] 2.1 Conversation panel (side panel and mobile sheet), threads in session storage, follow-up buttons, new conversation, scroll-into-view, cleared on sign-out; component, browser and axe tests on desktop and phone widths.

## 3. Deliver

- [x] 3.1 Update `docs/agent.md`, `docs/ui.md` and PRD-3 capability notes; run `bash scripts/check.sh --all` and `npm run spec:check`.
- [ ] 3.2 Deploy the agent then the web app through azd previews; verify readbacks; the user runs a three-turn conversation in their browser; record measured token usage per follow-up.
