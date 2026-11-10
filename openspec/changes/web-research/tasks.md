# Tasks

## 1. Platform

- [x] 1.1 Remove the `web-research` project layer and `set-webiq-connection`; delete the unused `research-newsloom-<env>` project (user-approved); Terraform-manage the Web IQ resource replacing `testwebiqtoberemoved`; document the managed-identity binding; mark the key-exception ADR superseded.
  - Evidence (2026-11-10): `web-research` preview showed 1 add (`webiq-newsloom-dev`) and 2 destroys (the empty `research-newsloom-dev` project, 0 connections, and the agent's role assignment on it); applied. The user connected the new account in Web IQ profiles and bound the agent identity's client ID. `testwebiqtoberemoved` was deleted (ARM 404 afterwards), and a request from the agent container with its managed identity still returned 200 with 10 results. `Microsoft.WebIQ` exposes only accounts, custom search configurations and usages in ARM, so the binding stays a manual step.

## 2. Agent

- [ ] 2.1 `search_web` tool: managed-identity token, `POST /v3/search/web`, result parsing and limits, failure handling; tests with a fake Web IQ endpoint.
- [ ] 2.2 Planner and evidence: web IDs, claim `web_ids`, budgets, "From the web" rendering, disabled-by-default; preview locally with the real connection on stored-news gaps.

## 3. Web

- [ ] 3.1 Parse and render `[Wn]` web citations, labelled as web sources; tests.

## 4. Deliver

- [ ] 4.1 Docs (`docs/agent.md`, `docs/ui.md`, `docs/adrs.md`, `docs/known-gaps.md`); `bash scripts/check.sh --all`; `npm run spec:check`.
- [ ] 4.2 Deploy through azd previews; signed-in check on a stored item that only points to its changes; record searches, tokens and cost.
