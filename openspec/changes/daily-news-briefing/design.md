# Design

## Context

See [proposal](proposal.md) and [behavior contract](specs/daily-news-briefing/spec.md).
The news API is co-hosted with MCP and shares four admission slots, delegated
news.read, strict DTOs, exact-origin policy and a bounded response cache.
The browser NewsCatalog is HTTP-only; Agent interactions remain A2A.
Its panel is currently a heading, early-access notice, context and composer.

Existing enrichment jobs demonstrate Consumption scheduling, managed identity,
zero replica retries and safe diagnostic events. Core ModelClient supplies an
async Entra transport and usage observations. The interactive agent is not a
scheduler: its delegated-user/OBO boundary and ten-item research evidence limit
are unsuitable for all-news weekly synthesis. PostgreSQL migrations currently
establish four foundation workload principals; their mapping checksum must not
be changed retroactively to add a fifth.

## Goals / Non-Goals

**Goals:** One durable shared artifact with TL;DR above a collapsed full briefing,
read without inference and independently of user context; real measurable daily
operation without a speculative dollar budget.

**Non-Goals:** A new chat agent, user impersonation, personalization, web search,
public regeneration, a briefing-history UI or changes to parked evaluations.

## Decisions

### 1. Dedicated scheduled workload, not an interactive-agent call

Add a small Python briefing workspace package/image and native azd
briefing-identity/briefing layers. Use a Consumption job in the retained ACA
environment, cron `0 5 * * *`, parallelism/completion count one and zero
replica retries. Default feature/schedule flags remain off until prerequisites
are verified. Use a 3,600-second worker deadline with shutdown reserve; assert
the platform/provider supports the configured timeout before enablement.

Use its own managed identity, registry pull and scoped telemetry access.
Add a separate deployment of the pinned enrichment chat model/version at
capacity 10 in the retained account/region, leaving existing deployments and
capacity untouched. Check current availability/quota/rate/pricing read-only
first. Reuse typed ModelClient transport, not enrichment generation prompts,
the A2A loop or MCP semantic search; no embeddings are needed.

The new model grant is chat-only at the narrowest supported service scope.
Supported RBAC may be account-scoped: explicitly document actual authority,
and enforce the named endpoint/deployment in the client without claiming
deployment-level RBAC isolation. Never broaden existing principals' grants.

### 2. Additive migrations and durable once-only slots

Create a separate migration for the briefing principal and application tables;
do not alter previous principal/migration checksums or the four-entry foundation
identity manifest. Wire the additional identity explicitly into owning
preparation/migration/readback inputs. Use only Entra DB authentication.

Tables hold metadata-only daily run records and one current published artifact.
Run records identify cutoff, status, safe failure category, evidence count/hash,
prompt/model revision, observed usage, uncertainty and timings; no evidence or
intermediate completions. The current row contains structured summary, TL;DR,
citations and immutable window/version/generation metadata.

The writer can SELECT the existing public-news projection and SELECT/INSERT/
UPDATE only its own tables. MCP receives SELECT only on the current artifact
and a safe refresh-status projection; no model, writer or new delegation grant.
No runtime DDL. Real-role tests must deny news writes and MCP briefing writes.

Derive the slot from the most recent 05:00 UTC cutoff, including a manual
bootstrap before the next trigger. Unique cutoff plus a transactionally
claimed run prevents duplicates. A nonblocking advisory lock spans the job to
prevent overlapping slots. Record intent before inference. A crashed/uncertain
slot becomes failed/unknown, never automatically regenerated; recovery may
reconcile publication state read-only. The next daily slot can proceed.

Validate the entire artifact before atomically replacing the current row and
completing its run. A partial write cannot pair different summary/TL;DR versions.
Keep only current published content; retain metadata-only run accounting, not
historical answer bodies.

### 3. Complete stored-week input with bounded hierarchical synthesis

At claim time freeze `[cutoff - 7 days, cutoff)` and take a repeatable-read
read-only snapshot of eligible committed public news. Stream stable
publication/UUID order into bounded in-memory batches; record total count and
canonical digest. Do not query just the API's 20/50/200-item views or sample a
semantic top-k. Later ingestion is considered in the following daily snapshot.

Every eligible record enters map-stage thematic notes with preserved source IDs.
Reduce notes recursively as required, preserving source membership and resolving
URLs from the frozen source map, then synthesize a coherent weekly summary.
All stages treat article text as untrusted and have no tools. Strict typed
generation envelopes disallow tool calls, refusal/incomplete outputs, unknown
source IDs, invented URLs and malformed structure.

Choose batch/request bytes and completion tokens using the verified deployment
context and 10k-token/minute envelope; pace serial requests and count transport
attempts. Use finite per-call timeouts and at most three transient transport
attempts under the original job deadline. Do not silently drop records to fit
limits or generate repeated repairs until something passes. Failure retains
the previous artifact with an explicit current-slot failure.

Produce 900-1,100 narrative words for ordinary coverage; word count excludes
headings/citation metadata/TL;DR. A structurally labelled limited-evidence result
can be shorter when the corpus is sparse, rather than padding. An empty
snapshot publishes a typed no-news result without any model call.
These are stored summaries/metadata, not verified full-article reporting.

### 4. Derive TL;DR after the summary, publish together

Use a final TL;DR generation call on the validated completed summary and its
resolved citations, not another pass over the original corpus. Request one
English paragraph targeting 60-100 words with only summary-supported claims.
Apply structural/reference checks and reject unknown citations, multi-paragraph
or oversized output. This second stage is part of the same job/run, not a
separate refresh. Any failure leaves the prior published pair intact.

Structural validation does not establish semantic faithfulness. Include authored
claim/citation oracles and a representative live qualitative check of both
summary and TL;DR before acceptance; report limitations, not a fabricated proof.

### 5. Protected read endpoint with explicit status

Add GET `/api/v1/briefing` to the existing enabled API. Extend the typed service/
repository boundary and route result scope without weakening existing contracts.
It returns `{briefing, refresh, meta}`:

- `briefing`: null, or a strict versioned object containing cutoff/window,
  generated_at, coverage/count, one TL;DR paragraph, structured cited summary
  sections and original-source references; no internal prompts or raw evidence.
- `refresh`: expected cutoff, state (`pending`, `running`, `ready`, `failed`)
  and stale flag. Safe fixed failure categories only, not worker exception text.
- `meta`: existing read_at/cache_age_seconds with a dedicated briefing scope.

No artifact yet is an explicit null with status, not a 404 pretending a service
failure is empty news. A no-news artifact is distinct. DB/service failures retain
the API error envelope; last-good content on generation failure is an explicit
publication state, not a catch-all successful fallback.

Authorize before every read/cache hit. Reuse the same per-caller cache bounds,
60-second absolute TTL, no-store responses, four-slot capacity and cancellation/
privacy rules. Include the expected UTC cutoff in cache identity so yesterday's
ready status cannot survive today's 05:00 boundary. The first request never
starts a job. No POST/regeneration endpoint or new browser scope/config.

### 6. Panel display separate from conversation state

Extend NewsCatalog/HttpCatalog with `briefing` and an independent cancellable
read lane. Load only when signed in and the panel opens; reuse for up to 60
seconds, refresh while open at most once per minute and on resumption. Close,
sign-out and teardown cancel owned reads and ignore late results. Retry is
read-only. An error must not suppress the composer or discard the answer.

Place a labelled briefing region below heading/Close, above the notice/context/
composer. TL;DR stays visible; native details/summary contains the complete cited
summary, initially closed and reset closed only on a new artifact version.
Use safe text/link/citation helpers and browser-local timestamps; don't force
the interactive-answer 16-KiB parser onto a larger briefing response.
Expansion, refresh and version changes never modify question, filters, selected
items, submitted A2A snapshots or focus. Preserve independent panel scrolling.

Show actual seven-day bounds, generated-at, roughly five-minute reading cue,
all-news scope and pending/stale/failed/no-news states compactly. Clearly
identify it as a generated overview of stored reporting, not the user's answer.

### 7. Measure before budgeting

No daily dollar budget or automatic spend cutoff. Persist observed per-stage/
per-run physical calls, input/output tokens, latency and available usage.
Mark lost/uncertain usage explicitly and never turn it into zero. Estimate
model cost using a dated verified price basis; keep hosting/ACR/build costs
separate and disclose when they are unmeasured. No content in logs/traces/job
output. Normal context/deadline/retry and once-only controls remain reliability
boundaries, not user spending policy.

## Risks / Trade-offs

- Large weekly input may exceed the finite job deadline -> fail explicitly,
  report actual volume/latency and retain stale content; never silently sample.
- Generative synthesis can omit themes or misstate claims -> deterministic
  provenance checks plus authored semantic oracles and live qualitative
  acceptance; citations alone are not quality proof.
- Dedicated model deployment consumes additional quota -> validate before
  provisioning; leave existing capacity untouched and stop on incompatibility.
- Persisting a shared completion is new product data -> store only the current
  protected artifact, not prompts/intermediates; retain content-free diagnostics.
- A once-only failed slot can stay stale until tomorrow -> show failure honestly;
  no automatic duplicate paid generation after an uncertain result.

## Migration Plan

1. Implement additive contracts/migrations/worker/API/UI and local real-role,
   model-transport, browser/axe and accounting tests; update phase capability,
   ADR, security grant inventory and owning runbooks. Keep runtime flags off.
2. Verify model/quota/price read-only; preview only owning additive identity/
   model/migration/job changes with exact preservation fingerprints. The user's
   no-confirmation instruction authorizes this declared scope, not unrelated
   grants, capacity increases or replacement of retained infrastructure.
3. Apply identity/model, versioned migration and disabled/manual job through
   native azd. Deploy the API then matching UI without new consent/config.
4. Execute one bootstrap slot, inspect actual artifact/usage and denied writes/
   anonymous access, verify source assets/backends and then enable 05:00 UTC
   scheduling. Verify a real scheduled execution separately; a manual start
   does not establish scheduler acceptance. Retain all unavailable acceptance.
5. Commit implementation, exact-source CI and separate measured status.
   Rollback first disables scheduling, then restores matching API/UI images;
   preserve tables/run accounting and identities. Never roll back data by
   deleting resources or rewriting migration history.
