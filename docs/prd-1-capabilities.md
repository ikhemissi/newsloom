# PRD-1 capabilities: MCP news platform

This document owns behavior, user stories, acceptance criteria, and open product
decisions. [PRD-1](prd-1.md) owns phase status, prerequisites, and the delivery plan.
Architectural decisions are recorded in [the ADRs](adrs.md).

## P1-C01: Configuration-driven source curation

**Outcome:** Operators control the news sources without changing application code.

**User stories**
- **P1-C01-US1:** As a news curator, I want to configure feed IDs, titles, URLs,
  and formats so that ingestion uses an explicit catalogue of primary sources.
- **P1-C01-US2:** As a news curator, I want optional publisher-category allowlists
  so that broad feeds contribute only relevant AI news.

**Acceptance criteria**
- Ingestion reads [feeds.json](../config/feeds.json), governed by the
  [OpenSpec catalogue contract](../openspec/specs/repository-foundation/spec.md#requirement-validated-initial-feed-catalogue).
- RSS and Atom are supported; JSON Feed remains optional.
- `include_categories` matches feed-supplied category terms after splitting commas,
  trimming, and case-insensitive exact comparison.
- Publisher terms and attribution requirements are reviewed before production use.

## P1-C02: Safe feed retrieval and normalization

**Outcome:** Public feed documents become bounded, consistent entries without
giving publishers access to internal networks or unrestricted processing.

**User stories**
- **P1-C02-US1:** As a news reader, I want entries from different publishers
  normalized consistently so that dates, authors, titles, and links are usable.
- **P1-C02-US2:** As a platform operator, I want hostile or malformed feeds
  constrained so that one publisher cannot compromise or exhaust ingestion.

**Acceptance criteria**
- The ingestion ACA job runs on a schedule and can also be started manually.
- Retrieval permits public addresses only, pins DNS per request and redirect,
  honors robots.txt, and enforces size, time, and redirect limits with retry backoff.
- Parsing prohibits DTDs/entities and resolves relative links. Normalized fields
  include source ID, title, canonical URL, published time, author, categories,
  and bounded text.
- Conditional requests use ETags, but validators are not saved when no entries
  parsed. A `--force` refetch remains available.
- Fixtures cover hostile networks/documents, relative links, and large feeds.
- Malformed items are isolated from valid siblings. Missing fields use feed data,
  then JSON-LD/OpenGraph, then bounded article text from one protected response
  without following article redirects. Ingestion extracts text; P1-C05 owns summaries.
- The existing feed catalogue rows record latest-run malformed, screening and
  acquisition-path counts, distinguishing duplicate occurrences and backlog work.

## P1-C03: Content screening and quarantine

**Outcome:** Rejected or not-yet-accepted content cannot enter the news-serving path.

**User stories**
- **P1-C03-US1:** As an MCP user, I want incoming entries screened for prompt
  injection so that hostile feed content is not silently accepted into the platform.
- **P1-C03-US2:** As a platform operator, I want rejected entries retained with
  their decisions and reasons so that rejection is inspectable without losing data.

**Acceptance criteria**
- Every entry passes through `ContentSecurityScanner`. Accepted entries enter
  `ingestion_queue` as `pending`; rejected entries go to quarantine.
- Scanner errors fail closed and are retried, never treated as acceptance.
- The model scanner uses a threshold calibrated on labelled examples, respects
  its rate limit, and passes clean/hostile fixture tests.
- The [delivered screening contract](../openspec/specs/content-screening/spec.md)
  distinguishes consumer-directed manipulation from contextual reporting,
  examples, and training-use notices; it binds calibration to policy/model
  configuration and requires a local paired comparison before rollout.
  Acceptance never makes source content trusted or guarantees attack absence.
- The scanner is replaceable behind its interface. There is no deployed no-op,
  bypass flag, or acceptance fallback; fake verdicts are exclusive to tests.
- Nothing in quarantine is automatically deleted. Model constraints and replacement
  planning follow ADR-6.

## P1-C04: Idempotent ingestion and durable processing

**Outcome:** Reruns, concurrent workers, and crashes do not lose ownership of work
or publish duplicate news.

**User stories**
- **P1-C04-US1:** As a news reader, I want each article represented once so that
  repeated ingestion does not flood my results with duplicates.
- **P1-C04-US2:** As a platform operator, I want leased, recoverable queue work
  so that interrupted or competing enrichment runs can safely resume.

**Acceptance criteria**
- Ingestion deduplicates on `(source, GUID)` or canonical URL and is idempotent.
- PostgreSQL queue operations sit behind a repository interface. Claims use
  `FOR UPDATE SKIP LOCKED`, fenced ownership, and lease-expiry recovery.
- States are `pending -> processing -> completed | failed -> dead_letter`,
  with attempts, timestamps, and a safe last error.
- Writing `news` and completing its queue item happens in one transaction.
- Duplicate-free reruns, concurrent claims, and kill-mid-run recovery are tested
  locally and verified in Azure as applicable to the slice.
- Azure verification demonstrates that the pending enrichment backlog drains.

## P1-C05: Structured model enrichment and embeddings

**Outcome:** Accepted entries become enriched news suitable for reading and search.

**User stories**
- **P1-C05-US1:** As a news reader, I want a summary, category, and tags so that
  I can assess relevance without reading every original article.
- **P1-C05-US2:** As a platform maintainer, I want replaceable model providers
  so that model changes do not require rewriting the processing workflow.

**Acceptance criteria**
- The scheduled enrichment job makes one GPT call for a closed-schema result
  containing summary, a category from a fixed list, and tags.
- One embedding call uses title, summary, and metadata and produces 1536 dimensions.
- `LlmProvider` and `EmbeddingProvider` isolate Foundry integrations; model
  deployments are configured according to ADR-5.
- Feed text is delimited as untrusted data, enrichment has no tools, and invalid
  outputs cannot be treated as successful enrichment.
- Labelled evaluations check output validity and category accuracy.

## P1-C06: Recent news, item details, and source discovery

**Outcome:** MCP clients can browse stored news and discover available filters.

**User stories**
- **P1-C06-US1:** As a signed-in MCP user, I want recent news and full stored
  details for a selected item so that I can catch up and inspect relevant stories.
- **P1-C06-US2:** As a signed-in MCP user, I want available sources and categories
  so that I can choose valid filters without guessing.

**Acceptance criteria**
- The always-on ACA app exposes streamable HTTP and the tools
  `get_recent_news(limit, since?)`, `get_news_item(id)`, and `list_sources()`.
- News results expose ID, title, summary, source, category, tags, published date,
  and URL; ranked results also include similarity score.
- Source discovery includes available sources and categories.
- Tools serve stored `news` only, never queued/quarantined content, and never
  fetch a URL supplied by a caller.
- A signed-in VS Code user can retrieve correct structured results from Azure.

## P1-C07: Filtered semantic search

**Outcome:** Users can find conceptually relevant news within explicit metadata limits.

**User stories**
- **P1-C07-US1:** As a signed-in MCP user, I want to search by meaning so that
  relevant stories are discoverable even when their wording differs from my query.
- **P1-C07-US2:** As a signed-in MCP user, I want source, category, tag, and date
  filters so that search stays focused on the news I need.

**Acceptance criteria**
- `search_news(query?, source?, category?, tags?, from?, to?, limit)` supports
  metadata-only search, semantic search, or both.
- A supplied query is embedded and ranked by pgvector cosine similarity within
  the requested filters, not ranked globally and filtered afterward.
- Stored embeddings use `vector(1536)` and an HNSW index; source, category, tags,
  and publication date have supporting indexes.
- Frozen-query evaluations measure recall@k with and without filters.

## P1-C08: User authentication and least-privilege workload access

**Outcome:** Only authorized users can query news, and each workload has only
the database and inference permissions its role needs.

**User stories**
- **P1-C08-US1:** As a news reader, I want to sign in with Entra rather than
  manage an API key so that access uses my organizational identity.
- **P1-C08-US2:** As a platform operator, I want separate workload identities
  so that an MCP reader cannot consume queue work or write news.

**Acceptance criteria**
- MCP validates bearer-token signature, issuer, audience, and `news.read` scope.
  Missing, forged, wrong-audience, and wrong-scope tokens are rejected.
- Users' tokens are never forwarded to PostgreSQL.
- Each unit has its own user-assigned managed identity and migration-created role:
  ingestion writes queue/quarantine; enrichment consumes the queue and writes news;
  MCP reads news only.
- PostgreSQL uses Entra-only authentication; Foundry key access is disabled and
  inference permissions are limited per workload. No passwords, keys, or client
  secrets are introduced.
- VS Code sign-in compatibility without Entra dynamic client registration is
  verified rather than assumed.

## P1-C09: Independently deployable, persistent Azure platform

**Outcome:** Operators can update and scale the platform without replacing its
developer environment or coupling the three workloads.

**User stories**
- **P1-C09-US1:** As a platform operator, I want independent ACA apps/jobs so that
  ingestion, enrichment, and MCP capacity can be managed separately.
- **P1-C09-US2:** As a developer, I want repeatable migrations and deployments
  so that an update preserves stored news and infrastructure state.

**Acceptance criteria**
- ACA workloads share typed libraries, not a runtime identity. PostgreSQL 18
  Flexible Server with pgvector stores `feed_sources`, `ingestion_queue`,
  `quarantine`, and `news`.
- Schema and role changes run through a migration job, never application startup.
- Terraform is driven by azd with common tags, registry image builds, and job-update
  hooks. Remote state follows the
  [OpenSpec bootstrap contract](../openspec/specs/repository-foundation/spec.md#requirement-secretless-remote-state-bootstrap).
  Keep one persistent developer environment.
- V1 uses public Entra-protected app ingress and a PostgreSQL Azure-services
  firewall rule; private networking and Front Door remain later work.
- Region/SKU capacity and subscription-shared model quotas are checked before
  provisioning.
- `azd up`, an Azure smoke test, and a least-privilege grant inventory verify the platform.

## P1-C10: Safe operational visibility

**Outcome:** Operators can diagnose pipeline health without accessing article
content or leaking sensitive data.

**User stories**
- **P1-C10-US1:** As a platform operator, I want pipeline counts and latencies
  so that I can identify feed failures, queue backlog, and slow model/search calls.
- **P1-C10-US2:** As a platform operator, I want end-to-end correlation without
  content logging so that I can trace an entry while protecting its data.

**Acceptance criteria**
- OpenTelemetry and structured logs reach Application Insights with Entra-only
  ingestion; a correlation ID connects feed entry to news item.
- Metrics cover feeds ok/failed, entries found, duplicates, accepted/rejected,
  queue depth, enrichment ok/failed, LLM/embedding latency and tokens, MCP latency,
  and vector-search latency.
- An attribute allowlist excludes tokens, credentials, article text, prompts, and
  completions. Third-party HTTP loggers stay at WARNING.
- Job logs carry safe counts so runs remain observable without developer database
  access; an optional read-only developer role remains an explicit decision.

## P1-C11: Evidence-based platform acceptance

**Outcome:** Maintainers can demonstrate correctness and quality before Phase 2 starts.

**User stories**
- **P1-C11-US1:** As a maintainer, I want repeatable adversarial and concurrency
  tests so that reruns and hostile inputs cannot silently break the platform.
- **P1-C11-US2:** As a maintainer, I want labelled and frozen evaluation sets
  so that scanner, enrichment, and retrieval quality can be measured consistently.

**Acceptance criteria**
- Local PostgreSQL tests cover migrations, idempotency, and concurrent/crashed work.
- Hostile retrieval/parsing fixtures, scanner calibration, enrichment validity and
  category accuracy, retrieval recall@k, and MCP contract/authentication tests run.
- A short Azure integration workflow uses a federated test identity.
- Phase acceptance demonstrates Entra-signed-in VS Code browsing/semantic search,
  hostile-fixture quarantine, and duplicate-free rerun/crash recovery in Azure.

## Decisions still required

The owning slices must settle core/model regions, PostgreSQL capacity/SKU, model
capacities, category-list values, scanner threshold/replacement, and VS Code
sign-in compatibility. Verify current model availability, including ADR-6's preview
limits and deprecation date, and evaluate whether the decision model should classify
categories. Do not invent numeric operating limits or evaluation pass thresholds;
define and verify them in the relevant OpenSpec changes.
