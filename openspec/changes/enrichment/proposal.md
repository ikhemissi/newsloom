# Proposal

## Why

Accepted entries currently stop in PostgreSQL's pending queue: there is no
enrichment worker or `news` table. PRD-1 Step 1.4 must turn that verified input into
structured, searchable news before the MCP serving slice can begin.

## What Changes

- Deliver one end-to-end [PRD-1](../../../docs/prd-1.md) enrichment slice, owning
  P1-C04 processing, P1-C05 model enrichment, and P1-C10 runtime visibility.
  Prerequisites are the archived, verified
  [ingestion](../archive/2026-10-23-feed-ingestion/tasks.md),
  [resilience](../archive/2026-10-23-resilient-feed-ingestion/tasks.md), and
  [contextual screening](../archive/2026-10-23-contextual-content-screening/tasks.md)
  slices and the existing Azure platform.
- Use one structured GPT request per logical enrichment attempt for an English
  summary of 2-3 sentences and at most 100 words, one primary category, and 3-5
  concise lowercase tags. Use one embedding request for a 1536-dimensional vector.
- Use the approved 11 categories: Regulations; Models; Agents & Applications;
  Developer Tools; Infrastructure; Research & Evaluations; Security & Safety;
  Governance; Industry & Business; Service Providers; FinOps.
- Governance means technical AI-agent governance and AI gateways,
  including model/tool access policies, approval flows, enforcement and
  auditability. Regulations separately covers laws, regulatory requirements
  and regulator enforcement.
- Add versioned migrations for durable leased queue processing and `news`.
  Complete a queue item and persist its validated news/vector atomically.
  Preserve completed identities for ingestion deduplication and leave quarantine
  untouched.
- Make ingestion and operator queue-depth reporting state-aware rather than
  continuing to count completed history as pending work.
- Implement a real independently deployable enrichment job using the existing
  enrichment identity, model deployments, PostgreSQL, registry, and telemetry.
  First verify 10 live entries immediately; after acceptance, enable at most
  25 entries per run every 30 minutes.
- Require 20 frozen labelled quality cases: all results schema-valid, at least
  18 correct primary categories, plus zero successful instruction overrides in
  separate hostile fixtures. Explicitly confirmed upstream jailbreak-filter
  blocks count as hostile defences and are reported separately; unknown API
  errors still fail. Evaluation must not publish its fixtures as news.

Out of scope: MCP endpoints/search serving, agent/UI work, new model deployments,
scanner changes or quarantine release, feed refetching, additional classification
services, a new queue/vector datastore, and automatic re-enrichment of history.

## Capabilities

### New Capabilities

- `news-enrichment`: structured summaries/classification/embeddings, durable
  leased processing, atomic news persistence, bounded execution and acceptance.

### Modified Capabilities

- `feed-ingestion`: queue-depth visibility excludes completed rows while retained
  identities continue to deduplicate.

## Impact

- Implement the existing [enrichment package](../../../services/enrichment/),
  add only its required existing-workspace dependency families, and keep typed
  `LlmProvider`, `EmbeddingProvider`, and repository interfaces.
- Reuse the normalized entry contract through
  [core](../../../packages/newsloom-core/) without coupling enrichment to the
  ingestion service. Extend [versioned migrations](../../../services/platform/src/newsloom_platform/database.py)
  and operator readbacks; do not edit applied migration SQL.
- Add an enrichment azd/Terraform layer and immutable-image/operator wiring
  following [the existing flow](../../../azure.yaml). No existing shared resource,
  environment state, runtime identity, region, or model capacity is replaced.
  Manual-to-scheduled transition may require replacement of only the newly
  introduced enrichment job; its preview requires explicit approval.
- Add an enrichment runbook and update the owning capability/phase/ADR evidence,
  not a second product specification.
- Recheck actual deployment contracts, regional availability, quota, and metered
  cost before cloud calls. Existing managed-identity access is the intended path;
  developer inference access is not a prerequisite. Unavailable models, denied
  access, or failed evaluation block rollout, not permission to add keys, grants,
  capacity, or a fallback automatically.
