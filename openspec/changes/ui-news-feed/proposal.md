# Proposal

## Why

The user confirmed that the deployed sign-in and cited research answer work, but
wants to browse news first and use the agent only to learn more. A default live
feed makes the product useful without initiating research on page load.

## What Changes

- Deliver a small PRD-3 P3-C07 slice: after sign-in, `/` shows the latest 20
  stored news items, newest first, without a hidden date cutoff or pagination
  completeness claim.
- Display titles, summaries, source/category, publication time and safe links to
  original reporting. Provide explicit loading, empty, error and refresh states.
- Add a top search box using MCP `search_news` on explicit submit. Show bounded
  relevance-ranked results; clearing search returns to latest news. Typing
  alone never calls MCP or the agent.
- Put agent interaction in a right-hand panel with explicit open/close controls,
  collapsed by default. "Ask about this" opens the existing composer with one
  visible removable selected-item context; no question is automatically sent.
  Closing the panel restores the feed's full width. General research stays
  explicitly available, and all agent interaction continues through A2A.
- Read news directly through the official MCP v2 browser client behind a typed
  NewsCatalog interface. The default feed calls only `get_recent_news`; no
  embeddings or generation for default browsing. Explicit semantic search uses
  the existing MCP embedding path, not A2A or a substitute research pipeline.
- Add exact-origin MCP browser CORS and corresponding owning origin preparation/
  readback, preserving existing MCP clients and the agent's OBO path.
- Extend the existing SPA registration with only delegated MCP `news.read`,
  retaining `news.agent`. Acquire separate audience-bound tokens with the
  existing tab-scoped MSAL session; do not use the agent token at MCP.
- Update the owning PRD-3 assignment/ADRs/runbook during implementation. Do not
  fold filters, pagination or the evaluation programme into this slice.

## Capabilities

### New Capabilities

- `browser-news-feed`: A bounded latest-news landing page, submitted MCP search
  and optional right-side item-context A2A research, with no automatic inference.

### Modified Capabilities

- `mcp-serving`: Add exact-origin browser preflight/response handling while
  retaining existing authorization, workload isolation and tool contracts.

## Impact

Prerequisites: the working `ui-spike-and-shell` browser auth/research integration
and delivered MCP recent-news contract. The first UI's full browser evidence and
selective implementation/status publication are still open; record those before
releasing this dependent slice, without requiring PRD-2 quality acceptance or
archiving unverified work.

Implementation surfaces: `services/web` auth/config/data/components/tests,
`services/mcp` ingress/runtime/tests, owning `infra/mcp` and `infra/ui-identity`
inputs, UI runtime configuration/security headers, platform preparation/readback,
root npm lock/checks and related documentation. Reuse existing identities,
workloads, ACA environment and models. No new cloud resource or model is planned;
only the SPA's explicit MCP delegated consent and browser-origin/image settings
change through reviewed owning layers.

The handoff's MCP client 2.4.0 advertises protocol `2026-07-28`; exact negotiation,
browser transport headers, token injection and cancellation require a bounded
compatibility check, not assumed example APIs. Consent may require the user's
admin action, as the first SPA grant did; never add directory roles as fallback.
Default browsing has no model cost. Explicit semantic search uses the existing
bounded MCP query-embedding budget; explicit research keeps existing A2A model
budgets and usage accounting. Hosting remains the current reviewed profile.

Out of scope: filters, pagination/cursors, item-detail routing,
multi-item selection, general caching framework, cached HTTP API, structured
citations, persistent history/preferences, baseline retries, broader grants and
automatic deployment.
