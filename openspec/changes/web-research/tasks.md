# Tasks

## 1. Platform

- [x] 1.1 `web-research` layer (Foundry project, agent Foundry User on it) with Terraform tests; `newsloom-platform set-webiq-connection` (hidden prompt, ARM PUT, readback without the key); ADR for the key exception and a dated review note.

## 2. Agent

- [ ] 2.1 `search_web` tool: Responses call with the MCP tool through the connection, raw result parsing, limits, failure handling; tests with a fake Responses endpoint.
- [ ] 2.2 Planner and evidence: web IDs, claim `web_ids`, budgets, "From the web" rendering, disabled-by-default; preview locally with the real connection on stored-news gaps.

## 3. Web

- [ ] 3.1 Parse and render `[Wn]` web citations, labelled as web sources; tests.

## 4. Deliver

- [ ] 4.1 Docs (`docs/agent.md`, `docs/ui.md`, `docs/adrs.md`, `docs/known-gaps.md`); `bash scripts/check.sh --all`; `npm run spec:check`.
- [ ] 4.2 Operator enters the key; deploy through azd previews; signed-in check on a stored item that only points to its changes; record searches, tokens and cost.
