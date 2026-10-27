# Proposal

## Why

[Step 2.1 is delivered](../../../docs/agent.md#verified-skeleton-archival), but its
single-item briefing cannot compare news or adapt an explanation to a reader's
question. [PRD-2 Step 2.2](../../../docs/prd-2.md#delivery-plan) should turn one
or multiple MCP news items into a bounded, cited answer tailored to preferences
supplied in the current request.

## What Changes

- Add an explicit research operation alongside the unchanged `recent-news`
  demonstrator. Accept a question, optional selected stored-item IDs and filters,
  and request-local language/audience/detail/focus preferences.
- Use a finite model-selected loop over only the four existing read-only MCP
  tools, with the originating user's secretless OBO and one shared deadline.
  Discover, search and compare stored items rather than offering an unbounded
  autonomous agent or a second retrieval pipeline.
- Separate trusted controls from untrusted questions/news; enforce typed tool
  calls, caller constraints, aggregate budgets and request-owned cleanup.
- Stream safe progress, then expose only a schema/citation-validated answer.
  Resolve citation IDs to the exact retrieved URLs in application code. State
  no-match, missing selected items, incomplete coverage and absent supporting
  detail explicitly; summaries are not access to full articles or the web.
- Preserve the delivered identity, authorization, privacy, recent-news client
  behavior, workload permissions and runtime isolation.
- Record web enrichment and persistent preferences/memory/Work IQ as
  [future TODOs](../../../docs/prd-2.md#deferred-research-todos), not implicit
  capabilities of this slice. The user chose to proceed without a toolbox when
  it was not ready in the retained environment.

**Prerequisites:** the
[verified skeleton archive](../archive/2026-10-27-agent-skeleton/tasks.md#verified-archival),
archive commit `2c160e395bf2e0106a0d910c1118292da4f48cff` and
[passing exact-SHA CI](https://github.com/ikhemissi/newsloom/actions/runs/40559574136).
This proposal permits planning only, not implementation, inference or deployment.

**Out of scope:** external web search/fetching, Foundry project/toolbox creation,
new models/capacity/grants, Responses API, direct database access, application-only
MCP, memory or Microsoft 365 data access, persistent conversations, UI selection,
automatic deployment, and Step 2.3's frozen phase-wide evaluation baseline.
Focused hostile, citation and manual research cases remain required here;
deferring the phase-wide study does not waive this slice's acceptance.

## Capabilities

### New Capabilities

- `news-research`: Request-local, preference-aware research over selected or
  discovered stored news, with bounded delegated tools, validated citations,
  honest evidence limits and hostile-content isolation.

### Modified Capabilities

- `a2a-serving`: Advertise and accept an explicit research skill only when
  implemented/enabled, while preserving all recent-news and caller-lifetime
  guarantees. Progress and validated answer emission must be described truthfully.

## Impact

- **Code to change later:** agent request contracts, serving/card/client,
  delegated tool session, model orchestration and safe aggregate telemetry;
  focused tests beside existing agent HTTP/delegation/generation/privacy tests.
  Extend typed client DTOs without importing the MCP server into the agent.
- **Infrastructure:** an agent-only image/configuration update in retained azd
  state, not a rebuild of MCP or another workload. No new resource or identity
  layer is planned. Keep one 0.25 CPU/0.5 GiB replica unless a separate review
  approves a change after measured memory/concurrency checks.
- **Dependencies:** prefer the pinned Python 3.15 Agent Framework/OpenAI/MCP
  stack. Validate structured planning/tool-result compatibility locally; do not
  adopt a Foundry/Responses connector or upgrade unrelated dependencies silently.
- **Identity/capacity/cost:** OBO already passed, but multiple calls still need
  actual same-user verification. Retain the existing chat-only deployment and
  region; recheck current availability, shared quota, token/search cost and the
  proposed finite profile before separately approved Azure acceptance.
  Semantic `search_news` uses MCP's existing embedding permission, never a new
  agent embedding grant.
- **Toolbox finding:** official
  [Toolbox](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox)
  and [Web Search](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/web-search)
  documentation support a managed MCP route. Read-only inspection on 2026-10-27
  found the retained AIServices account has project management disabled, zero
  Foundry projects and no configured project/toolbox endpoint. This is a current
  environment prerequisite gap, not a claim that Microsoft lacks the feature;
  no creation, inference or toolbox call was attempted. Revisit authorization,
  region, costs, privacy/display terms and pinned-client compatibility separately.
