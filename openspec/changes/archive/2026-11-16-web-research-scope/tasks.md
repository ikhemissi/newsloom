# Tasks

## 1. Agent

- [x] 1.1 Offer `search_web` only in unconstrained discovery; test that constrained and selected requests are not offered the web and a planned search fails before dispatch.
- [x] 1.2 Return the cited web results in `[Wn]` order from the controller and add `web_results` to the `conversation` artifact; tests for numbering, empty lists and text-only callers.

## 2. Web

- [x] 2.1 Accept the optional `web_results` field in the strict conversation schema; tests.

## 3. Deliver

- [x] 3.1 Update `docs/agent.md` and `docs/ui.md`; run `bash scripts/check.sh` and `npm run spec:check`; preview the web conversation locally.
- [x] 3.2 Deploy the web app, then the agent, through azd previews; verify readbacks.
  - Local (2026-11-16): new tests for constrained discovery (source, category, tags, from, to), cited web results in `[Wn]` order and the web app accepting `web_results`; 250 agent tests and the web unit tests pass. Preview `research-preview.sh --conversation web` with real Web IQ: both unconstrained turns used the web, no failures.
  - Local (2026-11-16): new tests for constrained discovery (source, category, tags, from, to), cited web results in `[Wn]` order and the web app accepting `web_results`; 250 agent tests and the web unit tests pass. Preview `research-preview.sh --conversation web` with real Web IQ: both unconstrained turns used the web, no failures.
  - Deployed 2026-11-16 after #47: web revision 23 first (preview: image, build revision and the governance tags on the app and its identity; `verify-ui` succeeded), then agent revision 14 (preview: image, build revision and tags; `verify-agent` readback succeeded).
