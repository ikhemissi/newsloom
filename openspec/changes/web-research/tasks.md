# Tasks

## 1. Platform

- [x] 1.1 Remove the `web-research` project layer and `set-webiq-connection`; delete the unused `research-newsloom-<env>` project (user-approved); Terraform-manage the Web IQ resource replacing `testwebiqtoberemoved`; document the managed-identity binding; mark the key-exception ADR superseded.
  - Evidence (2026-11-10): `web-research` preview showed 1 add (`webiq-newsloom-dev`) and 2 destroys (the empty `research-newsloom-dev` project, 0 connections, and the agent's role assignment on it); applied. The user connected the new account in Web IQ profiles and bound the agent identity's client ID. `testwebiqtoberemoved` was deleted (ARM 404 afterwards), and a request from the agent container with its managed identity still returned 200 with 10 results. `Microsoft.WebIQ` exposes only accounts, custom search configurations and usages in ARM, so the binding stays a manual step.

## 2. Agent

- [x] 2.1 `search_web` tool: managed-identity token, `POST /v3/search/web`, result parsing and limits, failure handling; tests with a fake Web IQ endpoint.
- [x] 2.2 Planner and evidence: web IDs, claim `web_ids`, budgets, "From the web" rendering, disabled-by-default; preview locally with the real connection on stored-news gaps.
  - Preview (2026-11-15, `research-preview.sh --conversation web`, model local, Web IQ from the agent container with its managed identity): the first prompt never used the web (it added an October publication-date filter, found nothing and stopped). After adding the no-invented-dates rule, the web rule in the instructions and the per-turn `web_note`, three consecutive runs used the web on every turn; "What's new in Microsoft Foundry in October 2026?" listed the roundup's changes cited `[W1]` to the original post, and "has any of that changed since?" summarised the web results and stated it could not confirm later changes. A claim with no evidence once failed validation; the synthesis schema now requires stored or web IDs per claim. Turn usage was about 6–9k input and 240–430 output tokens with one Web IQ search per turn. The keyword stand-in for stored search found no stored roundup in this preview; the live check uses vector search.

## 3. Web

- [x] 3.1 Parse and render `[Wn]` web citations, labelled as web sources; tests.

## 4. Deliver

- [x] 4.1 Docs (`docs/agent.md`, `docs/ui.md`, `docs/adrs.md`, `docs/known-gaps.md`); `bash scripts/check.sh --all`; `npm run spec:check`.
- [ ] 4.2 Deploy through azd previews; signed-in check on a stored item that only points to its changes; record searches, tokens and cost.
  - Deployed 2026-11-15: agent revision 11 (preview: new image, build revision and `WEB_RESEARCH_ENABLED=true` only; `verify-agent` readback succeeded) and web revision 21 (preview: image and build revision; the apply also re-added the two governance tags that had been removed from the UI identity; `verify-ui` succeeded). The first web apply hit a 403 on the Terraform state after the governance pass; `newsloom-platform unblock-state` reopened it.
  - Open (user is away): a signed-in check in the browser on a stored item that only points to its changes (for example the Foundry October roundup), and live Web IQ usage and cost per request. The only signed-in test client (`newsloom-agent verify-research`) needs the user's browser sign-in, so it was not run.
