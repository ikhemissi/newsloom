# Design

## Context

The agent plans over four MCP tools with structured outputs, executes calls
itself through a delegated MCP session and validates every citation against
stored evidence. It has no web access. Web IQ accepts Entra app-only tokens for
application (client) IDs bound in Web IQ profiles; a probe from the agent
container with its managed identity returned `webResults` (title, url, content,
lastUpdatedAt, crawledAt, language, isAdult) and `riskLevel`.

## Decisions

- **Identity:** the agent's managed identity client ID is bound in Web IQ profiles
  (a manual step recorded in the runbook); the agent requests a token for
  `https://api.microsoft.ai/.default`. No key, Foundry project or connection is
  used; the earlier `web-research` project layer and `set-webiq-connection`
  command are removed and the unused project deleted. The Web IQ resource is
  Terraform-managed (replacing the portal-created test resource).
  `WEB_RESEARCH_ENABLED` (default false) gates the tool.
- **Execution:** `search_web(query)` posts `{"query": ...}` to
  `https://api.microsoft.ai/v3/search/web` (10-second timeout, response ≤ 1 MiB) and
  keeps at most 5 `webResults` that are not `isAdult`, with an https `url`, title
  ≤ 200 characters, `content` cut to 1,000 characters and `lastUpdatedAt`.
  401/403, timeouts and malformed responses fail the web call only; the answer
  then states that the web could not be reached.
- **Evidence and rendering:** web results get IDs `W1…`; claims carry either
  stored `evidence_ids` or `web_ids`. Rendering keeps stored claims first, then
  "From the web" claims, then `[n] url` and `[Wn] url` citation lines, and
  replaces the fixed "web search were not accessed" line when the web was used.
- **Budgets:** at most 2 web searches per request, counted within the existing 8
  tool calls; web results count within the 10 evidence items.

## Risks

- Web content can carry instructions: treated as data, delimited, never tools.
- Web IQ access depends on the binding in Web IQ profiles; a missing binding
  shows as 401 and disables web results for that request.
- Web IQ terms and data handling apply to the queries.
