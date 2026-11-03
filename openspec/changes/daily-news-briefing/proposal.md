# Proposal

## Why

Readers want a roughly five-minute overview of the preceding week without asking
the agent a question. The user selected one shared written briefing of roughly
1,000 words, scheduled daily at 05:00 UTC, with a visible TL;DR paragraph and
the full summary collapsed by default at the top of the Agent panel.

## What Changes

- Generate a cited, thematic briefing from committed news in the seven days
  ending at the scheduled 05:00 UTC cutoff, independent of browsing filters.
- Derive the TL;DR paragraph from the completed summary in the same daily
  generation workflow, without introducing claims absent from the summary.
  Validate and atomically publish both as one versioned briefing.
- Publish one validated shared artifact per daily slot, with an atomic update
  and durable once-only generation/accounting. Reads never trigger generation.
- Permit an explicitly authorized operator retry after a known validation failure,
  preserving immutable failed-attempt metadata and all original call/cost rows.
  Successful slots and uncertain usage remain protected from retries.
- Provide an authenticated read-only HTTP endpoint under the existing news API,
  retaining delegated `news.read` and authorization before any cache access.
- Show the TL;DR below the panel heading/Close action and above research
  context/composer. Put the entire roughly 1,000-word summary and safe
  original-source citations in an accessible collapsible, closed by default.
  Expanding/collapsing never generates content. Show actual window, generation
  time and freshness.
- Retain the last good briefing with explicit pending/stale/failure states.
  Empty or insufficient evidence is not padded into invented reporting.
- Isolate the scheduled worker's identity, database writes and chat deployment;
  do not give MCP write authority or consume existing pipeline/agent capacity.

## Capabilities

### New Capabilities

- `daily-news-briefing`: Bounded scheduled production, protected shared
  publication and expandable browser presentation of a weekly news briefing.

### Modified Capabilities

None. Existing interactive A2A/MCP, workload-foundation and content-free
telemetry contracts remain intact; this slice owns its additive workload.

## Impact

A bounded [PRD-3](../../../docs/prd-3.md) vertical slice after the delivered HTTP
catalogue and timestamp presentation, with existing phase/evaluation acceptance
left open. Implementation updates the owning capability/ADR/runbook documents,
not the parked evaluation implementation.

Add a briefing worker/package, additive database migrations, read projection/API,
panel component, tests and native azd identity/job layers. New resources are one
Consumption job, its dedicated identity/scoped grants and a separate deployment
of the currently pinned enrichment chat model/version at capacity 10 in the
existing region/account. No new model selection, environment, database service,
cache service, embedding work, user consent or application registration.

Do not introduce a daily dollar cap at this stage. Measure actual model calls,
input/output tokens, latency and estimated model cost in practice, explicitly
distinguishing unobserved usage from zero and hosting/build costs from model
cost. Use those observations to inform a later budget decision. Retain normal
request/context limits, deadlines, bounded retries and duplicate-run prevention;
these are reliability controls, not a daily spending policy.
Verify current price, model availability and quota before enablement; stop
rather than increase capacity or broaden access.
The user's instruction authorizes execution without further confirmation
questions within this scope; tool permission prompts remain outside this plan.

Out of scope: audio, personalization/filter-specific briefings, web search,
saved conversations, history browsing, public regenerate actions, changes to
existing model deployments/roles/schedules, and restarting parked evaluations.
