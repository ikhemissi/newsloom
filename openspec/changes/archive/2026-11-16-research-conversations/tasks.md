# Tasks

## 1. Agent

- [x] 1.1 Add bounded `history` to the research request with validation tests (limits, unknown fields, instruction-shaped content); pass it to planning and synthesis as untrusted context; allow history-cited IDs as detail targets within the existing budget.
- [x] 1.2 Add `follow_ups` to synthesis and the optional JSON artifact when accepted; keep text-only responses byte-identical; record history and follow-up token usage. Preview locally on real questions with record/replay before deploying.
  - Preview (2026-11-10, `scripts/research-preview.sh`, gpt-5.4-mini, recorded week, keyword search standing in for vector search): the first prompt left follow-ups empty and answered "and what about AWS?" from the earlier Foundry items; after adding the follow-up rule and the explicit history decision, later runs searched for AWS on the follow-up, re-read the earlier items for "which of these", and returned three reader-style follow-ups. Usage per turn was about 2–9k input and 70–460 output tokens (history adds roughly 1–3k). Misses seen across 9 turns came from existing planner behaviour, not history: a self-added category filter that the keyword stand-in could not match, one `research_repeated_tool` and one `research_citation_unknown` (validation rejected it). The live check with vector search remains part of 3.2.

## 2. Web

- [x] 2.1 Conversation panel (side panel and mobile sheet), threads in session storage, follow-up buttons, new conversation, scroll-into-view, cleared on sign-out; component, browser and axe tests on desktop and phone widths.

## 3. Deliver

- [x] 3.1 Update `docs/agent.md`, `docs/ui.md` and PRD-3 capability notes; run `bash scripts/check.sh --all` and `npm run spec:check`.
- [x] 3.2 Deploy the agent then the web app through azd previews; verify readbacks; the user runs a three-turn conversation in their browser; record measured token usage per follow-up.
  - First signed-in try (2026-11-10): a Vertex question worked; "and what about AWS?" showed nothing twice because the planner repeated a call (`research_repeated_tool`) and the error appeared outside the panel, and the third attempt answered about AWS in general. Fixed: repeated calls are dropped, research errors show in the panel, follow-ups keep the earlier topic, and the planner no longer invents source/category filters. Preview after the fix: the Foundry conversation's AWS turn searched AWS agents/Bedrock and cited 5 AgentCore/Bedrock items; the recorded week has too little Vertex content to judge that scenario offline.
  - Signed-in check (2026-11-16): two failures (`research_evidence_limit` after three searches; `research_unknown_item` on a follow-up re-reading an earlier citation, rejected by the MCP adapter before dispatch) were fixed in #44, and an intermittent `research_citation_unknown` (an answer citing an earlier item it had not re-read) in #45; agent revisions 12 and 13, web revision 22, `verify-agent` and `verify-ui` succeeded. The user then asked about Vertex AI and followed with "and what about AWS?": both answered with citations (09:40:52 UTC: 7 tool calls, 4 model calls, 16,550 input and 579 output tokens; follow-up 09:42:02 UTC: 2 tool calls, 3 model calls, 11,548 input and 431 output tokens). Finding: the follow-up answered with AWS news in general rather than AWS's AI platform; the user accepted it ("this still works for me"). A third signed-in turn ("which of these…") was not run; the three-turn local preview after #45 passed all turns. Recorded in known gaps.
