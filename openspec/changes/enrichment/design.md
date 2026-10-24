# Design

## Context

See [the proposal](proposal.md) for motivation, approved limits and exclusions,
and [the enrichment contract](specs/news-enrichment/spec.md) for acceptance.

Observed implementation constraints:

- The enrichment package contains only its boundary and core dependency.
- [The current migration](../../../services/platform/src/newsloom_platform/migrations/002_ingestion.sql)
  restricts queue status to `pending`; no `news` table or processing lease exists.
  Add a new migration through the existing migration ledger, not startup DDL.
- [Platform model probes](../../../services/platform/src/newsloom_platform/models.py)
  already exercise strict JSON Chat Completions and 1536-dimensional embeddings.
  The enrichment identity already has those inference operations, registry pull,
  telemetry publishing and an Entra database principal, but not domain-table grants.
- Both [ingestion counts](../../../services/ingestion/src/newsloom_ingestion/repository.py)
  and [operator readback](../../../services/platform/src/newsloom_platform/database.py)
  currently call all queue rows pending. Their meaning must change when completed
  rows remain for deduplication.
- The existing azd build, immutable-image, execution and readback pattern is usable.
  [Manual-to-scheduled transitions](../../../docs/ingestion.md) require job
  replacement with the current provider; shared platform state must remain intact.

## Goals / Non-Goals

**Goals:** one small async worker, one relational transaction boundary, existing
model services, explicit failures, and bounded evidence before scheduled rollout.

**Non-Goals:** a workflow engine, ORM, language-classification service, model judge,
general evaluation framework, new infrastructure isolation, or history rewriting.
Acceptance is finite evidence, not a guarantee against hallucination or injection.

## Decisions

### 1. Share the normalized entry shape, not service implementations

Move the existing `Candidate`/`Entry` data contract into core and re-export the
current ingestion names so parsing, screening and stored JSON remain compatible.
Keep ingestion-only limits, counters and decisions in ingestion. Enrichment
depends on core rather than importing the ingestion runtime.

Define narrow async `LlmProvider`, `EmbeddingProvider` and queue-repository
interfaces in enrichment. Add only the workspace's existing dependency families
for HTTP, Entra, PostgreSQL and telemetry to its own manifest. Use the proven
direct HTTP style, not a new SDK/framework or service-wide refactor.

### 2. Make the taxonomy explicit and use stable identifiers

Add a single category catalogue with these labels and identifiers:

| Identifier | Label and main subject |
| --- | --- |
| `regulations` | Regulations: laws, regulatory requirements and regulator enforcement |
| `models` | Models: model releases, capabilities and material model changes |
| `agents-applications` | Agents & Applications: agent systems and end-user AI applications |
| `developer-tools` | Developer Tools: SDKs, frameworks and developer tooling |
| `infrastructure` | Infrastructure: compute, hosting and deployment architecture |
| `research-evaluations` | Research & Evaluations: research methods, benchmarks and evaluation results |
| `security-safety` | Security & Safety: vulnerabilities, attacks, defenses and safety findings |
| `governance` | Governance: AI-agent governance and AI gateways, including access policies, approval, enforcement and auditability |
| `industry-business` | Industry & Business: funding, acquisitions, partnerships and business developments |
| `service-providers` | Service Providers: managed AI services, provider offerings and availability |
| `finops` | FinOps: AI spending, allocation, budgeting and cost optimization |

The main event determines the category, not publisher identity or keyword count.
Agent/gateway governance belongs to Governance, not Regulations; a central legal
change belongs to Regulations. Cost-control articles use FinOps. Gateway articles
must not be classified as generic provider/infrastructure news solely because a
gateway is deployed software. Cover these boundaries in the frozen labelled set.

Generate the request enum from the catalogue and validate the response against
the same identifiers. Database category constraints are authored in the owning
migration, with a test checking that they match the catalogue. Future taxonomy
changes require a deliberate migration, not runtime constraint generation.

### 3. Use isolated strict generation followed by validated embedding

Use the existing configured `gpt-5.4-mini` deployment through
`/openai/v1/chat/completions`, with a fixed trusted instruction message and one
separately serialized untrusted entry. Do not interpolate article text into the
trusted instructions, include earlier articles, supply tools, or fetch source URLs.

The closed generation result contains `summary_sentences`, `category`, and
`tags`. Require 2-3 nonempty sentence strings and at most 100 whitespace-separated
words across their joined text. Persist their joined form as the plain `summary`
field. This avoids using naive punctuation splitting to decide the number of
summary units; sentence-boundary cases, including abbreviations and decimals,
still need tests and quality checks.

Require one known category identifier and 3-5 concise, unique lowercase tags.
Only deterministic whitespace/case normalization is allowed; do not invent
missing fields or run an output-repair model. Reject refusals, missing choices,
non-`stop` termination, invalid JSON, extra fields and invalid values explicitly.
A typed shape does not prove English or factual accuracy: the labelled cases
also have expected English wording/source facts and forbidden-content checks.

Only then call `/openai/v1/embeddings` with the original title, validated summary
and bounded attribution/classification metadata, requesting 1536 dimensions.
Require finite non-boolean numbers, exact dimensionality and nonzero vector norm.
Both adapters share a small bounded request helper within enrichment; credentials
and raw provider bodies never enter diagnostics.

One generation and one embedding request is the normal logical attempt.
Transport retries are bounded exceptions, not a second summarization pipeline.
The prompt, taxonomy and model configuration fingerprints are retained with
evaluation evidence and model metadata with stored news.

### 4. Extend PostgreSQL with recoverable ownership and atomic completion

Add `003_enrichment.sql` through the existing migration ledger. Preserve applied
migrations and all existing queue/quarantine records.

Extend queue states to `pending`, `processing`, `completed`, `failed`,
`dead_letter`; add attempt count, retry time, lease token/expiry, safe last error
and processing/completion timestamps with state constraints and claim indexes.
All existing rows remain pending with no lease.

Create `news` with its queue ID as the primary key/reference, original source,
GUID/full URL/title/date/author attribution, plain summary, primary category,
tags, `vector(1536)`, model/version metadata and timestamps. Keep uniqueness for
source/GUID and full URL, a cosine HNSW index, and indexes needed for later
date/source/category filtering. Do not duplicate the article body into `news`.
Do not delete completed queue rows or introduce retention cleanup in this slice.

Claim one item at a time using `FOR UPDATE SKIP LOCKED`, atomically issuing an
ownership token and increasing its attempt count in a short transaction. Finish
model work outside that transaction. Before inserting news, lock/check the row
against both the token and unexpired lease. Insert news and mark the same claim
completed in one transaction. The final completion update checks the token and
unexpired lease again; any failed fence or SQL operation rolls back both.
Failure writes are fenced too, so a stale worker cannot overwrite a newer claim.

Recover expired claims before selecting eligible work. Exhausted expired claims
must reach dead letter rather than becoming permanently unclaimable. Retries
never reset completed work; no `--force` re-enrichment or quarantine release exists.

Initial bounded implementation profile:

| Boundary | Proposed value |
| --- | --- |
| Job deadline | 900 seconds, reserving 20 seconds for shutdown |
| Request timeout / transport attempts | 30 seconds / at most 3 attempts |
| Per-item deadline / lease | 240 / 300 seconds |
| Queue processing attempts | At most 5, including expired claims |
| Retry eligibility | Exponential delay from 30 seconds, capped at 30 minutes, respecting longer provider Retry-After |
| Work per execution | At most 25 claims, including failed attempts; initial smoke limit 10 |

These are implementation defaults, not observed throughput or model quotas.
Do not claim another item unless its whole item/commit budget fits the remaining
job deadline. Do not sleep beyond the deadline for throttling; persist retry
eligibility instead. Start with sequential processing, not speculative concurrency.

### 5. Keep grants and cross-service readbacks honest

Grant enrichment only queue `SELECT` and processing-column `UPDATE`, plus news
`SELECT`/`INSERT`; retain no queue insert, quarantine access, DDL, delete, admin
or registry-push privilege. Do not grant MCP access before its owning slice.
Extend the existing permission tests and actual managed-identity verification.

Update ingestion's queue count and the platform's `pending`/`screened_pending`
queries to filter pending status, not total stored rows. Add separate processing,
retryable-failed, completed, dead-letter and news counts to enrichment readback.
Preserve ingestion's all-state identity lookup, URLs/fragments, scanner
calibration and quarantine behavior. Test this with retained completed rows.

Use the existing migration identity for fixed read-only aggregate readback. No
developer database grant or firewall exception is required. Compare database
counts to committed run counts rather than interpreting model logs as writes.

### 6. Reuse the deployment flow and gate scheduling on evidence

Add an enrichment Dockerfile, dedicated azd/Terraform layer/backend key, immutable
image build, and explicit build/execute/evaluate/readback operator commands.
Extend the existing helpers rather than copying a parallel provisioning system.
Use the existing enrichment identity and Consumption environment; the layer
depends on migrations. Reuse ingestion's basic job resource profile initially,
without new shared services, identities or model capacity.

Provide `run`, evaluation-only execution, and a validated `--limit` between 1 and
25. Evaluation does not connect to production queue/news tables. It uses the
same adapters and validators under managed identity and emits only safe case IDs,
expected/actual category IDs, assertions, usage and aggregate results.

Freeze 20 authored quality holdouts covering all 11 categories and boundary cases,
separate from development examples, plus separate hostile fixtures in metadata
and body. Validate actual English/sentence/word/tag and source-fact expectations,
not just JSON structure. Require 20 valid outputs, at least 18 correct categories,
zero successful hostile instruction overrides and no missing/incomplete calls.
After the first real run, all 20 quality cases passed and five hostile cases
returned safe valid outputs; the sixth received a confirmed service jailbreak
filter block. The user approved recognizing only that typed block as a completed
hostile defence, not an operational error. Preserve the original failed report.
Require HTTP 400, the known content-filter and policy-violation codes, and strict
detected/filtered jailbreak booleans. Report blocked hostiles separately from
generated hostiles; do not fabricate a category, summary or vector. Unknown
errors still block acceptance, and all benign quality cases still need valid
generated outputs. The prompt, fixtures, labels and model targets remain unchanged.
Record failed gates without relabelling inspected holdouts; a changed prompt
needs a fresh holdout. Do not add a model judge or log raw completions.

Create the new job in manual mode, run quality evaluation, then invoke the live
10-entry smoke immediately. Only after acceptance enable
`*/30 * * * *` UTC with the 25-entry cap. The known manual-to-scheduled provider
transition may replace only this newly added enrichment job; obtain explicit
approval of that preview. Do not replace existing ingestion/migration jobs,
identities or shared resources to avoid that provider limitation.

Add allowlisted enrichment counts, queue depth, request latency and token usage
using the existing authenticated telemetry pattern. No prompts, article bodies,
completions, credentials or arbitrary provider errors enter logs/traces.

## Risks / Trade-offs

- **Categories overlap:** use main-event rules and explicit boundary fixtures;
  do not add multi-category output or publisher defaults to hide ambiguity.
- **Model quality remains imperfect:** enforce structural/size contracts and
  the approved finite quality gates; do not claim unseen-output guarantees.
- **Quota or availability changes:** recheck existing deployments and metered
  cost before inference; stop rather than expand grants/capacity or change models.
- **A crash can repeat paid calls:** fencing guarantees atomic, duplicate-free
  database effects, not exactly-once model billing.
- **Backlog drainage is gradual:** at most 25 entries per half hour; verify real
  progress rather than processing the whole backlog as a smoke test.
- **Job trigger replacement resets execution history:** retain evidence first,
  review the job-only preview, and preserve all PostgreSQL data.

## Migration Plan

1. Implement contracts, migrations, adapters, worker, operator wiring and their
   focused tests. Run the complete local gate and package builds before Azure.
2. Preserve current ingestion/resource/data baselines privately. Preview and
   apply only the new migration and owning enrichment resources through the
   existing azd environment; verify migration replay and table privileges.
3. Run the frozen quality/hostile evaluation in the real enrichment job. A failed
   gate leaves it manual and blocks live/scheduled rollout.
4. Immediately execute the 10-entry smoke. Independently verify nonzero valid
   news, queue completions, embeddings, attribution, no duplicates and unchanged
   quarantine. Exercise rerun/concurrency and bounded cancellation/lease recovery;
   record precisely which behavior was proven locally and in Azure.
5. After acceptance and approval of the job-only transition preview, enable the
   schedule. Verify its actual configuration, runtime telemetry and backlog
   progress without waiting for the next scheduled interval.
6. If deployment or runtime verification fails, stop new enrichment executions
   and disable scheduling through a reviewed job-only transition if the provider
   requires one. Retain news, queue state, leases and the additive
   migration; do not roll the database back to a pending-only constraint.
   Ingestion remains compatible. Restore a compatible verified enrichment image
   if one exists; otherwise leave enrichment stopped until fixed.
7. Record local/Azure evidence before the implementation commit, verify its
   exact-commit CI, then retain separate acceptance evidence and final-head CI.
