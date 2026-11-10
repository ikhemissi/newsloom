# Proposal

## Why

Stored news is often a pointer to the real change ("What's new in Microsoft
Foundry | October 2026") and can be out of date by the time it is read. The user
asked for web search through Web IQ so research can go beyond the fetched news
when stored evidence is not enough (2026-11-09/10).

## What Changes

- **Web IQ through a Foundry project connection (user decision 2026-11-10).** A
  new Foundry project `research-newsloom-<env>` holds one connection to the Web IQ
  MCP server. Its API key is entered once by the operator, stored only in that
  connection and never in the repository, azd environment, Terraform state or
  application settings. The agent reaches Web IQ only through the project's
  Responses API with its managed identity (Foundry User on that project).
  This is a recorded exception to the no-keys rule, to be reviewed from the
  week after Ignite in case Web IQ adds Entra and RBAC support.
- **The agent decides (user decision).** A `search_web` planning tool is offered
  in discovery mode when web research is enabled. The planner may use it at most
  twice per request when stored evidence does not answer the question or may be
  out of date. Selected-item requests stay stored-news only.
- **Separate web evidence.** Web results (title, URL, snippet; at most 5 per call)
  are untrusted data like news. Claims cite either stored items or web results;
  the answer renders web claims under "From the web" with their own citations
  (`[W1] url`), and states when the web was used. Text-only callers keep the same
  format with these additional lines.
- **Browser.** Web citations are links like stored ones and are labelled as web
  sources.

Owning slice: PRD-3 research experience; follows `research-conversations`.

Out of scope: fetching full pages, domain allow-lists, per-user Web IQ identity,
web results in the briefing or radar.

Decisions surfaced:
- **Data leaves Newsloom:** planner-written queries (derived from the question
  and stored evidence) go to Web IQ. No tokens or user identifiers are sent.
- **Cost:** about $7 per 1,000 Web IQ searches plus one extra model call per web
  search; bounded by two searches per request and measured in acceptance.
- **Compatibility:** with web research disabled (default), requests, prompts and
  answers are unchanged.
