# Proposal

## Why

The reviewed weekly briefing is too generic to save an AI solution architect
time, while operational metadata hides its TL;DR. The current pipeline compresses
specific reporting into short thematic notes and then enforces a 900-word minimum,
which encourages expansion rather than useful architectural signal.

## What Changes

- Show only the browser-local generation timestamp before the TL;DR on a healthy
  briefing; retain concise exceptional stale/failure notices, not a diagnostics
  block or read/cache/cutoff/window counters.
- Remove the redundant main-page applied-filter badge row. Preserve actual
  filtering and research-context snapshots attached to submitted answers.
- Review all eligible stored news, but select concrete, significant changes that
  affect AI architecture decisions. Deduplicate repeated announcements and omit
  routine promotions, generic trends and business-as-usual reporting.
- Preserve named products, actual changes, availability, supported quantitative
  facts and caveats through generation. Explain their architectural implications
  without inventing baselines, benchmark results or deployment guarantees.
- Treat five minutes as an estimated reading ceiling, not a word target. Produce
  shorter output for fewer meaningful changes and a distinct no-material-change
  result when evidence contains news but no qualifying signal.
- Derive the TL;DR from the selected completed briefing in the same run; preserve
  citations, collapsed full content, daily schedule, protected reads and audited
  retries/accounting.

## Capabilities

### New Capabilities

- `architect-focused-briefing`: Selective, specific architectural intelligence
  with concise briefing presentation and no forced prose length.

### Modified Capabilities

None in main specs: browser briefing is currently an active delivered slice,
not an archived main capability.

## Impact

A small [PRD-3](../../../docs/prd-3.md) refinement over the deployed
[daily briefing](../2026-11-07-daily-news-briefing/proposal.md). Affects worker editorial
contracts/prompts/selection, shared and browser length/outcome validation,
panel/main-page markup, focused tests and owning documentation.

Intentional conflict: the parent's active contract still requires 900-1,100
words and visible window/status metadata. Apply must reconcile those directly
related planning requirements with the approved new behavior before code changes;
this proposal does not retroactively close the parent's scheduled/quality checks.

No new resources, model choice, dependencies, embeddings, identity, consent,
scope, scheduling policy, database service or monetary caps. No new regional
capacity decision is needed; inference usage remains measured. Broader
enrichment changes, raw-article fetching/web research, per-user personalization,
and restarting parked evaluations are out of scope.
