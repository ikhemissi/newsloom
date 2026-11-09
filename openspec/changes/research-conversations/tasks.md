# Tasks

## 1. Agent

- [ ] 1.1 Add bounded `history` to the research request with validation tests (limits, unknown fields, instruction-shaped content); pass it to planning and synthesis as untrusted context; allow history-cited IDs as detail targets within the existing budget.
- [ ] 1.2 Add `follow_ups` to synthesis and the optional JSON artifact when accepted; keep text-only responses byte-identical; record history and follow-up token usage. Preview locally on real questions with record/replay before deploying.

## 2. Web

- [ ] 2.1 Conversation panel (side panel and mobile sheet), threads in session storage, follow-up buttons, new conversation, scroll-into-view, cleared on sign-out; component, browser and axe tests on desktop and phone widths.

## 3. Deliver

- [ ] 3.1 Update `docs/agent.md`, `docs/ui.md` and PRD-3 capability notes; run `bash scripts/check.sh --all` and `npm run spec:check`.
- [ ] 3.2 Deploy the agent then the web app through azd previews; verify readbacks; the user runs a three-turn conversation in their browser; record measured token usage per follow-up.
