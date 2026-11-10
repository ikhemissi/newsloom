# Design

## Context

The agent plans over four MCP tools with structured outputs, executes calls
itself through a delegated MCP session and validates every citation against
stored evidence. It has no web access. Foundry's Responses API can call a remote
MCP server through a project connection that holds the server's credential.

## Decisions

- **Project and connection:** new `web-research` layer: Foundry project
  `research-newsloom-<env>` on the existing account; the agent identity gets
  Foundry User on that project only. The connection (custom keys, MCP target
  `https://api.microsoft.ai/v3/mcp`, header `x-apikey`) is created by
  `newsloom-platform set-webiq-connection`, which reads the key from a hidden
  prompt and PUTs it through Azure Resource Manager; Terraform never sees it.
  Rotation reruns the command. `WEB_RESEARCH_ENABLED` (default false) gates the
  tool.
- **Execution:** `search_web(query)` runs one Responses call on the project with
  the enrichment model, the MCP tool restricted to Web IQ's web search tool,
  `require_approval: never`, and an instruction to only call the tool. The
  controller reads the raw `mcp_call` output, parses at most 5 results
  (title ≤ 200, URL https, snippet ≤ 1,000 characters) and discards the model's
  own text. Timeouts, MCP errors and malformed results fail the web call only;
  the answer then states that the web could not be reached.
- **Evidence and rendering:** web results get IDs `W1…`; claims carry either
  stored `evidence_ids` or `web_ids`. Rendering keeps stored claims first, then
  "From the web" claims, then `[n] url` and `[Wn] url` citation lines, and
  replaces the fixed "web search were not accessed" line when the web was used.
- **Budgets:** at most 2 web searches per request, counted within the existing 8
  tool calls; web results count within the 10 evidence items.

## Risks

- Web content can carry instructions: treated as data, delimited, never tools.
- The key is a long-lived secret held by Foundry: access to the project
  connection is limited to the operator; reviewed from the week after Ignite.
- Web IQ terms and data handling apply to the queries.
