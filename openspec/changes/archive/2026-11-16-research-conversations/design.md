# Design

## Context

The agent (`services/agent`) serves A2A with a `ResearchRequest` data part
(question, item IDs, filters, preferences), plans tool calls over four MCP tools,
synthesises cited claims and returns one `text/plain` artifact ending in
citation lines. `context_id` is accepted but carries no state. The web research
client streams progress and the final artifact; the panel renders below the
news column on narrow screens.

## Goals / Non-Goals

**Goals:** coherent follow-ups without new storage; visible answers; backwards
compatibility for existing clients and evaluations.

**Non-Goals:** server-side memory, web search, multi-user threads.

## Decisions

- **History in the request** (`history: [{question, answer, cited_item_ids}]`,
  ≤3 turns, ≤12 KiB) validated like the question. Planning and synthesis prompts
  receive it in a delimited "conversation so far" block marked as untrusted.
  Cited IDs from history are allowed as detail-read targets (same tool budget),
  so the agent can re-read evidence instead of trusting old answer text.
  Alternative: agent-side memory keyed by `context_id`; rejected because the
  agent has no storage and runs several replicas.
- **Follow-ups:** synthesis output gains `follow_ups` (0-3 strings, ≤120 chars),
  emitted as a second artifact (`application/json`) only when accepted output
  modes include it. Evaluation fixtures stay text-only, so the frozen baseline
  contract is unchanged.
- **Web:** threads in `sessionStorage` keyed by a random thread ID; the client
  sends the last 3 turns, trimming the oldest answer text first to fit 12 KiB.
  Panel layout uses CSS (side panel ≥ 1024px, sheet below) with a focus trap
  on the sheet; the newest answer is scrolled into view on completion.

## Risks / Trade-offs

- [Prompt injection through stored previous answers] → history is caller
  data, delimited and given no authority; evidence rules unchanged.
- [Token growth] → 12 KiB cap and 3 turns; usage recorded per request.
- [Follow-up suggestions drift outside stored news] → suggestions are plain
  questions; answering them goes through the same evidence rules.

## Migration Plan

Deploy the agent first (accepts requests with and without history), then the
web app. Rollback: redeploy previous images; old web clients never send history.

## Open Questions

None blocking.
